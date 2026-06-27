import asyncio
import json
import logging
import argparse
from memory import Memory
from schemas.eval_result import EvalResult
import planner as planner_mod
import executor as executor_mod
import evaluator as evaluator_mod
from config import MAX_LOOP_ITERATIONS, CONFIDENCE_THRESHOLD, LOG_LEVEL


logging.basicConfig(level=getattr(logging, LOG_LEVEL))
log = logging.getLogger("loop")


class LoopLimitExceeded(Exception):
    pass


class TaskFailed(Exception):
    pass


def emit(event: str, iteration: int, **kwargs) -> None:
    payload = {"event": event, "iteration": iteration, **kwargs}
    log.info(json.dumps(payload))


async def run(goal: str, max_iterations: int = MAX_LOOP_ITERATIONS) -> list[dict]:
    memory = Memory()
    task_list = await planner_mod.plan(goal, memory.summary())
    emit("PLAN", 0, goal=goal, tasks=[t.id for t in task_list.tasks])

    iteration = 0

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
                if eval_result.suggestion:
                    task = await planner_mod.refine(task, eval_result.suggestion)
                retries += 1
            else:
                raise TaskFailed(task.id, eval_result.reason)

    emit("DONE", iteration, goal=goal)
    return memory.full_trace()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--goal", required=True)
    parser.add_argument("--log-level", default=LOG_LEVEL)
    args = parser.parse_args()

    logging.getLogger("loop").setLevel(getattr(logging, args.log_level.upper()))
    asyncio.run(run(args.goal))
