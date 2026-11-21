#!/usr/bin/env bash
# Launcher: run in your own Terminal (outside the sandbox).
set -euo pipefail

STUDIO=/Users/volost/GitRepos/canva/studio
PY=/Users/volost/ComfyUI-Installs/ComfyUI-test/ComfyUI/.venv/bin/python
COMFY_DIR=/Users/volost/ComfyUI-Installs/ComfyUI-test/ComfyUI
MODELS=/Volumes/WoofData/ComfyUI/models
EXTRA=/Users/volost/GitRepos/canva/pilot/comfy/extra_model_paths.yaml
LOG="$STUDIO/logs/comfy.log"

# ComfyUI must NOT run under -I (it needs its own folder on sys.path); cwd = COMFY_DIR.
# The studio's own Python below DOES run under -I (isolated: no user site, no PYTHONPATH, no cwd on sys.path),
# because ComfyUI is the owner's trusted local install but the studio handles Claude-written JSON.
# --listen 127.0.0.1: ComfyUI has no authentication, so it must not be reachable from the network.
# --disable-all-custom-nodes: only ComfyUI's built-in nodes are loaded; the studio's graph (app/comfy.py) uses nothing else.
# STUDIO_DRY_RUN=1 only prints the ComfyUI command (used to check it without starting anything).
COMFY_CMD=("$PY" main.py --listen 127.0.0.1 --port 8188 --disable-auto-launch
  --disable-all-custom-nodes --extra-model-paths-config "$EXTRA")

if [ "${STUDIO_DRY_RUN:-}" = "1" ]; then
  echo "cd $COMFY_DIR && ${COMFY_CMD[*]}"
  exit 0
fi

if [ ! -d "$MODELS" ]; then
  echo "Немає теки з моделями: $MODELS (диск WoofData не підключено?)" >&2
  exit 1
fi

mkdir -p "$STUDIO/logs"

# Start ComfyUI only if nothing answers on its port yet (so run.sh can be repeated safely), detached with nohup so it
# survives this script, then wait up to 45 x 2 s = ~90 s for it to answer before starting the studio.
if ! curl -s --max-time 2 -o /dev/null http://127.0.0.1:8188; then
  (cd "$COMFY_DIR" && nohup "${COMFY_CMD[@]}" >>"$LOG" 2>&1 &)
  up=0
  for _ in $(seq 1 45); do
    if curl -s --max-time 2 -o /dev/null http://127.0.0.1:8188; then up=1; break; fi
    sleep 2
  done
  if [ "$up" != 1 ]; then
    echo "ComfyUI не запустився за ~90 с. Дивіться журнал: $LOG" >&2
    exit 1
  fi
fi

echo "Студія: http://127.0.0.1:8765"
echo "ComfyUI: http://127.0.0.1:8188"

# -I ignores the current folder, so the studio root is put on sys.path explicitly; exec replaces this shell so Ctrl+C stops the studio.
cd "$STUDIO"
exec "$PY" -I -c 'import sys; sys.path.insert(0, "."); from app.server import main; main()'
