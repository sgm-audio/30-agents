"""Tests for core/self_improve.py — correction logging + preference export."""
import json
from pathlib import Path

import pytest

from core import self_improve


@pytest.fixture(autouse=True)
def tmp_data_dir(tmp_path, monkeypatch):
    """Redirect the module's data paths to a tmp dir for every test."""
    monkeypatch.setattr(self_improve, "CORRECTIONS_FILE", tmp_path / "corrections.jsonl")
    monkeypatch.setattr(self_improve, "FINETUNE_DIR", tmp_path / "finetune_data")
    return tmp_path


def test_log_correction_appends_jsonl():
    self_improve.log_correction("summarize X", "wrong", "right", "summarizer")

    lines = self_improve.CORRECTIONS_FILE.read_text().strip().splitlines()
    assert len(lines) == 1

    record = json.loads(lines[0])
    assert record["task"] == "summarize X"
    assert record["wrong"] == "wrong"
    assert record["right"] == "right"
    assert record["agent"] == "summarizer"
    assert "ts" in record


def test_export_preference_dataset_empty_returns_none():
    assert self_improve.export_preference_dataset(self_improve.FINETUNE_DIR) is None


def test_export_preference_dataset_writes_chosen_rejected():
    self_improve.log_correction("task1", "bad1", "good1", "agentA")
    self_improve.log_correction("task2", "bad2", "good2", "agentB")

    out = self_improve.export_preference_dataset(self_improve.FINETUNE_DIR)
    assert out is not None

    rows = [json.loads(line) for line in Path(out).read_text().strip().splitlines()]
    assert len(rows) == 2
    assert rows[0] == {"instruction": "task1", "chosen": "good1", "rejected": "bad1"}
    assert rows[1] == {"instruction": "task2", "chosen": "good2", "rejected": "bad2"}


def test_export_auto_triggers_at_threshold(monkeypatch):
    monkeypatch.setattr(self_improve, "EXPORT_THRESHOLD", 2)

    result1 = self_improve.log_correction("t1", "b1", "g1")
    assert result1["exported"] is None

    result2 = self_improve.log_correction("t2", "b2", "g2")
    assert result2["exported"] is not None
    assert result2["count"] == 2
