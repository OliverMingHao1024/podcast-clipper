#!/bin/bash
# Double-click (macOS) or run in a terminal (Linux) to open the podclip browser UI.
# Everything runs on this computer.
cd "$(dirname "$0")" || exit 1

# Homebrew (Apple Silicon / Intel) and the usual claude install spots; appended so the user's own PATH wins.
export PATH="$PATH:/opt/homebrew/bin:/usr/local/bin:$HOME/.local/bin:$HOME/.claude/local"

# The system python3 on macOS can be 3.9; look for a newer one.
PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  echo "Python 3.10 or newer is required."
  echo "macOS: install it from https://www.python.org/downloads/ (or: brew install python), then run this again."
  read -r -p "Press Enter to close..." _
  exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "First run: creating a private Python environment and downloading components from PyPI."
  echo "This happens once and can take a few minutes..."
  "$PY" -m venv .venv && .venv/bin/python -m pip install -q -e ".[asr]" || {
    echo "Setup failed. See the messages above."
    read -r -p "Press Enter to close..." _
    exit 1
  }
fi

# Optional speaker labels: older private environments get the extra component once. A failed install only turns that
# feature off and leaves a marker so it is not retried on every start; delete .venv/.no-speakers to try again.
if [ ! -f .venv/.no-speakers ] && ! .venv/bin/python -c "import sherpa_onnx, numpy" >/dev/null 2>&1; then
  echo "Installing the optional speaker-labelling component, one time..."
  if ! .venv/bin/python -m pip install -q -e ".[speakers]"; then
    echo "Speaker labels will be unavailable because the install failed. Delete .venv/.no-speakers to try again."
    : > .venv/.no-speakers
  fi
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "WARNING: ffmpeg was not found. Install it first (macOS: brew install ffmpeg), otherwise cutting will fail."
fi

.venv/bin/python -m podclip.cli web
read -r -p "Press Enter to close..." _
