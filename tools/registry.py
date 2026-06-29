"""Dynamic tool registry for the loop-engineering executor.

Usage
-----
Register at import time via the decorator::

    from tools.registry import registry

    @registry.tool("my_tool", "Does something useful", {"type": "object", ...})
    async def my_tool(inputs: dict, scratchpad: dict) -> dict:
        ...

Or imperatively::

    registry.register("my_tool", my_tool_fn, "Does something", schema)

The executor checks the registry before falling back to built-in tools.
"""

from __future__ import annotations

from typing import Callable


class ToolRegistry:
    """Singleton registry that maps tool names to callables + metadata."""

    _instance: "ToolRegistry | None" = None

    def __new__(cls) -> "ToolRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools: dict[str, dict] = {}
        return cls._instance

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        name: str,
        fn: Callable,
        description: str,
        input_schema: dict,
    ) -> None:
        """Register a tool callable.

        Args:
            name: Unique tool identifier (used in Task.tool field).
            fn: Async callable with signature ``async (inputs: dict, scratchpad: dict) -> dict``.
                The dict should contain at least ``output`` (str) and ``success`` (bool).
            description: Human-readable description of what the tool does.
            input_schema: JSON-Schema dict describing expected inputs.
        """
        self._tools[name] = {
            "name": name,
            "fn": fn,
            "description": description,
            "schema": input_schema,
        }

    def unregister(self, name: str) -> None:
        """Remove a tool from the registry. No-op if not present."""
        self._tools.pop(name, None)

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, name: str) -> Callable | None:
        """Return the callable for *name*, or None if not registered."""
        entry = self._tools.get(name)
        return entry["fn"] if entry else None

    def list_tools(self) -> list[dict]:
        """Return metadata for all registered tools (excludes the callable)."""
        return [
            {"name": e["name"], "description": e["description"], "schema": e["schema"]}
            for e in self._tools.values()
        ]

    # ------------------------------------------------------------------
    # Decorator
    # ------------------------------------------------------------------

    @staticmethod
    def tool(name: str, description: str, input_schema: dict):
        """Decorator that registers the decorated function as a tool.

        Example::

            @registry.tool("my_tool", "Runs my logic", {"type": "object"})
            async def my_tool(inputs: dict, scratchpad: dict) -> dict:
                return {"output": "done", "success": True}
        """
        def decorator(fn: Callable) -> Callable:
            # Use the global singleton
            _registry = ToolRegistry()
            _registry.register(name, fn, description, input_schema)
            return fn
        return decorator


# Global singleton — import this everywhere
registry = ToolRegistry()
