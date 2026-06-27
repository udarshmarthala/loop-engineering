import json
from pathlib import Path
import anthropic
from schemas.task import Task, TaskResult
from schemas.eval_result import EvalResult
from config import LLM_MODEL, CONFIDENCE_THRESHOLD


client = anthropic.Anthropic()
_EVAL_PROMPT = Path("prompts/evaluator.txt").read_text()


async def evaluate(task: Task, result: TaskResult) -> EvalResult:
    # deterministic fast-path: explicit failure
    if not result.success and result.error:
        return EvalResult(
            task_id=task.id,
            status="retry",
            reason=f"Executor error: {result.error}",
            confidence=1.0,
            suggestion=f"Fix the error: {result.error}",
        )

    prompt = _EVAL_PROMPT.format(
        task=task.model_dump_json(),
        result=result.model_dump_json(),
    )
    message = client.messages.create(
        model=LLM_MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    data = json.loads(raw)
    eval_result = EvalResult(task_id=task.id, **{k: v for k, v in data.items() if k != "task_id"})

    # low confidence → mark for human gate (caller checks CONFIDENCE_THRESHOLD)
    return eval_result
