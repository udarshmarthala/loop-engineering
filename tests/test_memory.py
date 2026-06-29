import pytest

from memory import LongTermMemory


def test_long_term_memory_requires_flag(monkeypatch):
    monkeypatch.setattr("memory.ENABLE_LONG_TERM_MEMORY", False)

    with pytest.raises(RuntimeError, match="ENABLE_LONG_TERM_MEMORY=True"):
        LongTermMemory()
