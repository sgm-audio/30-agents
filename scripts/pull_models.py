#!/usr/bin/env python3
"""
Pull all required Ollama models with exponential-backoff retry and checkpoint resume.

Features:
- Checks if model already exists before pulling
- Exponential backoff: 30s, 60s, 120s, 240s... up to 10 attempts
- Checkpoint file to resume interrupted pulls
- Sleep/resume detection
- Progress reporting
"""
import json
import logging
import subprocess
import sys
import time
from pathlib import Path

log = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────
MODELS = [
    "nomic-embed-text",                                  # embeddings
    "hf.co/evalengine/unbound-e2b-gguf:Q4_K_M",         # fast agent
    "minicpm-v:8b",                                      # vision/multimodal
    "huihui_ai/gemma-4-abliterated:e4b-q4_K",            # reasoning
]

CHECKPOINT_FILE = Path(__file__).parent.parent / "data" / "pull_checkpoint.json"
MAX_ATTEMPTS = 7
BASE_WAIT = 10  # seconds (reduced for faster retries)

# ── Helpers ───────────────────────────────────────────────

def load_checkpoint() -> dict:
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    if CHECKPOINT_FILE.exists():
        try:
            return json.loads(CHECKPOINT_FILE.read_text())
        except Exception as e:
            log.warning("checkpoint.load_failed", error=str(e))
    return {}


def save_checkpoint(data: dict):
    CHECKPOINT_FILE.write_text(json.dumps(data, indent=2))


def model_exists(model: str) -> bool:
    """Check if model is already present in Ollama."""
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True, text=True, timeout=10
        )
        # Model names may include digest suffix; check prefix match
        model_base = model.split(":")[0]
        return model in result.stdout or model_base in result.stdout
    except Exception:
        return False


def wait_for_ollama(max_wait: int = 60) -> bool:
    """Wait until Ollama is responsive."""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            result = subprocess.run(
                ["ollama", "list"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                return True
        except Exception as e:
            log.debug("ollama.wait_retry", error=str(e))
        print("  Waiting for Ollama...", flush=True)
        time.sleep(3)
    return False


def pull_model(model: str) -> bool:
    """Pull a single model with streaming output. Returns True on success."""
    print(f"\n  Pulling {model}...", flush=True)
    try:
        proc = subprocess.Popen(
            ["ollama", "pull", model],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
            bufsize=1,
        )
        last_line = ""
        for line in proc.stdout:
            line = line.rstrip()
            if line and line != last_line:
                print(f"    {line}", flush=True)
                last_line = line
        proc.wait()
        return proc.returncode == 0
    except KeyboardInterrupt:
        proc.terminate()
        print("\n  Interrupted by user.")
        return False
    except Exception as e:
        print(f"  Pull exception: {e}")
        return False


def pull_with_retry(model: str, checkpoint: dict) -> bool:
    """Pull model with exponential backoff, skipping if already done."""

    # Already successfully pulled?
    if checkpoint.get(model) == "done":
        print(f"[OK] {model} already pulled (checkpoint)")
        return True

    # Already in Ollama?
    if model_exists(model):
        print(f"[OK] {model} already present in Ollama")
        checkpoint[model] = "done"
        save_checkpoint(checkpoint)
        return True

    attempts = checkpoint.get(f"{model}_attempts", 0)

    for attempt in range(attempts, MAX_ATTEMPTS):
        checkpoint[f"{model}_attempts"] = attempt + 1
        save_checkpoint(checkpoint)

        print(f"\n{'='*50}")
        print(f"  {model} — attempt {attempt + 1}/{MAX_ATTEMPTS}")
        print(f"{'='*50}")

        # Ensure Ollama is up
        if not wait_for_ollama():
            print("  ERROR: Ollama not responding. Is it running?")
            sys.exit(1)

        success = pull_model(model)

        if success and model_exists(model):
            checkpoint[model] = "done"
            checkpoint[f"{model}_attempts"] = attempt + 1
            save_checkpoint(checkpoint)
            print(f"\n[OK] {model} pulled successfully!")
            return True

        if attempt < MAX_ATTEMPTS - 1:
            wait_sec = BASE_WAIT * (2 ** attempt)
            wait_sec = min(wait_sec, 3600)  # cap at 1 hour
            print(f"\n  Pull failed. Retrying in {wait_sec}s...")
            try:
                time.sleep(wait_sec)
            except KeyboardInterrupt:
                print("\nAborted by user.")
                sys.exit(1)

        print(f"\nFAIL {model}: failed after {MAX_ATTEMPTS} attempts")
    return False


# ── Main ──────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  30-Agent System — Model Pull Script")
    print("=" * 60)

    checkpoint = load_checkpoint()
    print(f"  Checkpoint file: {CHECKPOINT_FILE}")
    print(f"  Models to pull: {', '.join(MODELS)}\n")

    if not wait_for_ollama(max_wait=30):
        print("ERROR: Ollama is not running. Start it first:")
        print("  systemctl --user start ollama")
        sys.exit(1)

    failed = []
    for model in MODELS:
        ok = pull_with_retry(model, checkpoint)
        if not ok:
            failed.append(model)

    print("\n" + "=" * 60)
    print("  Pull Summary")
    print("=" * 60)
    for model in MODELS:
        status = "OK" if checkpoint.get(model) == "done" else "FAILED"
        print(f"  {status}  {model}")

    if failed:
        print(f"\nFailed models: {failed}")
        print("Re-run this script to retry failed models.")
        sys.exit(1)
    else:
        print("\nAll models pulled successfully!")


if __name__ == "__main__":
    main()
