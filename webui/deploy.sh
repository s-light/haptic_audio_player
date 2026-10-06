#!/bin/sh
# Build the web UI here and copy webui/dist/spa to the board (the Quasar CLI needs Node >= 22.12, which the
# board's Debian usually does not have).
#
#   webui/deploy.sh user@board [remote-repo-dir]      default remote dir: ~/haptic_audio_player
#
# If the board's root is read-only (after `./setup_pb2.py readonly-root`): run ./readwrite.sh on the board first
# and ./readonly.sh afterwards. The player serves the files straight from disk - no restart needed.
set -eu
[ $# -ge 1 ] || { echo "usage: $0 user@board [remote-repo-dir]" >&2; exit 1; }
cd "$(dirname "$0")"
remote="$1"
dir="${2:-haptic_audio_player}"
pnpm install --frozen-lockfile
pnpm build
rsync -av --delete dist/spa/ "$remote:$dir/webui/dist/spa/"
