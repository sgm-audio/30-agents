#!/usr/bin/env bash
# ============================================================
# run.sh — Start the 30-Agent Cognitive System in tmux
# Usage: ./run.sh [--no-tmux]
# ============================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$SCRIPT_DIR/venv"
SESSION="agents30"

# ── Color output ─────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; }

# ── Check venv ────────────────────────────────────────────────
if [[ ! -f "$VENV/bin/python" ]]; then
    error "Virtual environment not found. Run setup first:"
    echo "  python scripts/setup.py"
    exit 1
fi

# ── Ensure Ollama service is running ─────────────────────────
info "Checking Ollama service on port 11435..."
if ! curl -sf http://127.0.0.1:11435/ > /dev/null 2>&1; then
    warn "Ollama not responding yet, starting manually..."
    OLLAMA_HOST=127.0.0.1:11435 OLLAMA_MODELS=/media/sgm/linux/home/SGM/.ollama/models \
    OLLAMA_VULKAN=1 HSA_OVERRIDE_GFX_VERSION=11.5.0 \
    OLLAMA_NUM_GPU=999 OLLAMA_NUM_PARALLEL=4 \
    ollama serve > "$SCRIPT_DIR/logs/ollama.log" 2>&1 &
    sleep 3
fi
info "Ollama: OK"

# ── Ensure Redis is running ───────────────────────────────────
info "Checking Redis..."
if redis-cli ping >/dev/null 2>&1; then
    info "Redis: OK"
else
    # Prefer local redis-server, then docker/podman container
    if command -v redis-server >/dev/null 2>&1; then
        if command -v service >/dev/null 2>&1; then
            sudo service redis-server start >/dev/null 2>&1 || true
        fi
        redis-server --daemonize yes --port 6379 >/dev/null 2>&1 || true
    elif command -v docker >/dev/null 2>&1; then
        docker start redis-agent >/dev/null 2>&1 || \
            docker run -d --name redis-agent --restart unless-stopped -p 6379:6379 \
            redis:7-alpine >/dev/null 2>&1 || true
    elif command -v podman >/dev/null 2>&1; then
        podman start redis-agent >/dev/null 2>&1 || \
            podman run -d --name redis-agent --restart always -p 6379:6379 \
            docker.io/library/redis:7-alpine \
            redis-server --save 60 1 --loglevel warning >/dev/null 2>&1 || true
    fi

    for i in {1..5}; do
        if redis-cli ping >/dev/null 2>&1; then
            info "Redis: OK"
            break
        fi
        sleep 1
    done
fi

# ── No-tmux mode ─────────────────────────────────────────────
if [[ "${1:-}" == "--no-tmux" ]]; then
    info "Starting agent server (no-tmux mode)..."
    cd "$SCRIPT_DIR"
    exec "$VENV/bin/python" main.py serve
fi

# ── tmux mode ─────────────────────────────────────────────────
info "Starting in tmux session: $SESSION"
tmux new-session -d -s "$SESSION" -n "agents" 2>/dev/null || \
    tmux new-window -t "$SESSION" -n "agents" 2>/dev/null || true

# Kill existing agent process if running
tmux send-keys -t "$SESSION:agents" "" Enter 2>/dev/null || true

# Start the agent server
tmux send-keys -t "$SESSION:agents" \
    "cd $SCRIPT_DIR && $VENV/bin/python main.py serve 2>&1 | tee logs/server.log" Enter

# Create a second pane for logs/monitoring
tmux split-window -t "$SESSION:agents" -v 2>/dev/null || true
tmux send-keys -t "$SESSION:agents" \
    "tail -f $SCRIPT_DIR/logs/agents.log" Enter 2>/dev/null || true

# Create third window for CLI access
tmux new-window -t "$SESSION" -n "cli" 2>/dev/null || true
tmux send-keys -t "$SESSION:cli" \
    "cd $SCRIPT_DIR && source $VENV/bin/activate && echo 'CLI ready. Try: python main.py chat \"hello\"'" Enter

echo ""
echo -e "${GREEN}════════════════════════════════════════════${NC}"
echo -e "${GREEN}  30-Agent System started!${NC}"
echo -e "${GREEN}════════════════════════════════════════════${NC}"
echo ""
echo -e "  Web UI:    ${YELLOW}http://localhost:8000${NC}"
echo -e "  API Docs:  ${YELLOW}http://localhost:8000/docs${NC}"
echo -e "  tmux:      ${YELLOW}tmux attach -t $SESSION${NC}"
echo ""
echo -e "  CLI:       ${YELLOW}$VENV/bin/python main.py chat \"your task\"${NC}"
echo -e "  Health:    ${YELLOW}$VENV/bin/python main.py health${NC}"
echo ""

# Auto-attach if running interactively
if [[ -t 0 ]]; then
    tmux attach-session -t "$SESSION"
fi
