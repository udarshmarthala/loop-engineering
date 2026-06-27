"""Targeted: fix a specific failing test file."""
import asyncio
import sys
from loop import run

test_file = sys.argv[1] if len(sys.argv) > 1 else "tests/"

GOAL = f"""
Run pytest on {test_file}.
For each failing test: read the test, read the implementation it tests,
identify the bug, write a fix, re-run only that test.
Stop when all tests in {test_file} pass.
"""

if __name__ == "__main__":
    trace = asyncio.run(run(GOAL.strip()))
    print(f"\nCompleted in {len(trace)} steps.")
