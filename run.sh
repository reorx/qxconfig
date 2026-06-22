#!/usr/bin/env bash
#
# Serve the built ./dest directory over HTTP so Quantumult X can fetch the
# localized rules and the Clash subscription. Binds all interfaces so the LAN
# address in --base-url works.
#
# Usage:
#   ./run.sh           # serve ./dest on port 8888
#   ./run.sh 9000      # serve on a different port
set -euo pipefail

cd "$(dirname "$0")"

PORT="${1:-8888}"

if [ ! -d dest ]; then
  echo "dest/ not found — run ./build.sh first." >&2
  exit 1
fi

echo "Serving ./dest at http://0.0.0.0:${PORT} (Ctrl-C to stop)"
exec python3 -m http.server "${PORT}" --bind 0.0.0.0 --directory dest
