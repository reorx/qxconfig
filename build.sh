#!/usr/bin/env bash
#
# Build the self-contained Quantumult X config into ./dest with all options on:
#   - exclude [rewrite_remote] and [task_local]
#   - reference the Clash config as a [server_remote] subscription (tag=lan)
#
# Already-downloaded rules are reused. To force a fresh re-download, append --force:
#   ./build.sh --force
set -euo pipefail

cd "$(dirname "$0")"

uv run build-qxconf.py \
  --source profile/QX_Config.conf \
  --base-url 'http://192.168.0.108:8888' \
  --clash-nodes ../clash_config/build/local-unified/local-unified.yaml \
  -o dest \
  --disable-rewrite-remote \
  --disable-task-local \
  --server-remote \
  "$@"
