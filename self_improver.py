"""Self-improvement module: analyse loop failures and evolve prompt files.

Prompt versions are stored as:
  prompts/{name}_v1.txt
  prompts/{name}_v2.txt
  ...

The original unversioned file (e.g. prompts/planner.txt) is treated as v0.
"""

import json
import re
from pathlib import Path

import anthropic

from config import LLM_MODEL


_PROMPTS_DIR = Path("prompts")
_client = anthropic.Anthropic()


class SelfImprover:
    """Analyses past loop failures and rewrites prompt files to improve them."""

    # ------------------------------------------------------------------
    # Failure analysis
    # ------------------------------------------------------------------

    async def analyze_failures(self, trace: list[dict]) -> list[str]:
        """Extract actionable lessons from failed/retried tasks in a trace.

        Args:
            trace: The list returned by Memory.full_trace().

        Returns:
            A list of lesson strings (may be empty if no failures found).
        """
        failed_steps = [
            entry for entry in trace
            if entry.get("eval", {}).get("status") in ("retry", "fail")
        ]
        if not failed_steps:
            return []

        summary = json.dumps(failed_steps, indent=2)
        prompt = (
            "You are a meta-learning agent. Analyse the following failed/retried loop steps "
            "and extract a concise list of lessons that would help avoid these failures in "
            "future runs. Focus on actionable, generalisable insights — not task-specific "
            "details. Return ONLY a JSON array of strings, each a single lesson.\n\n"
            f"Failed steps:\n{summary}"
        )
        message = _client.messages.create(
            model=LLM_MODEL,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text.strip()
        # Strip markdown fences if present
        raw = re.sub(r"^```[a-z]*\n?", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"\n?```$", "", raw, flags=re.MULTILINE)
        lessons: list[str] = json.loads(raw)
        return lessons

    # ------------------------------------------------------------------
    # Prompt evolution
    # ------------------------------------------------------------------

    async def evolve_prompt(self, prompt_name: str, failures: list[str]) -> str:
        """Rewrite a prompt file incorporating failure lessons.

        Args:
            prompt_name: Base name without extension, e.g. "planner" or "evaluator".
            failures: Lessons returned by analyze_failures().

        Returns:
            The new prompt text (also saved via save_evolved_prompt).
        """
        current = self.get_best_prompt(prompt_name)
        lessons_text = "\n".join(f"- {l}" for l in failures)

        prompt = (
            "You are a prompt engineering expert. Rewrite the following system prompt to "
            "address the lessons learned from past failures. Preserve the original intent "
            "and structure but improve clarity, add guard-rails for known failure modes, "
            "and make instructions more precise. Return ONLY the improved prompt text — "
            "no preamble, no markdown fences.\n\n"
            f"=== CURRENT PROMPT ===\n{current}\n\n"
            f"=== LESSONS FROM FAILURES ===\n{lessons_text}"
        )
        message = _client.messages.create(
            model=LLM_MODEL,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        evolved = message.content[0].text.strip()
        self.save_evolved_prompt(prompt_name, evolved)
        return evolved

    # ------------------------------------------------------------------
    # Versioned persistence
    # ------------------------------------------------------------------

    def save_evolved_prompt(self, prompt_name: str, content: str) -> None:
        """Save *content* as the next version of the named prompt.

        Files are written as prompts/{name}_v{n}.txt where n starts at 1.
        """
        _PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
        next_version = self._next_version(prompt_name)
        dest = _PROMPTS_DIR / f"{prompt_name}_v{next_version}.txt"
        dest.write_text(content)

    def get_best_prompt(self, prompt_name: str) -> str:
        """Return the content of the latest evolved version, or the original if none exist."""
        _PROMPTS_DIR.mkdir(parents=True, exist_ok=True)
        latest = self._latest_version_path(prompt_name)
        if latest is not None:
            return latest.read_text()
        # Fall back to the unversioned original
        original = _PROMPTS_DIR / f"{prompt_name}.txt"
        if original.exists():
            return original.read_text()
        return ""

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _all_versions(self, prompt_name: str) -> list[Path]:
        """Return all versioned files for a prompt, sorted by version number."""
        pattern = re.compile(rf"^{re.escape(prompt_name)}_v(\d+)\.txt$")
        versioned: list[tuple[int, Path]] = []
        for p in _PROMPTS_DIR.glob(f"{prompt_name}_v*.txt"):
            m = pattern.match(p.name)
            if m:
                versioned.append((int(m.group(1)), p))
        versioned.sort(key=lambda t: t[0])
        return [p for _, p in versioned]

    def _latest_version_path(self, prompt_name: str) -> Path | None:
        versions = self._all_versions(prompt_name)
        return versions[-1] if versions else None

    def _next_version(self, prompt_name: str) -> int:
        versions = self._all_versions(prompt_name)
        if not versions:
            return 1
        # Parse the highest existing version number and increment
        pattern = re.compile(rf"^{re.escape(prompt_name)}_v(\d+)\.txt$")
        highest = max(int(pattern.match(p.name).group(1)) for p in versions)
        return highest + 1
