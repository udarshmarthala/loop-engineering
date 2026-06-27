import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from schemas.task import Task, TaskList, TaskResult
from schemas.eval_result import EvalResult
from loop import run, LoopLimitExceeded, TaskFailed


def make_task(id="t1", tool="bash"):
    return Task(
        id=id,
        description="echo hello",
        expected_output="hello",
        tool=tool,
        inputs={"command": "echo hello"},
    )


def make_task_list(tasks=None):
    tasks = tasks or [make_task()]
    return TaskList(goal="test goal", tasks=tasks)


@pytest.mark.asyncio
async def test_successful_run():
    task = make_task()
    result = TaskResult(task_id="t1", output="hello", success=True)
    eval_ok = EvalResult(task_id="t1", status="ok", reason="output matches", confidence=1.0)

    with (
        patch("loop.planner_mod.plan", new=AsyncMock(return_value=make_task_list([task]))),
        patch("loop.executor_mod.run", new=AsyncMock(return_value=result)),
        patch("loop.evaluator_mod.evaluate", new=AsyncMock(return_value=eval_ok)),
    ):
        trace = await run("echo hello")
    assert len(trace) == 1
    assert trace[0]["eval"]["status"] == "ok"


@pytest.mark.asyncio
async def test_retry_then_success():
    task = make_task()
    result_fail = TaskResult(task_id="t1", output="", success=False, error="oops")
    result_ok = TaskResult(task_id="t1", output="hello", success=True)
    eval_retry = EvalResult(task_id="t1", status="retry", reason="failed", confidence=1.0, suggestion="fix it")
    eval_ok = EvalResult(task_id="t1", status="ok", reason="done", confidence=1.0)

    exec_calls = [result_fail, result_ok]
    eval_calls = [eval_retry, eval_ok]

    with (
        patch("loop.planner_mod.plan", new=AsyncMock(return_value=make_task_list([task]))),
        patch("loop.executor_mod.run", new=AsyncMock(side_effect=exec_calls)),
        patch("loop.evaluator_mod.evaluate", new=AsyncMock(side_effect=eval_calls)),
        patch("loop.planner_mod.refine", new=AsyncMock(return_value=task)),
    ):
        trace = await run("echo hello")
    assert trace[-1]["eval"]["status"] == "ok"


@pytest.mark.asyncio
async def test_loop_limit_exceeded():
    task = Task(id="t1", description="x", expected_output="x", tool="bash", inputs={}, max_retries=100)
    result = TaskResult(task_id="t1", output="", success=False, error="fail")
    eval_retry = EvalResult(task_id="t1", status="retry", reason="fail", confidence=1.0)

    with (
        patch("loop.planner_mod.plan", new=AsyncMock(return_value=make_task_list([task]))),
        patch("loop.executor_mod.run", new=AsyncMock(return_value=result)),
        patch("loop.evaluator_mod.evaluate", new=AsyncMock(return_value=eval_retry)),
        patch("loop.planner_mod.refine", new=AsyncMock(return_value=task)),
    ):
        with pytest.raises(LoopLimitExceeded):
            await run("x", max_iterations=3)


@pytest.mark.asyncio
async def test_task_failed():
    task = make_task()
    result = TaskResult(task_id="t1", output="", success=False)
    eval_fail = EvalResult(task_id="t1", status="fail", reason="unrecoverable", confidence=1.0)

    with (
        patch("loop.planner_mod.plan", new=AsyncMock(return_value=make_task_list([task]))),
        patch("loop.executor_mod.run", new=AsyncMock(return_value=result)),
        patch("loop.evaluator_mod.evaluate", new=AsyncMock(return_value=eval_fail)),
    ):
        with pytest.raises(TaskFailed):
            await run("fail goal")
