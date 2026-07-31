#!/usr/bin/env bash
# RFHound installer — creates a virtual environment and installs RFHound.
#
#   ./install.sh          # normal install
#   ./install.sh --dev    # also install test/lint tools (pytest, flake8)
#
# It never installs system packages for you; it prints the exact commands for
# the optional SDR decoder tools so you stay in control.
set -euo pipefail

DEV=0
[ "${1:-}" = "--dev" ] && DEV=1

PY="${PYTHON:-python3}"
VENV=".venv"

say(){ printf '\033[36m›\033[0m %s\n' "$*"; }
ok(){  printf '\033[32m✓\033[0m %s\n' "$*"; }
warn(){ printf '\033[33m!\033[0m %s\n' "$*"; }

# 1) Python version check (need 3.9+)
if ! command -v "$PY" >/dev/null 2>&1; then
  warn "python3 not found. Install Python 3.9+ first."; exit 1
fi
VER="$("$PY" -c 'import sys;print("%d.%d"%sys.version_info[:2])')"
say "Using $PY (Python $VER)"
"$PY" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] >= (3,9) else 1)' || {
  warn "Python 3.9+ is required (found $VER)."; exit 1; }

# 2) Virtual environment
if [ ! -d "$VENV" ]; then
  say "Creating virtual environment in $VENV"
  "$PY" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
python -m pip install --upgrade pip >/dev/null
ok "Virtual environment ready"

# 3) Install RFHound
if [ "$DEV" = "1" ]; then
  say "Installing RFHound + dev tools"
  pip install -e ".[dev]"
else
  say "Installing RFHound"
  pip install -e .
fi
ok "RFHound installed"

# 4) Verify
echo
say "Verifying install:"
rfhound --version
echo

# 5) Optional SDR decoder tools (hints only)
say "Optional SDR tools RFHound can drive (install what you need):"
if [ "$(uname)" = "Darwin" ]; then
  echo "    brew install hackrf rtl_433 multimon-ng"
else
  echo "    sudo apt install hackrf rtl-433 multimon-ng soapysdr-module-hackrf"
fi
echo "    (dump1090-fa, AIS-catcher, gnuradio… — see docs/USAGE.md)"
echo

ok "Done. Next steps:"
echo "    source $VENV/bin/activate      # each new shell"
echo "    rfhound setup                  # one-time setup summary"
echo "    rfhound --simulate recon       # try it with no hardware"
echo "    rfhound --simulate web --open  # open the dashboard"
echo "    See docs/TUTORIAL.md for the full walkthrough."
