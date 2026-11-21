#!/usr/bin/env bash
# Launcher: run in your own Terminal (outside the Claude Code sandbox: ComfyUI needs the GPU and the local ports).
# Every machine-specific path and port comes from config.json (git-ignored; copy config.example.json to config.json
# and edit it - see README.md). Nothing machine-specific is hard-coded here.
set -euo pipefail

# STUDIO = the folder this script lives in (the repository root), whatever the current directory is.
STUDIO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG="$STUDIO/config.json"

if [ ! -f "$CONFIG" ]; then
  echo "Немає config.json. Скопіюйте config.example.json у config.json і відредагуйте шляхи (README.md, розділ Setup)." >&2
  echo "config.json not found: copy config.example.json to config.json and edit the paths (README.md, section Setup)." >&2
  exit 1
fi

# cfg KEY -> prints config.json[KEY]. Uses the system python3 under -I (stdlib only: no user site, no PYTHONPATH,
# no cwd on sys.path) because the venv Python that the config names is not known yet at this point.
cfg() {
  python3 -I -c 'import json, sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$CONFIG" "$1" ||
    { echo "Не вдалося прочитати ключ \"$1\" з $CONFIG (config.json is missing the key or is not valid JSON)" >&2; exit 1; }
}
# cfg_port KEY -> the TCP port of the URL stored under KEY (comfy_url).
cfg_port() {
  python3 -I -c 'import json, sys; from urllib.parse import urlparse; print(urlparse(json.load(open(sys.argv[1]))[sys.argv[2]]).port)' "$CONFIG" "$1" ||
    { echo "Не вдалося визначити порт у ключі \"$1\" з $CONFIG" >&2; exit 1; }
}

PY="$(cfg python)"
COMFY_MAIN="$(cfg comfy_main)"
COMFY_DIR="$(dirname "$COMFY_MAIN")"       # ComfyUI's own folder (main.py lives in it); also the cwd for ComfyUI
MODELS="$(cfg models_dir)"
EXTRA="$(cfg extra_model_paths)"
COMFY_URL="$(cfg comfy_url)"
COMFY_PORT="$(cfg_port comfy_url)"
STUDIO_PORT="$(cfg studio_port)"
LOG="$STUDIO/logs/comfy.log"

# ComfyUI must NOT run under -I (it needs its own folder on sys.path); cwd = COMFY_DIR.
# The studio's own Python below DOES run under -I (isolated: no user site, no PYTHONPATH, no cwd on sys.path),
# because ComfyUI is the owner's trusted local install but the studio handles Claude-written JSON.
# --listen 127.0.0.1: ComfyUI has no authentication, so it must not be reachable from the network (kept hard-coded
# on purpose: it is a security setting, not a machine path).
# --disable-all-custom-nodes: only ComfyUI's built-in nodes are loaded; the studio's graph (app/comfy.py) uses nothing else.
# STUDIO_DRY_RUN=1 only prints the ComfyUI command (used to check it without starting anything).
COMFY_CMD=("$PY" main.py --listen 127.0.0.1 --port "$COMFY_PORT" --disable-auto-launch
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
if ! curl -s --max-time 2 -o /dev/null "$COMFY_URL"; then
  (cd "$COMFY_DIR" && nohup "${COMFY_CMD[@]}" >>"$LOG" 2>&1 &)
  up=0
  for _ in $(seq 1 45); do
    if curl -s --max-time 2 -o /dev/null "$COMFY_URL"; then up=1; break; fi
    sleep 2
  done
  if [ "$up" != 1 ]; then
    echo "ComfyUI не запустився за ~90 с. Дивіться журнал: $LOG" >&2
    exit 1
  fi
fi

echo "Студія: http://127.0.0.1:$STUDIO_PORT"
echo "ComfyUI: $COMFY_URL"

# -I ignores the current folder, so the studio root is put on sys.path explicitly; exec replaces this shell so Ctrl+C stops the studio.
# The studio itself reads config.json again (app/server.py main) - the port printed above is the one it binds.
cd "$STUDIO"
exec "$PY" -I -c 'import sys; sys.path.insert(0, "."); from app.server import main; main()'
