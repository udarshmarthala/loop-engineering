"""Search → read → summarize → identify gaps → search again → compile report."""
import asyncio
from loop import run

GOAL = """
Research the topic: "loop-based autonomous agents in production".
Search the web for 3 relevant articles, summarize each, identify knowledge gaps,
search for 2 more targeted articles to fill gaps, then compile a final structured report.
Save the report to output/research_report.md.
"""

if __name__ == "__main__":
    trace = asyncio.run(run(GOAL.strip()))
    print(f"\nCompleted in {len(trace)} steps.")
