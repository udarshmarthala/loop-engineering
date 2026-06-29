import asyncio
import sys
import types

sys.modules.setdefault(
    "anthropic",
    types.SimpleNamespace(
        Anthropic=lambda: types.SimpleNamespace(
            messages=types.SimpleNamespace(create=lambda **kwargs: None)
        )
    ),
)

import server  # noqa: E402


def test_status_endpoint_defaults():
    status = asyncio.run(server.get_status())

    assert status["status"] in {"idle", "running", "stopped", "done", "failed"}
    assert "queue_depth" in status
    assert "registered_tools" in status


def test_sse_generator_starts_connected():
    event = asyncio.run(server._event_generator().__anext__())

    assert "CONNECTED" in event
