#!/usr/bin/env bash
# ============================================================
# status.sh — Show the current state of the 30-Agent system
# ============================================================
set -euo pipefail

GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

check() {
    local name="$1"; local cmd="$2"
    if eval "$cmd" > /dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} $name"
        return 0
    else
        echo -e "  ${RED}✗${NC} $name"
        return 1
    fi
}

echo ""
echo -e "${CYAN}══════════════════════════════════════════════${NC}"
echo -e "${CYAN}   30-Agent Cognitive System — Status         ${NC}"
echo -e "${CYAN}══════════════════════════════════════════════${NC}"
echo ""

echo -e "${YELLOW}Services:${NC}"
check "Ollama"  "curl -sf http://127.0.0.1:11434/"
check "Redis"   "podman exec redis-agent redis-cli ping"
check "API"     "curl -sf http://127.0.0.1:8000/api/health"

echo ""
echo -e "${YELLOW}Models:${NC}"
MODELS_JSON=$(curl -sf http://127.0.0.1:11434/api/tags 2>/dev/null || echo '{"models":[]}')
if echo "$MODELS_JSON" | python3 -c "
import sys, json
d = json.load(sys.stdin)
models = d.get('models', [])
if not models:
    print('  (no models pulled yet)')
else:
    for m in models:
        size = m.get('size', 0)
        size_gb = size / 1e9
        print(f'  ✓ {m[\"name\"]:40s} {size_gb:.1f} GB')
" 2>/dev/null; then true; fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CHECKPOINT_FILE="$PROJECT_DIR/data/pull_checkpoint.json"

echo ""
echo -e "${YELLOW}Pull Progress:${NC}"
if [[ -f "$CHECKPOINT_FILE" ]]; then
    python3 -c "
import json
data = json.load(open('$CHECKPOINT_FILE'))
models = ['nomic-embed-text', 'hf.co/evalengine/unbound-e2b-gguf:Q4_K_M', 'minicpm-v:8b', 'huihui_ai/gemma-4-abliterated:e4b-q4_K']
for m in models:
    status = data.get(m, 'pending')
    attempts = data.get(f'{m}_attempts', 0)
    icon = '✓' if status == 'done' else '…' if attempts > 0 else '○'
    print(f'  {icon} {m:40s} {status} (attempts: {attempts})')
"
else
    echo "  (no checkpoint yet)"
fi

echo ""
echo -e "${YELLOW}System Resources:${NC}"
python3 -c "
import subprocess
# RAM
with open('/proc/meminfo') as f:
    lines = {l.split(':')[0]: l.split(':')[1].strip() for l in f if ':' in l}
total = int(lines.get('MemTotal','0 kB').split()[0]) / 1024 / 1024
avail = int(lines.get('MemAvailable','0 kB').split()[0]) / 1024 / 1024
print(f'  RAM: {avail:.1f}/{total:.1f} GB available')

# Swap
swap_total = int(lines.get('SwapTotal','0 kB').split()[0]) / 1024 / 1024
swap_free = int(lines.get('SwapFree','0 kB').split()[0]) / 1024 / 1024
swap_used = swap_total - swap_free
print(f'  Swap: {swap_used:.1f}/{swap_total:.1f} GB used')

# Swappiness
with open('/proc/sys/vm/swappiness') as f:
    print(f'  Swappiness: {f.read().strip()}')
"

echo ""
tmux ls 2>/dev/null | grep -E "modelpull|agents30" | sed 's/^/  tmux: /' || true
echo ""
