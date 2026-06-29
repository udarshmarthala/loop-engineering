from __future__ import annotations

from typing import Annotated, Literal, Optional, Union
from pydantic import BaseModel, Field


class Task(BaseModel):
    id: str
    description: str
    expected_output: str
    tool: str  # built-ins: bash/file/web/llm; registry tools: any string
    inputs: dict
    max_retries: int = 3


class TaskList(BaseModel):
    tasks: list[Task]
    goal: str


class TaskResult(BaseModel):
    task_id: str
    output: str
    success: bool
    error: Optional[str] = None
    artifacts: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Parallel execution schemas (Feature 4)
# ---------------------------------------------------------------------------


class ParallelTaskGroup(BaseModel):
    """A group of tasks that are safe to run concurrently via asyncio.gather."""

    group_id: str
    tasks: list[Task]


# TaskPlan steps may be either individual Tasks or ParallelTaskGroups.
PlanStep = Annotated[
    Union[ParallelTaskGroup, Task],
    Field(discriminator=None),  # resolved structurally by pydantic
]


class TaskPlan(BaseModel):
    """A mixed sequential + parallel execution plan."""

    goal: str
    steps: list[Union[ParallelTaskGroup, Task]]
