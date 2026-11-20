#!/usr/bin/env bash
# Launcher: run in your own Terminal (outside the sandbox).
set -euo pipefail

STUDIO=/Users/volost/GitRepos/canva/studio
PY=/Users/volost/ComfyUI-Installs/ComfyUI-test/ComfyUI/.venv/bin/python
COMFY_MAIN=/Users/volost/ComfyUI-Installs/ComfyUI-test/ComfyUI/main.py
MODELS=/Volumes/WoofData/ComfyUI/models
EXTRA=/Users/volost/GitRepos/canva/pilot/comfy/extra_model_paths.yaml

if [ ! -d "$MODELS" ]; then
  echo "Немає теки з моделями: $MODELS (диск WoofData не підключено?)" >&2
  exit 1
fi

mkdir -p "$STUDIO/logs"

if ! curl -s -o /dev/null http://127.0.0.1:8188; then
  nohup "$PY" -I "$COMFY_MAIN" --listen 127.0.0.1 --port 8188 --disable-auto-launch \
    --disable-all-custom-nodes --extra-model-paths-config "$EXTRA" \
    >"$STUDIO/logs/comfy.log" 2>&1 &
fi

echo "Студія: http://127.0.0.1:8765"
echo "ComfyUI: http://127.0.0.1:8188"

cd "$STUDIO"
exec "$PY" -I -c 'import sys; sys.path.insert(0, "."); from app.server import main; main()'
