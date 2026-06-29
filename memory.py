import json
import uuid
from schemas.task import Task, TaskResult
from schemas.eval_result import EvalResult
from config import ENABLE_LONG_TERM_MEMORY, CHROMA_PATH


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


class LongTermMemory:
    """Persistent semantic memory backed by ChromaDB.

    Only initialised when ENABLE_LONG_TERM_MEMORY=True (config.py).
    Two collections:
      - "runs"      — stores completed loop traces keyed by goal
      - "learnings" — stores task-type-specific lessons
    """

    def __init__(self, path: str = CHROMA_PATH):
        if not ENABLE_LONG_TERM_MEMORY:
            raise RuntimeError(
                "LongTermMemory requires ENABLE_LONG_TERM_MEMORY=True in config.py"
            )
        try:
            import chromadb
        except ImportError as exc:
            raise ImportError(
                "chromadb is required for LongTermMemory. "
                "Install it with: pip install chromadb>=0.5.0"
            ) from exc

        self._client = chromadb.PersistentClient(path=path)
        self._runs = self._client.get_or_create_collection("runs")
        self._learnings = self._client.get_or_create_collection("learnings")

    # ------------------------------------------------------------------
    # Run storage
    # ------------------------------------------------------------------

    def store_run(self, goal: str, trace: list[dict], outcome: str) -> None:
        """Persist a completed loop run for future retrieval.

        Args:
            goal: The original goal string.
            trace: Full Memory.full_trace() list.
            outcome: One of "success" | "failure" | "partial".
        """
        doc_id = str(uuid.uuid4())
        document = json.dumps({"goal": goal, "outcome": outcome, "trace": trace})
        self._runs.add(
            ids=[doc_id],
            documents=[document],
            metadatas=[{"goal": goal, "outcome": outcome}],
        )

    def retrieve_similar(self, goal: str, n: int = 3) -> list[dict]:
        """Return the *n* most semantically similar past runs.

        Returns a list of dicts with keys: goal, outcome, trace.
        """
        results = self._runs.query(query_texts=[goal], n_results=min(n, self._runs.count()))
        if not results or not results.get("documents"):
            return []
        docs = results["documents"][0]
        return [json.loads(d) for d in docs]

    # ------------------------------------------------------------------
    # Learning storage
    # ------------------------------------------------------------------

    def store_learning(self, task_type: str, lesson: str) -> None:
        """Persist a lesson learned for a given task type (e.g. "bash", "web")."""
        doc_id = str(uuid.uuid4())
        self._learnings.add(
            ids=[doc_id],
            documents=[lesson],
            metadatas=[{"task_type": task_type}],
        )

    def retrieve_learnings(self, task_type: str, n: int = 5) -> list[str]:
        """Return up to *n* relevant lessons for the given task type."""
        count = self._learnings.count()
        if count == 0:
            return []
        results = self._learnings.query(
            query_texts=[task_type],
            n_results=min(n, count),
            where={"task_type": task_type} if count > 0 else None,
        )
        if not results or not results.get("documents"):
            return []
        return results["documents"][0]
