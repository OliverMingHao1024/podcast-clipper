#!/bin/bash
# Double-click (macOS) or run in a terminal (Linux) to open the podclip browser UI.
# Everything runs on this computer.
cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3.10 or newer is required."
  echo "macOS: install it from https://www.python.org/downloads/ (or: brew install python), then run this again."
  read -r -p "Press Enter to close..." _
  exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "First run: creating a private Python environment and downloading components from PyPI."
  echo "This happens once and can take a few minutes..."
  python3 -m venv .venv && .venv/bin/python -m pip install -q -e ".[asr]" || {
    echo "Setup failed. See the messages above."
    read -r -p "Press Enter to close..." _
    exit 1
  }
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "WARNING: ffmpeg was not found. Install it first (macOS: brew install ffmpeg), otherwise cutting will fail."
fi

.venv/bin/python -m podclip.cli web
read -r -p "Press Enter to close..." _
