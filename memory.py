import json
from schemas.task import Task, TaskResult
from schemas.eval_result import EvalResult


class Memory:
    def __init__(self):
        self.trace: list[dict] = []
        self.scratchpad: dict = {}

    def add(self, task: Task, result: TaskResult, eval_result: EvalResult) -> None:
        self.trace.append({
            "task": task.model_dump(),
            "result": result.model_dump(),
            "eval": eval_result.model_dump(),
        })

    def summary(self) -> str:
        if not self.trace:
            return "No prior steps."
        lines = []
        for entry in self.trace:
            status = entry["eval"]["status"]
            desc = entry["task"]["description"]
            lines.append(f"[{status.upper()}] {desc}")
        return "\n".join(lines)

    def full_trace(self) -> list[dict]:
        return self.trace
