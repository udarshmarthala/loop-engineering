import asyncio
import sys
import types

from schemas.task import Task
from tools.registry import registry


class _FakeAnthropic:
    def __init__(self):
        self.messages = types.SimpleNamespace(create=lambda **kwargs: None)


sys.modules.setdefault("anthropic", types.SimpleNamespace(Anthropic=_FakeAnthropic))

from executor import run  # noqa: E402


def test_example_tools_are_registered():
    tool_names = {tool["name"] for tool in registry.list_tools()}

    assert "python_repl" in tool_names
    assert "grep_tool" in tool_names


def test_executor_uses_registered_tool():
    @registry.tool(
        "echo_tool",
        "Echo a value from the provided inputs.",
        {"type": "object"},
    )
    async def echo_tool(inputs: dict, scratchpad: dict) -> dict:
        return {"output": inputs.get("value", ""), "success": True}

    try:
        task = Task(
            id="dyn-1",
            description="echo input",
            expected_output="hello",
            tool="echo_tool",
            inputs={"value": "hello"},
        )

        result = asyncio.run(run(task, {}))

        assert result.success is True
        assert result.output == "hello"
    finally:
        registry.unregister("echo_tool")
