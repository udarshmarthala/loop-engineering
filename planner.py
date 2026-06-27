import json
from pathlib import Path
import anthropic
from schemas.task import Task, TaskList
from config import LLM_MODEL


client = anthropic.Anthropic()
_PLANNER_PROMPT = Path("prompts/planner.txt").read_text()


async def plan(goal: str, memory_summary: str = "No prior steps.") -> TaskList:
    prompt = _PLANNER_PROMPT.format(goal=goal, memory_summary=memory_summary)
    message = client.messages.create(
        model=LLM_MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    data = json.loads(raw)
    return TaskList(goal=goal, tasks=[Task(**t) for t in data["tasks"]])


async def refine(task: Task, suggestion: str) -> Task:
    prompt = (
        f"Refine this task based on the evaluator suggestion.\n"
        f"Task: {task.model_dump_json()}\n"
        f"Suggestion: {suggestion}\n"
        f"Return ONLY the updated task JSON."
    )
    message = client.messages.create(
        model=LLM_MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    data = json.loads(raw)
    return Task(**data)
