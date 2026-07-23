"""
Self-improving loop: logs human corrections to agent outputs and exports a
preference-tuning dataset (chosen/rejected pairs) for offline fine-tuning
(Unsloth / llama.cpp LoRA workflows).

ponytail: export_preference_dataset re-reads the whole corrections file on
every call — fine up to low-thousands of rows. Upgrade path: track a byte/line
cursor if this needs to scale past that.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parent.parent
CORRECTIONS_FILE = PROJECT_ROOT / "data" / "corrections.jsonl"
FINETUNE_DIR = PROJECT_ROOT / "data" / "finetune_data"
EXPORT_THRESHOLD = 50


def log_correction(task: str, wrong: str, right: str, agent: str = "") -> dict[str, Any]:
    """Append a correction record. Auto-exports a fresh preference dataset
    once EXPORT_THRESHOLD corrections have accumulated; callers can also
    export on demand via export_preference_dataset()."""
    CORRECTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": time.time(),
        "task": task,
        "wrong": wrong,
        "right": right,
        "agent": agent,
    }
    with CORRECTIONS_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    count = _count_corrections()
    exported = export_preference_dataset(FINETUNE_DIR) if count >= EXPORT_THRESHOLD else None

    return {"logged": True, "count": count, "exported": exported}


def load_corrections() -> list[dict]:
    """Read all logged corrections."""
    if not CORRECTIONS_FILE.exists():
        return []
    records = []
    with CORRECTIONS_FILE.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _count_corrections() -> int:
    if not CORRECTIONS_FILE.exists():
        return 0
    with CORRECTIONS_FILE.open(encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def export_preference_dataset(out_dir: Path | str = FINETUNE_DIR) -> str | None:
    """Write {instruction, chosen, rejected} JSONL from all logged corrections.
    Returns the output file path, or None if there are no corrections yet."""
    records = load_corrections()
    if not records:
        return None

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"preferences_{int(time.time())}.jsonl"

    with out_path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps({
                "instruction": r["task"],
                "chosen": r["right"],
                "rejected": r["wrong"],
            }) + "\n")

    return str(out_path)


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        orig_file, orig_dir = CORRECTIONS_FILE, FINETUNE_DIR
        CORRECTIONS_FILE = Path(tmp) / "corrections.jsonl"
        FINETUNE_DIR = Path(tmp) / "finetune_data"
        try:
            assert export_preference_dataset(FINETUNE_DIR) is None
            result = log_correction("summarize X", "wrong answer", "right answer", "summarizer")
            assert result["count"] == 1 and result["exported"] is None
            out = export_preference_dataset(FINETUNE_DIR)
            assert out and Path(out).exists()
            row = json.loads(Path(out).read_text().strip().splitlines()[0])
            assert row == {"instruction": "summarize X", "chosen": "right answer", "rejected": "wrong answer"}
            print("self_improve self-check: OK")
        finally:
            CORRECTIONS_FILE, FINETUNE_DIR = orig_file, orig_dir
