#!/bin/bash
# post-merge.sh — runs automatically after a task merge.
# This is a pure Python project; install Python dependencies only.
set -e

echo "[post-merge] Installing Python dependencies…"
pip install -r webhook_server/requirements.txt --quiet
echo "[post-merge] Done."
