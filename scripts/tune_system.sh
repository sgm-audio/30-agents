#!/usr/bin/env bash
# ============================================================
# tune_system.sh — Performance tuning for the 30-agent system
# Adjusts CPU governor, swappiness, and GPU settings
# Safe to re-run; all changes survive only until next boot
# (add to systemd for persistence)
# ============================================================
set -euo pipefail

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info() { echo -e "${GREEN}[TUNE]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }

# ── 1. CPU Governor → performance ────────────────────────────
info "Setting CPU governor to 'performance'..."
for cpu in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
    if [[ -w "$cpu" ]]; then
        echo performance > "$cpu" 2>/dev/null || true
    fi
done
# Check what we have
GOV=$(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo "unknown")
info "CPU governor: $GOV"

# ── 2. Swappiness ─────────────────────────────────────────────
# Reduce swap usage (more RAM for models)
CURRENT_SWAP=$(cat /proc/sys/vm/swappiness)
info "Current swappiness: $CURRENT_SWAP → setting to 10"
sudo sysctl -w vm.swappiness=10 2>/dev/null || \
    echo 10 | sudo tee /proc/sys/vm/swappiness > /dev/null 2>/dev/null || \
    warn "Could not set swappiness (need sudo)"

# ── 3. Huge pages for model weights ──────────────────────────
info "Enabling transparent huge pages (madvise)..."
echo madvise | sudo tee /sys/kernel/mm/transparent_hugepage/enabled > /dev/null 2>/dev/null || \
    warn "Could not set hugepages (need sudo)"

# ── 4. AMD GPU power profile ─────────────────────────────────
info "Setting AMD GPU power profile to high performance..."
# For RDNA3.5 iGPU
GPU_PERF=/sys/class/drm/card1/device/power_dpm_force_performance_level
if [[ -w "$GPU_PERF" ]]; then
    echo high > "$GPU_PERF"
    info "GPU DPM: $(cat $GPU_PERF)"
elif [[ -f "$GPU_PERF" ]]; then
    echo high | sudo tee "$GPU_PERF" > /dev/null 2>/dev/null || warn "Could not set GPU DPM (need sudo)"
else
    warn "GPU DPM control not found (skipping)"
fi

# ── 5. File descriptor limits ────────────────────────────────
info "Setting file descriptor limits..."
ulimit -n 65536 2>/dev/null || warn "Could not set ulimit"

# ── 6. OOM score for Ollama ──────────────────────────────────
OLLAMA_PID=$(pgrep -f "ollama serve" 2>/dev/null | head -1 || echo "")
if [[ -n "$OLLAMA_PID" ]]; then
    echo -500 | sudo tee /proc/"$OLLAMA_PID"/oom_score_adj > /dev/null 2>/dev/null || true
    info "OOM protection applied to Ollama PID $OLLAMA_PID"
fi

# ── 7. Memory lock limits (for model loading) ────────────────
info "Checking memlock..."
MEMLOCK=$(ulimit -l 2>/dev/null || echo "unknown")
info "Memlock limit: $MEMLOCK KB"

echo ""
echo -e "${GREEN}System tuning complete.${NC}"
echo "  CPU Governor: $(cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo 'unknown')"
echo "  Swappiness:   $(cat /proc/sys/vm/swappiness)"
echo "  Hugepages:    $(cat /sys/kernel/mm/transparent_hugepage/enabled 2>/dev/null | grep -o '\[.*\]' || echo 'unknown')"
