"""
30 Agents — Windows desktop launcher.

Double-click / run this to start the stack and open the chat UI.
Build a real .exe on Windows with Build-Exe.bat.
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

# Project root = parent of launcher/
ROOT = Path(__file__).resolve().parent.parent
if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
    # When frozen as onedir/onefile next to project, allow override
    if (ROOT / "main.py").exists():
        pass
    elif (ROOT.parent / "main.py").exists():
        ROOT = ROOT.parent

API = "http://127.0.0.1:8000"
HEALTH = f"{API}/api/health"


def _venv_python() -> Path:
    if sys.platform == "win32":
        return ROOT / "venv" / "Scripts" / "python.exe"
    return ROOT / "venv" / "bin" / "python"


def _ensure_venv() -> Path:
    py = _venv_python()
    if py.exists():
        return py
    base = sys.executable
    subprocess.check_call([base, "-m", "venv", str(ROOT / "venv")], cwd=str(ROOT))
    pip = ROOT / "venv" / ("Scripts" if sys.platform == "win32" else "bin") / "pip"
    subprocess.check_call([str(pip), "install", "-U", "pip"], cwd=str(ROOT))
    subprocess.check_call(
        [str(pip), "install", "-r", str(ROOT / "requirements.txt")],
        cwd=str(ROOT),
    )
    return _venv_python()


def port_open(host: str, port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def api_health() -> dict | None:
    try:
        with urllib.request.urlopen(HEALTH, timeout=2) as resp:
            import json

            return json.loads(resp.read().decode())
    except Exception:
        return None


def ensure_redis(log) -> None:
    if port_open("127.0.0.1", 6379):
        log("Redis is up")
        return
    log("Starting Redis…")
    if sys.platform == "win32":
        # Docker Desktop on Windows
        subprocess.run(
            ["docker", "start", "redis-agent"],
            cwd=str(ROOT),
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        r = subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                "redis-agent",
                "--restart",
                "unless-stopped",
                "-p",
                "6379:6379",
                "redis:7-alpine",
            ],
            cwd=str(ROOT),
            capture_output=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if r.returncode == 0:
            log("Redis container started")
        elif port_open("127.0.0.1", 6379):
            log("Redis is up")
        else:
            log("Redis not available (install Docker Desktop or Redis)")
    else:
        subprocess.run(["redis-server", "--daemonize", "yes"], capture_output=True)


class LauncherApp:
    def __init__(self):
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.server_proc: subprocess.Popen | None = None
        self.root = tk.Tk()
        self.root.title("30 Agents")
        self.root.geometry("520x560")
        self.root.minsize(480, 520)
        self.root.configure(bg="#0c1210")

        # Accent: copper on deep ink (not purple / not cream-terracotta cliché)
        self.colors = {
            "bg": "#0c1210",
            "panel": "#141c18",
            "text": "#e8efe9",
            "muted": "#8a9a90",
            "accent": "#d4a574",
            "good": "#3ecf8e",
            "bad": "#e85d5d",
            "warn": "#e6b84d",
            "btn": "#1a2820",
            "btn_fg": "#e8efe9",
            "primary": "#d4a574",
            "primary_fg": "#0c1210",
        }

        self._build(ttk)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self._tick()

    def _build(self, ttk):
        c = self.colors
        pad = {"padx": 28, "pady": 8}

        brand = self.tk.Label(
            self.root,
            text="30 AGENTS",
            font=("Segoe UI Semibold", 28),
            fg=c["accent"],
            bg=c["bg"],
        )
        brand.pack(anchor="w", padx=28, pady=(28, 0))

        sub = self.tk.Label(
            self.root,
            text="Your local agent team. One click to chat.",
            font=("Segoe UI", 11),
            fg=c["muted"],
            bg=c["bg"],
        )
        sub.pack(anchor="w", padx=28, pady=(4, 16))

        self.status_var = self.tk.StringVar(value="Checking…")
        self.status_lbl = self.tk.Label(
            self.root,
            textvariable=self.status_var,
            font=("Segoe UI Semibold", 16),
            fg=c["text"],
            bg=c["bg"],
        )
        self.status_lbl.pack(anchor="w", **pad)

        # Service row
        row = self.tk.Frame(self.root, bg=c["bg"])
        row.pack(fill="x", padx=28, pady=8)
        self.dot_api = self._service_chip(row, "API")
        self.dot_redis = self._service_chip(row, "Redis")
        self.dot_ollama = self._service_chip(row, "Ollama")

        # Primary CTA
        self.open_btn = self.tk.Button(
            self.root,
            text="Open Chat",
            font=("Segoe UI Semibold", 13),
            bg=c["primary"],
            fg=c["primary_fg"],
            activebackground="#e0b88a",
            activeforeground=c["primary_fg"],
            relief="flat",
            cursor="hand2",
            command=self.open_chat,
            height=2,
        )
        self.open_btn.pack(fill="x", padx=28, pady=(18, 8))

        btn_row = self.tk.Frame(self.root, bg=c["bg"])
        btn_row.pack(fill="x", padx=28, pady=4)

        self.start_btn = self.tk.Button(
            btn_row,
            text="Start System",
            font=("Segoe UI", 10),
            bg=c["btn"],
            fg=c["btn_fg"],
            activebackground="#24352c",
            relief="flat",
            cursor="hand2",
            command=lambda: threading.Thread(target=self.start_system, daemon=True).start(),
        )
        self.start_btn.pack(side="left", expand=True, fill="x", padx=(0, 6))

        self.stop_btn = self.tk.Button(
            btn_row,
            text="Stop",
            font=("Segoe UI", 10),
            bg=c["btn"],
            fg=c["btn_fg"],
            activebackground="#24352c",
            relief="flat",
            cursor="hand2",
            command=lambda: threading.Thread(target=self.stop_system, daemon=True).start(),
        )
        self.stop_btn.pack(side="left", expand=True, fill="x", padx=(6, 0))

        log_lbl = self.tk.Label(
            self.root, text="Activity", font=("Segoe UI", 9), fg=c["muted"], bg=c["bg"]
        )
        log_lbl.pack(anchor="w", padx=28, pady=(16, 4))

        self.log = self.tk.Text(
            self.root,
            height=12,
            bg=c["panel"],
            fg=c["text"],
            insertbackground=c["text"],
            relief="flat",
            font=("Consolas", 9),
            wrap="word",
        )
        self.log.pack(fill="both", expand=True, padx=28, pady=(0, 24))
        self.log.configure(state="disabled")

        self._log("Ready when you are. Hit Start System, then Open Chat.")

    def _service_chip(self, parent, name: str):
        c = self.colors
        frame = self.tk.Frame(parent, bg=c["panel"], padx=10, pady=6)
        frame.pack(side="left", padx=(0, 8))
        dot = self.tk.Label(frame, text="●", fg=c["muted"], bg=c["panel"], font=("Segoe UI", 10))
        dot.pack(side="left")
        lbl = self.tk.Label(frame, text=f"  {name}", fg=c["text"], bg=c["panel"], font=("Segoe UI", 9))
        lbl.pack(side="left")
        return dot

    def _set_dot(self, dot, ok: bool | None):
        c = self.colors
        if ok is True:
            dot.configure(fg=c["good"])
        elif ok is False:
            dot.configure(fg=c["bad"])
        else:
            dot.configure(fg=c["muted"])

    def _log(self, msg: str):
        self.log.configure(state="normal")
        self.log.insert("end", f"{msg}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _tick(self):
        health = api_health()
        redis_ok = port_open("127.0.0.1", 6379)
        if health:
            self.status_var.set("Online — chat is ready")
            self.status_lbl.configure(fg=self.colors["good"])
            self._set_dot(self.dot_api, True)
            self._set_dot(self.dot_redis, bool(health.get("redis")))
            self._set_dot(self.dot_ollama, bool(health.get("ollama")))
            if not health.get("ollama"):
                self.status_var.set("Online — Ollama offline (limited answers)")
                self.status_lbl.configure(fg=self.colors["warn"])
        else:
            self.status_var.set("Offline — press Start System")
            self.status_lbl.configure(fg=self.colors["bad"])
            self._set_dot(self.dot_api, False)
            self._set_dot(self.dot_redis, redis_ok)
            self._set_dot(self.dot_ollama, None)
        self.root.after(2000, self._tick)

    def open_chat(self):
        if not api_health():
            self._log("System not running — starting it first…")
            threading.Thread(target=self._start_then_open, daemon=True).start()
            return
        webbrowser.open(f"{API}/")
        self._log("Opened chat UI in your browser")

    def _start_then_open(self):
        self.start_system()
        for _ in range(40):
            if api_health():
                self.root.after(0, lambda: webbrowser.open(f"{API}/"))
                self.root.after(0, lambda: self._log("Opened chat UI in your browser"))
                return
            time.sleep(0.5)
        self.root.after(0, lambda: self._log("Failed to start — check the log above"))

    def start_system(self):
        try:
            self.root.after(0, lambda: self._log("Preparing environment…"))
            py = _ensure_venv()
            (ROOT / "logs").mkdir(exist_ok=True)
            (ROOT / "data" / "chroma").mkdir(parents=True, exist_ok=True)
            ensure_redis(lambda m: self.root.after(0, lambda: self._log(m)))

            if api_health():
                self.root.after(0, lambda: self._log("Already running"))
                return

            self.root.after(0, lambda: self._log("Starting API server…"))
            creation = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
            log_f = open(ROOT / "logs" / "server.log", "a", encoding="utf-8")
            self.server_proc = subprocess.Popen(
                [str(py), str(ROOT / "main.py"), "serve"],
                cwd=str(ROOT),
                stdout=log_f,
                stderr=subprocess.STDOUT,
                creationflags=creation,
            )
            for _ in range(45):
                if api_health():
                    self.root.after(0, lambda: self._log("API is ready at http://127.0.0.1:8000"))
                    return
                time.sleep(1)
            self.root.after(0, lambda: self._log("Timed out waiting for API — see logs/server.log"))
        except Exception as e:
            self.root.after(0, lambda: self._log(f"Error: {e}"))

    def stop_system(self):
        self._log("Stopping…")
        if self.server_proc and self.server_proc.poll() is None:
            self.server_proc.terminate()
            try:
                self.server_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.server_proc.kill()
            self.server_proc = None

        if sys.platform == "win32":
            # Kill whatever holds :8000
            try:
                out = subprocess.check_output("netstat -ano", shell=True, text=True)
                for line in out.splitlines():
                    if ":8000" in line and "LISTENING" in line:
                        pid = line.split()[-1]
                        subprocess.run(
                            ["taskkill", "/PID", pid, "/F"],
                            capture_output=True,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                        )
            except Exception:
                pass
        else:
            subprocess.run(["fuser", "-k", "8000/tcp"], capture_output=True)

        self._log("Stopped")

    def _on_close(self):
        # Leave server running so chat keeps working after closing launcher
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    # Auto-start if launched with --start
    app = LauncherApp()
    if "--start" in sys.argv:
        threading.Thread(target=app.start_system, daemon=True).start()
    if "--open" in sys.argv:
        threading.Thread(target=app._start_then_open, daemon=True).start()
    app.run()


if __name__ == "__main__":
    main()
