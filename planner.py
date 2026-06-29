import json
from pathlib import Path
import anthropic
from schemas.task import Task, TaskList, TaskPlan, ParallelTaskGroup
from config import LLM_MODEL


client = anthropic.Anthropic()
_PLANNER_PROMPT = Path("prompts/planner.txt").read_text()

_PARALLEL_PROMPT = """\
You are a planning agent with expertise in parallel task scheduling.
Given a user goal, decompose it into an ordered execution plan where tasks that have
no data dependency on each other are grouped for concurrent execution.

Return ONLY valid JSON matching this schema:
{
  "goal": "<goal string>",
  "steps": [
    // Each step is either a single Task OR a ParallelTaskGroup
    // Single sequential task:
    {"id": "...", "description": "...", "expected_output": "...", "tool": "bash|file|web|llm", "inputs": {...}, "max_retries": 3},
    // Group of tasks to run concurrently:
    {"group_id": "...", "tasks": [ <Task>, <Task>, ... ]}
  ]
}

Rules:
- Only group tasks when they have no shared mutable state and do not depend on each other's output.
- When in doubt, keep tasks sequential (do not group).
- Preserve ordering constraints — a later step may depend on an earlier step's output.

Goal: {goal}
Memory: {memory_summary}
"""


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


async def plan_with_parallelism(goal: str, memory_summary: str = "No prior steps.") -> TaskPlan:
    """Ask the LLM to produce a mixed sequential + parallel TaskPlan.

    Tasks that are independent are wrapped in ParallelTaskGroup entries so the
    loop controller can run them concurrently via asyncio.gather.
    """
    prompt = _PARALLEL_PROMPT.format(goal=goal, memory_summary=memory_summary)
    message = client.messages.create(
        model=LLM_MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    data = json.loads(raw)

    steps: list = []
    for step in data.get("steps", []):
        if "group_id" in step:
            # It's a ParallelTaskGroup
            tasks = [Task(**t) for t in step["tasks"]]
            steps.append(ParallelTaskGroup(group_id=step["group_id"], tasks=tasks))
        else:
            steps.append(Task(**step))

    return TaskPlan(goal=goal, steps=steps)
