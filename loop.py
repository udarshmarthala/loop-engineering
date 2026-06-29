import asyncio
import json
import logging
import argparse
from memory import Memory
from schemas.eval_result import EvalResult
from schemas.task import Task, TaskResult, ParallelTaskGroup
import planner as planner_mod
import executor as executor_mod
import evaluator as evaluator_mod
from config import (
    MAX_LOOP_ITERATIONS,
    CONFIDENCE_THRESHOLD,
    LOG_LEVEL,
    SELF_IMPROVE_FAILURE_THRESHOLD,
)


logging.basicConfig(level=getattr(logging, LOG_LEVEL))
log = logging.getLogger("loop")

# Optionally bridged to the SSE server — set by server.py at startup
_sse_queue: "asyncio.Queue | None" = None


class LoopLimitExceeded(Exception):
    pass


class TaskFailed(Exception):
    pass


def set_sse_queue(q: asyncio.Queue) -> None:
    """Called by server.py to wire the SSE event queue into the loop."""
    global _sse_queue
    _sse_queue = q


def emit(event: str, iteration: int, **kwargs) -> None:
    payload = {"event": event, "iteration": iteration, **kwargs}
    log.info(json.dumps(payload))

    # Bridge to SSE stream if server is running
    if _sse_queue is not None:
        try:
            _sse_queue.put_nowait(payload)
        except asyncio.QueueFull:
            pass  # non-blocking: drop if consumer is slow


async def run_parallel_group(
    group: ParallelTaskGroup,
    memory: Memory,
    scratchpad: dict,
    iteration_counter: list[int],
    max_iterations: int,
) -> list[TaskResult]:
    """Run all tasks in a ParallelTaskGroup concurrently via asyncio.gather.

    Each task is executed, evaluated, and added to memory. Results are returned
    in the same order as group.tasks.

    Args:
        group: The parallel group to execute.
        memory: Shared memory (adds entries after each task).
        scratchpad: Shared scratchpad injected into every executor call.
        iteration_counter: Single-element list used as a mutable int counter.
        max_iterations: Hard cap on total iterations.

    Returns:
        List of TaskResult objects in task order.

    Raises:
        LoopLimitExceeded: If the iteration cap is hit.
        TaskFailed: If any task in the group reaches a hard-fail status.
    """
    async def _run_one(task: Task) -> TaskResult:
        iteration_counter[0] += 1
        if iteration_counter[0] > max_iterations:
            raise LoopLimitExceeded(f"Hit {max_iterations} iterations")

        emit("EXEC", iteration_counter[0], task_id=task.id, tool=task.tool, parallel=True)
        result = await executor_mod.run(task, scratchpad)

        emit("EVAL", iteration_counter[0], task_id=task.id, parallel=True)
        eval_result = await evaluator_mod.evaluate(task, result)
        memory.add(task, result, eval_result)

        emit(
            eval_result.status.upper(),
            iteration_counter[0],
            task_id=task.id,
            reason=eval_result.reason,
            confidence=eval_result.confidence,
            suggestion=eval_result.suggestion,
            parallel=True,
        )

        if eval_result.status == "fail":
            raise TaskFailed(task.id, eval_result.reason)

        return result

    results = await asyncio.gather(*[_run_one(t) for t in group.tasks])
    return list(results)


async def run(goal: str, max_iterations: int = MAX_LOOP_ITERATIONS) -> list[dict]:
    memory = Memory()
    task_list = await planner_mod.plan(goal, memory.summary())
    emit("PLAN", 0, goal=goal, tasks=[t.id for t in task_list.tasks])

    iteration = 0
    failure_count = 0

    for task in task_list.tasks:
        retries = 0
        while retries <= task.max_retries:
            iteration += 1
            if iteration > max_iterations:
                raise LoopLimitExceeded(f"Hit {max_iterations} iterations")

            emit("EXEC", iteration, task_id=task.id, tool=task.tool)
            result = await executor_mod.run(task, memory.scratchpad)

            emit("EVAL", iteration, task_id=task.id)
            eval_result = await evaluator_mod.evaluate(task, result)

            memory.add(task, result, eval_result)

            emit(
                eval_result.status.upper(),
                iteration,
                task_id=task.id,
                reason=eval_result.reason,
                confidence=eval_result.confidence,
                suggestion=eval_result.suggestion,
            )

            if eval_result.confidence < CONFIDENCE_THRESHOLD:
                print(
                    f"\n[HUMAN GATE] Low confidence ({eval_result.confidence:.2f}) on task '{task.id}'.\n"
                    f"Reason: {eval_result.reason}\n"
                    f"Continue? (y/n): ",
                    end="",
                    flush=True,
                )
                answer = input().strip().lower()
                if answer != "y":
                    raise TaskFailed(task.id, "Human rejected low-confidence step")

            if eval_result.status == "ok":
                break
            elif eval_result.status == "retry":
                failure_count += 1
                if eval_result.suggestion:
                    task = await planner_mod.refine(task, eval_result.suggestion)
                retries += 1
            else:  # fail
                failure_count += 1
                raise TaskFailed(task.id, eval_result.reason)

    trace = memory.full_trace()

    # Self-improvement: analyse failures and evolve prompts if threshold exceeded
    if failure_count >= SELF_IMPROVE_FAILURE_THRESHOLD:
        try:
            from self_improver import SelfImprover
            improver = SelfImprover()
            emit("SELF_IMPROVE", iteration, failure_count=failure_count)
            lessons = await improver.analyze_failures(trace)
            if lessons:
                for prompt_name in ("planner", "evaluator"):
                    await improver.evolve_prompt(prompt_name, lessons)
                emit("PROMPTS_EVOLVED", iteration, prompts=["planner", "evaluator"], lessons=lessons)
        except Exception as exc:
            log.warning(f"Self-improvement step failed (non-fatal): {exc}")

    emit("DONE", iteration, goal=goal)
    return trace


async def run_with_parallelism(goal: str, max_iterations: int = MAX_LOOP_ITERATIONS) -> list[dict]:
    """Variant of run() that uses plan_with_parallelism for concurrent task groups."""
    memory = Memory()
    task_plan = await planner_mod.plan_with_parallelism(goal, memory.summary())
    step_ids = [
        s.group_id if isinstance(s, ParallelTaskGroup) else s.id
        for s in task_plan.steps
    ]
    emit("PLAN", 0, goal=goal, steps=step_ids, mode="parallel")

    iteration_counter = [0]  # mutable counter shared with run_parallel_group
    failure_count = 0

    for step in task_plan.steps:
        if isinstance(step, ParallelTaskGroup):
            emit("PARALLEL_GROUP_START", iteration_counter[0], group_id=step.group_id,
                 tasks=[t.id for t in step.tasks])
            await run_parallel_group(step, memory, memory.scratchpad, iteration_counter, max_iterations)
            emit("PARALLEL_GROUP_DONE", iteration_counter[0], group_id=step.group_id)
        else:
            # Sequential task — same logic as run()
            task = step
            retries = 0
            while retries <= task.max_retries:
                iteration_counter[0] += 1
                if iteration_counter[0] > max_iterations:
                    raise LoopLimitExceeded(f"Hit {max_iterations} iterations")

                emit("EXEC", iteration_counter[0], task_id=task.id, tool=task.tool)
                result = await executor_mod.run(task, memory.scratchpad)

                emit("EVAL", iteration_counter[0], task_id=task.id)
                eval_result = await evaluator_mod.evaluate(task, result)
                memory.add(task, result, eval_result)

                emit(
                    eval_result.status.upper(),
                    iteration_counter[0],
                    task_id=task.id,
                    reason=eval_result.reason,
                    confidence=eval_result.confidence,
                    suggestion=eval_result.suggestion,
                )

                if eval_result.confidence < CONFIDENCE_THRESHOLD:
                    print(
                        f"\n[HUMAN GATE] Low confidence ({eval_result.confidence:.2f}) "
                        f"on task '{task.id}'.\nContinue? (y/n): ",
                        end="", flush=True,
                    )
                    if input().strip().lower() != "y":
                        raise TaskFailed(task.id, "Human rejected low-confidence step")

                if eval_result.status == "ok":
                    break
                elif eval_result.status == "retry":
                    failure_count += 1
                    if eval_result.suggestion:
                        task = await planner_mod.refine(task, eval_result.suggestion)
                    retries += 1
                else:
                    failure_count += 1
                    raise TaskFailed(task.id, eval_result.reason)

    trace = memory.full_trace()

    if failure_count >= SELF_IMPROVE_FAILURE_THRESHOLD:
        try:
            from self_improver import SelfImprover
            improver = SelfImprover()
            emit("SELF_IMPROVE", iteration_counter[0], failure_count=failure_count)
            lessons = await improver.analyze_failures(trace)
            if lessons:
                for prompt_name in ("planner", "evaluator"):
                    await improver.evolve_prompt(prompt_name, lessons)
                emit("PROMPTS_EVOLVED", iteration_counter[0], prompts=["planner", "evaluator"])
        except Exception as exc:
            log.warning(f"Self-improvement step failed (non-fatal): {exc}")

    emit("DONE", iteration_counter[0], goal=goal)
    return trace


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--goal", required=True)
    parser.add_argument("--log-level", default=LOG_LEVEL)
    parser.add_argument("--parallel", action="store_true", help="Use parallel planning")
    args = parser.parse_args()

    logging.getLogger("loop").setLevel(getattr(logging, args.log_level.upper()))
    fn = run_with_parallelism if args.parallel else run
    asyncio.run(fn(args.goal))
