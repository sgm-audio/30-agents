#!/usr/bin/env python3
"""
Setup script: install dependencies, verify environment, prepare system.
Run once before first launch.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
VENV_DIR = PROJECT_ROOT / "venv"

def run(cmd: list[str], check: bool = True, **kwargs) -> subprocess.CompletedProcess:
    print(f"  $ {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, **kwargs)
    if check and result.returncode != 0:
        print(f"  ERROR: command failed (exit {result.returncode})")
        sys.exit(result.returncode)
    return result


def main():
    print("=" * 60)
    print("  30-Agent System — Setup")
    print("=" * 60)

    # 1. Create data dirs
    print("\n[1] Creating directories...")
    for d in ["data/chroma", "logs", "data"]:
        (PROJECT_ROOT / d).mkdir(parents=True, exist_ok=True)
        print(f"  OK: {d}")

    # 2. Python venv
    print(f"\n[2] Setting up Python venv at {VENV_DIR}...")
    if sys.platform == "win32":
        python_bin = VENV_DIR / "Scripts" / "python.exe"
        pip_bin = VENV_DIR / "Scripts" / "pip.exe"
    else:
        python_bin = VENV_DIR / "bin" / "python"
        pip_bin = VENV_DIR / "bin" / "pip"

    if not python_bin.exists():
        run([sys.executable, "-m", "venv", str(VENV_DIR)])
        print("  Created venv")
    else:
        print("  Venv already exists")

    pip = str(pip_bin)

    # 3. Install requirements
    print("\n[3] Installing Python packages...")
    run([pip, "install", "--upgrade", "pip", "-q"])
    run([pip, "install", "-r", str(PROJECT_ROOT / "requirements.txt"), "-q"])
    print("  All packages installed")

    # 4. Verify Ollama
    print("\n[4] Checking Ollama...")
    if shutil.which("ollama"):
        result = run(["ollama", "--version"], capture_output=True, text=True, check=False)
        print(f"  Ollama: {result.stdout.strip()}")
    else:
        print("  WARNING: ollama not found in PATH")

    # 5. Redis via Podman
    print("\n[5] Setting up Redis via Podman...")
    result = run(
        ["podman", "container", "inspect", "redis-agent"],
        capture_output=True, text=True, check=False
    )
    if result.returncode == 0:
        print("  Redis container 'redis-agent' already exists")
    else:
        print("  Creating Redis container...")
        run([
            "podman", "run", "-d",
            "--name", "redis-agent",
            "--restart", "always",
            "-p", "6379:6379",
            "docker.io/library/redis:7-alpine",
            "redis-server", "--save", "60", "1", "--loglevel", "warning"
        ])
        print("  Redis container created")

    # Ensure it's running
    run(["podman", "start", "redis-agent"], check=False)
    print("  Redis started")

    # 6. Create Ollama systemd user service
    print("\n[6] Setting up Ollama systemd service with Vulkan...")
    service_dir = Path.home() / ".config" / "systemd" / "user"
    service_dir.mkdir(parents=True, exist_ok=True)
    service_file = service_dir / "ollama.service"

    service_content = """[Unit]
Description=Ollama LLM Server (Vulkan/ROCm)
After=default.target

[Service]
Type=simple
Environment=OLLAMA_VULKAN=1
Environment=HSA_OVERRIDE_GFX_VERSION=11.5.0
Environment=OLLAMA_NUM_GPU=999
Environment=OLLAMA_NUM_PARALLEL=4
Environment=OLLAMA_MAX_LOADED_MODELS=3
Environment=OLLAMA_FLASH_ATTENTION=true
Environment=OLLAMA_KEEP_ALIVE=10m
ExecStart=/usr/local/bin/ollama serve
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
"""
    service_file.write_text(service_content)
    print(f"  Service file: {service_file}")

    run(["systemctl", "--user", "daemon-reload"], check=False)
    run(["systemctl", "--user", "enable", "ollama"], check=False)
    run(["systemctl", "--user", "restart", "ollama"], check=False)
    print("  Ollama service enabled and started")

    # 7. Create Redis systemd service (using podman)
    print("\n[7] Setting up Redis systemd service...")
    redis_service = service_dir / "redis-agent.service"
    redis_service.write_text("""[Unit]
Description=Redis (Podman) for Agent System
After=default.target

[Service]
Type=forking
ExecStart=/usr/bin/podman start redis-agent
ExecStop=/usr/bin/podman stop redis-agent
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
""")
    run(["systemctl", "--user", "daemon-reload"], check=False)
    run(["systemctl", "--user", "enable", "redis-agent"], check=False)
    print("  Redis service enabled")

    print("\n" + "=" * 60)
    print("  Setup complete!")
    print("=" * 60)
    print(f"""
Next steps:
  1. Pull models:
       python scripts/pull_models.py

  2. Start the system:
       ./start

  3. Open the web UI:
       http://localhost:8000

   Or use the CLI:
        source venv/bin/activate
        python main.py chat "your task here"
""")


if __name__ == "__main__":
    main()
