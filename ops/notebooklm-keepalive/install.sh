#!/bin/bash
# Restore the NotebookLM keepalive system on Muse's VM.
# Run from this directory (ops/notebooklm-keepalive in the repo) as root.
set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
DEST=/home/hatch/nblm-vm
mkdir -p "$DEST/systemd" /home/hatch/.notebooklm-kenta/profiles/default
cp "$SRC/refresh.sh" "$SRC/sync_secret.py" "$DEST/"
cp "$SRC/systemd/"* "$DEST/systemd/"
chmod +x "$DEST/refresh.sh"
# venv with notebooklm-py + pynacl (skip if already present)
if [ ! -x "$DEST/.venv/bin/notebooklm" ]; then
  "$HOME/.local/bin/uv" venv --python 3.12 "$DEST/.venv"
  "$HOME/.local/bin/uv" pip install --python "$DEST/.venv/bin/python" \
    "notebooklm-py[browser,impersonate,headless]==0.8.5" pynacl
fi
cp "$DEST/systemd/"*.service "$DEST/systemd/"*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now nblm-refresh.timer nblm-secret-sync.timer
systemctl start nblm-refresh.service nblm-secret-sync.service
echo "Installed. Check: systemctl list-timers | grep nblm ; tail ~/nblm-vm/refresh.log"
echo "NOTE: ~/.notebooklm-kenta/profiles/default/storage_state.json must exist"
echo "(see README.md recovery steps) or auth refresh will fail."
