"""FastAPI SSE server for the loop-engineering agent.

Endpoints
---------
GET  /stream          — SSE stream of all loop events (text/event-stream)
POST /run             — Start a new loop run:   {"goal": "..."}
GET  /status          — Current loop state
POST /stop            — Stop the running loop
POST /inject          — Inject a human override: {"instruction": "..."}

Start with:
    uvicorn server:app --reload --port 8000

Or programmatically:
    import uvicorn; uvicorn.run(app, host="0.0.0.0", port=8000)
"""

from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

import loop as loop_mod

# ---------------------------------------------------------------------------
# Shared state
# ---------------------------------------------------------------------------

event_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)

_state: dict = {
    "status": "idle",          # idle | running | stopped | done | failed
    "goal": None,
    "started_at": None,
    "iteration": 0,
    "last_event": None,
}

_current_task: asyncio.Task | None = None
_human_injection: asyncio.Queue = asyncio.Queue(maxsize=10)


# ---------------------------------------------------------------------------
# Wire the loop's emit() into our queue
# ---------------------------------------------------------------------------

loop_mod.set_sse_queue(event_queue)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class RunRequest(BaseModel):
    goal: str
    max_iterations: int = 20
    use_parallel: bool = False


class InjectRequest(BaseModel):
    instruction: str


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # Cancel any running loop on shutdown
    if _current_task and not _current_task.done():
        _current_task.cancel()


app = FastAPI(title="Loop Engineering Server", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "http://localhost:8080", "http://127.0.0.1:*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _push_event(event: str, **data) -> None:
    """Push an event into the SSE queue (non-blocking; drops on full queue)."""
    payload = {"event": event, "ts": time.time(), **data}
    _state["last_event"] = payload
    try:
        event_queue.put_nowait(payload)
    except asyncio.QueueFull:
        pass


async def _run_loop(goal: str, max_iterations: int, use_parallel: bool) -> None:
    """Coroutine that drives loop.run() and updates server state."""
    global _state
    _state.update({"status": "running", "goal": goal, "started_at": time.time(), "iteration": 0})
    _push_event("SERVER_START", goal=goal)

    try:
        fn = loop_mod.run_with_parallelism if use_parallel else loop_mod.run
        trace = await fn(goal, max_iterations)
        _state["status"] = "done"
        _push_event("SERVER_DONE", goal=goal, steps=len(trace))
    except loop_mod.LoopLimitExceeded as exc:
        _state["status"] = "failed"
        _push_event("SERVER_ERROR", error=str(exc), kind="limit_exceeded")
    except loop_mod.TaskFailed as exc:
        _state["status"] = "failed"
        _push_event("SERVER_ERROR", error=str(exc), kind="task_failed")
    except asyncio.CancelledError:
        _state["status"] = "stopped"
        _push_event("SERVER_STOPPED", goal=goal)
    except Exception as exc:
        _state["status"] = "failed"
        _push_event("SERVER_ERROR", error=str(exc), kind="unexpected")


# ---------------------------------------------------------------------------
# SSE stream
# ---------------------------------------------------------------------------

async def _event_generator() -> AsyncGenerator[str, None]:
    """Drain the event_queue and yield SSE-formatted strings."""
    # Send an initial connection confirmation
    yield f"data: {json.dumps({'event': 'CONNECTED', 'ts': time.time()})}\n\n"

    while True:
        try:
            payload = await asyncio.wait_for(event_queue.get(), timeout=15.0)
            yield f"data: {json.dumps(payload)}\n\n"
        except asyncio.TimeoutError:
            # Heartbeat to keep the connection alive
            yield f": heartbeat {time.time()}\n\n"


@app.get("/stream")
async def stream_events():
    """SSE endpoint — connect here to receive all loop events in real time."""
    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Control endpoints
# ---------------------------------------------------------------------------

@app.post("/run")
async def start_run(req: RunRequest):
    """Start a new loop run. Rejects if a run is already in progress."""
    global _current_task

    if _state["status"] == "running":
        raise HTTPException(status_code=409, detail="A loop is already running. POST /stop first.")

    if _current_task and not _current_task.done():
        _current_task.cancel()

    _current_task = asyncio.create_task(
        _run_loop(req.goal, req.max_iterations, req.use_parallel)
    )
    return {"status": "started", "goal": req.goal}


@app.get("/status")
async def get_status():
    """Return the current loop state."""
    return {
        **_state,
        "queue_depth": event_queue.qsize(),
        "registered_tools": [],  # populated lazily — avoids importing registry at module load
    }


@app.post("/stop")
async def stop_run():
    """Cancel the currently running loop (if any)."""
    global _current_task

    if _current_task and not _current_task.done():
        _current_task.cancel()
        _state["status"] = "stopped"
        _push_event("SERVER_STOPPED", reason="user_request")
        return {"status": "stopped"}

    return {"status": "not_running"}


@app.post("/inject")
async def inject_instruction(req: InjectRequest):
    """Inject a human override instruction into the running loop.

    The instruction is pushed to _human_injection queue. The loop (or a future
    human-gate extension) can drain this queue to incorporate mid-run guidance.
    """
    if _state["status"] != "running":
        raise HTTPException(status_code=409, detail="No loop is currently running.")

    await _human_injection.put(req.instruction)
    _push_event("HUMAN_INJECT", instruction=req.instruction)
    return {"status": "injected", "instruction": req.instruction}


# ---------------------------------------------------------------------------
# Dev entry-point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
