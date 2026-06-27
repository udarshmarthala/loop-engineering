from typing import Literal, Optional
from pydantic import BaseModel


class EvalResult(BaseModel):
    task_id: str
    status: Literal["ok", "retry", "fail"]
    reason: str
    confidence: float = 1.0
    suggestion: Optional[str] = None
