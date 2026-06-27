from typing import Literal, Optional
from pydantic import BaseModel, Field


class Task(BaseModel):
    id: str
    description: str
    expected_output: str
    tool: Literal["bash", "file", "web", "llm"]
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
