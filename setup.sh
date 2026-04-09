#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}[maintainer]${NC} $*"; }
success() { echo -e "${GREEN}[maintainer]${NC} $*"; }
warn()    { echo -e "${YELLOW}[maintainer]${NC} $*"; }
die()     { echo -e "${RED}[maintainer] ERROR:${NC} $*" >&2; exit 1; }

echo ""
echo "  Maintainer Setup"
echo "  ================"
echo ""

# ── Python ────────────────────────────────────────────────────────────────────
command -v python3 &>/dev/null || die "Python 3 is required but not found."
PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
info "Python $PY_VER found."

# ── Venv + deps ───────────────────────────────────────────────────────────────
VENV_DIR="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    info "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
info "Installing dependencies..."
pip install --quiet psutil

# ── Config prompts ────────────────────────────────────────────────────────────
echo ""
info "Configuration  (press Enter to accept default)"
echo ""

read -r -p "  Service name to monitor [openclaw]: " INPUT_SERVICE
export SERVICE_NAME="${INPUT_SERVICE:-openclaw}"

read -r -p "  Disk path to monitor [/]: " INPUT_DISK
export DISK_PATH="${INPUT_DISK:-/}"

read -r -p "  Enable GPU monitoring? (NVIDIA only) [y/N]: " INPUT_GPU

echo ""
info "Sentinel probe  (leave blank to skip)"
read -r -p "  Sentinel health URL  [e.g. http://127.0.0.1:8000/healthz]: " INPUT_HEALTH
export HEALTH_URL="${INPUT_HEALTH:-}"
read -r -p "  Prometheus metrics URL  [e.g. http://127.0.0.1:9090/metrics]: " INPUT_PROM
export PROM_URL="${INPUT_PROM:-}"

echo ""
info "Alert webhook  (leave blank to skip)"
read -r -s -p "  Webhook URL: " INPUT_WEBHOOK
echo ""
export WEBHOOK_URL="${INPUT_WEBHOOK:-}"

echo ""
read -r -p "  Enable live auto-restart remediation? (default: dry-run only) [y/N]: " INPUT_REMED
if [[ "${INPUT_REMED,,}" == "y" ]]; then
    export DRY_RUN="false"
    warn "Live remediation enabled — Maintainer will restart $SERVICE_NAME on critical failure."
else
    export DRY_RUN="true"
    info "Dry-run mode: restarts will be logged but not executed."
fi

# Build enabled_modules list
MODULES_LIST='"process"'
[[ "${INPUT_GPU,,}" == "y" ]] && MODULES_LIST+=',"gpu"'
MODULES_LIST+=',"memory","disk","config_drift","sentinel_probe"'
export MODULES="[$MODULES_LIST]"

# ── Write config.json via Python (safe handling of special chars) ─────────────
info "Writing config.json..."
python3 - <<'PYEOF'
import json, os, pathlib

config_path = pathlib.Path("config.json")
with open(config_path) as f:
    config = json.load(f)

config["enabled_modules"]                  = json.loads(os.environ["MODULES"])
config["process"]["service_name"]          = os.environ["SERVICE_NAME"]
config["disk"]["path"]                     = os.environ["DISK_PATH"]
config["sentinel_probe"]["health_url"]     = os.environ.get("HEALTH_URL", "")
config["sentinel_probe"]["prom_url"]       = os.environ.get("PROM_URL", "")
config["alert_sink"]["webhook_url"]        = os.environ.get("WEBHOOK_URL", "")
config["remediation"]["dry_run"]           = os.environ["DRY_RUN"] == "true"

with open(config_path, "w") as f:
    json.dump(config, f, indent=2)
print("  config.json updated.")
PYEOF

# ── Validate config ───────────────────────────────────────────────────────────
info "Validating config..."
python3 - <<'PYEOF'
import importlib.util, pathlib, sys

spec = importlib.util.spec_from_file_location("maintainer_main", pathlib.Path("main.py"))
mod  = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
try:
    mod.load_config()
    print("  Config OK.")
except Exception as exc:
    print(f"  Config error: {exc}", file=sys.stderr)
    sys.exit(1)
PYEOF

# ── Launch options ────────────────────────────────────────────────────────────
echo ""
echo "  How would you like to run Maintainer?"
echo "  1) Start now (foreground)"
echo "  2) Install as systemd service"
echo "  3) Exit (run manually later)"
echo ""
read -r -p "  Choice [1]: " CHOICE
CHOICE="${CHOICE:-1}"

case "$CHOICE" in
  1)
    echo ""
    success "Starting Maintainer (Ctrl+C to stop)..."
    echo ""
    python3 main.py
    ;;

  2)
    UNIT_DST="/etc/systemd/system/maintainer.service"
    if [ "$EUID" -ne 0 ]; then
        warn "Systemd install requires root. Re-run with:"
        echo ""
        echo "  sudo bash setup.sh"
        echo ""
        echo "  Or install manually:"
        echo "    sudo install -D -m 0644 deploy/maintainer.service $UNIT_DST"
        echo "    # Update WorkingDirectory, ExecStart, User, Group in the unit file"
        echo "    sudo systemctl daemon-reload && sudo systemctl enable --now maintainer.service"
        echo ""
    else
        REAL_USER="${SUDO_USER:-root}"
        REAL_GROUP="$(id -gn "$REAL_USER" 2>/dev/null || echo "$REAL_USER")"
        cp deploy/maintainer.service "$UNIT_DST"
        sed -i "s|WorkingDirectory=.*|WorkingDirectory=$SCRIPT_DIR|"             "$UNIT_DST"
        sed -i "s|ExecStart=.*|ExecStart=$VENV_DIR/bin/python3 $SCRIPT_DIR/main.py|" "$UNIT_DST"
        sed -i "s|User=maintainer|User=$REAL_USER|"                              "$UNIT_DST"
        sed -i "s|Group=maintainer|Group=$REAL_GROUP|"                           "$UNIT_DST"
        systemctl daemon-reload
        systemctl enable --now maintainer.service
        echo ""
        success "Maintainer installed and started."
        echo ""
        systemctl status maintainer.service --no-pager
    fi
    ;;

  3)
    echo ""
    success "Setup complete. To start manually:"
    echo ""
    echo "  source .venv/bin/activate && python3 main.py"
    echo ""
    ;;

  *)
    warn "Unknown choice. To start: source .venv/bin/activate && python3 main.py"
    ;;
esac
