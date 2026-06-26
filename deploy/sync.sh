#!/usr/bin/env bash
# Mirror the fmradiod source from this Mac repo to the Pi.
#
#   deploy/sync.sh            one-shot rsync
#   deploy/sync.sh --watch    continuous (needs `brew install fswatch`)
#
# Canonical source is this repo; the Pi at /root/fmradio is a mirror. Runtime
# state (state.json) and the Pi venv (.venv) are excluded so they survive syncs.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
DEST="root@fmradio.local:/root/fmradio"
SSH='ssh -o BatchMode=yes'

do_sync() {
  rsync -rlptzv --delete --no-owner --no-group -e "$SSH" \
    --exclude '.venv/' \
    --exclude '__pycache__/' \
    --exclude '.pytest_cache/' \
    --exclude '.git/' \
    --exclude '.DS_Store' \
    --exclude 'state.json' \
    --exclude '*.egg-info/' \
    --exclude 'openspec/' \
    --exclude 'docs/' \
    --exclude '.claude/' \
    --exclude '.opencode/' \
    "$REPO/" "$DEST/"
}

if [[ "${1:-}" == "--watch" ]]; then
  command -v fswatch >/dev/null || { echo "fswatch not installed (brew install fswatch)" >&2; exit 1; }
  do_sync; echo "initial sync done; watching $REPO/fmradiod …"
  fswatch -o "$REPO/fmradiod" "$REPO/tests" "$REPO/config.yaml" "$REPO/deploy" \
    | while read -r _; do do_sync && echo "synced $(date +%T)"; done
else
  do_sync
  echo "synced $REPO/ -> $DEST"
fi
