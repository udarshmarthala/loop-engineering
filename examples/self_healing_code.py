"""Run tests → find failures → patch → re-run until green."""
import asyncio
from loop import run

GOAL = """
Run pytest on the src/ directory.
If tests fail, identify the failing test, read the relevant source file,
patch the bug, and re-run tests. Repeat until all tests pass.
"""

if __name__ == "__main__":
    trace = asyncio.run(run(GOAL.strip()))
    print(f"\nCompleted in {len(trace)} steps.")
