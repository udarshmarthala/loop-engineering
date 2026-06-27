import pytest
from unittest.mock import patch, MagicMock
from schemas.task import Task, TaskResult
from schemas.eval_result import EvalResult


def make_task():
    return Task(
        id="t1",
        description="run tests",
        expected_output="all tests pass",
        tool="bash",
        inputs={"command": "pytest"},
    )


@pytest.mark.asyncio
async def test_deterministic_failure_path():
    from evaluator import evaluate
    task = make_task()
    result = TaskResult(task_id="t1", output="", success=False, error="command not found")

    eval_result = await evaluate(task, result)

    assert eval_result.status == "retry"
    assert "command not found" in eval_result.reason
    assert eval_result.confidence == 1.0


@pytest.mark.asyncio
async def test_llm_eval_ok():
    from evaluator import evaluate
    task = make_task()
    result = TaskResult(task_id="t1", output="5 passed", success=True)

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='{"task_id":"t1","status":"ok","reason":"tests passed","confidence":0.95,"suggestion":null}')]

    with patch("evaluator.client.messages.create", return_value=mock_response):
        eval_result = await evaluate(task, result)

    assert eval_result.status == "ok"
    assert eval_result.confidence == 0.95
