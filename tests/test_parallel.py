import asyncio
import sys
import types
from unittest.mock import AsyncMock, patch

sys.modules.setdefault(
    "anthropic",
    types.SimpleNamespace(Anthropic=lambda: types.SimpleNamespace(messages=types.SimpleNamespace(create=lambda **kwargs: None))),
)

from schemas.eval_result import EvalResult
from schemas.task import ParallelTaskGroup, Task, TaskPlan, TaskResult
from loop import run_with_parallelism


def make_task(task_id: str, command: str = "echo hello") -> Task:
    return Task(
        id=task_id,
        description=f"run {task_id}",
        expected_output="hello",
        tool="bash",
        inputs={"command": command},
    )


def test_parallel_group_runs_all_tasks():
    group = ParallelTaskGroup(group_id="group-1", tasks=[make_task("t1"), make_task("t2")])
    task_plan = TaskPlan(goal="parallel goal", steps=[group])

    task_one = group.tasks[0]
    task_two = group.tasks[1]
    result_one = TaskResult(task_id=task_one.id, output="hello", success=True)
    result_two = TaskResult(task_id=task_two.id, output="hello", success=True)
    eval_one = EvalResult(task_id=task_one.id, status="ok", reason="ok", confidence=1.0)
    eval_two = EvalResult(task_id=task_two.id, status="ok", reason="ok", confidence=1.0)

    with (
        patch("loop.planner_mod.plan_with_parallelism", new=AsyncMock(return_value=task_plan)),
        patch("loop.executor_mod.run", new=AsyncMock(side_effect=[result_one, result_two])),
        patch("loop.evaluator_mod.evaluate", new=AsyncMock(side_effect=[eval_one, eval_two])),
    ):
        trace = asyncio.run(run_with_parallelism("parallel goal"))

    assert len(trace) == 2
    assert {entry["task"]["id"] for entry in trace} == {"t1", "t2"}
    assert all(entry["eval"]["status"] == "ok" for entry in trace)
