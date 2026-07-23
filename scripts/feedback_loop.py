#!/usr/bin/env python3
"""
Export the preference dataset built from logged corrections and print a
one-line hint for kicking off a LoRA fine-tune with Unsloth or llama.cpp.

Usage:
  python scripts/feedback_loop.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.self_improve import FINETUNE_DIR, _count_corrections, export_preference_dataset


def main():
    count = _count_corrections()
    print(f"Corrections logged: {count}")

    out_path = export_preference_dataset(FINETUNE_DIR)
    if not out_path:
        print("No corrections yet — nothing to export. Log some with `python main.py feedback log`.")
        return

    print(f"Exported preference dataset: {out_path}")
    print(
        "Fine-tune hint: load the base model in Unsloth, train with its DPO/ORPO "
        f"trainer on '{out_path}' (instruction/chosen/rejected), then convert the "
        "LoRA to GGUF with llama.cpp's convert_lora_to_gguf.py to serve locally via Ollama."
    )


if __name__ == "__main__":
    main()
