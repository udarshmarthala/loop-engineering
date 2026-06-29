import sys
import types


class _FakeAnthropic:
    def __init__(self):
        self.messages = types.SimpleNamespace(create=lambda **kwargs: None)


sys.modules.setdefault("anthropic", types.SimpleNamespace(Anthropic=_FakeAnthropic))

from self_improver import SelfImprover


def test_prompt_versioning_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr("self_improver._PROMPTS_DIR", tmp_path)

    (tmp_path / "planner.txt").write_text("base planner")

    improver = SelfImprover()
    assert improver.get_best_prompt("planner") == "base planner"

    improver.save_evolved_prompt("planner", "planner v1")
    improver.save_evolved_prompt("planner", "planner v2")

    assert (tmp_path / "planner_v1.txt").read_text() == "planner v1"
    assert (tmp_path / "planner_v2.txt").read_text() == "planner v2"
    assert improver.get_best_prompt("planner") == "planner v2"
