"""Sequential background generation queue: one daemon worker, one log line per run.

One worker on purpose: ComfyUI renders on the one local GPU, so running several generations at once only
slows each down and risks running out of memory. The queue lives in memory only; it is lost on a restart,
which is why tickets.py persists the tickets and marks the ones this queue no longer knows as "lost".
Each run appends one JSON line to <root>/logs/generations.jsonl (the audit trail of seeds and prompts).
"""
import json
import queue
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app import comfy


class GenQueue:
    def __init__(self, cfg, log_path: Path, generate_fn=None):
        self._cfg = cfg
        self._log = Path(log_path)
        self._gen = generate_fn or comfy.generate
        self._q: queue.Queue = queue.Queue()
        self._lock = threading.Lock()
        self._jobs: dict[str, dict] = {}
        self._order: list[str] = []
        threading.Thread(target=self._run, name="genqueue", daemon=True).start()

    def submit(self, job: dict) -> str:
        jid = uuid.uuid4().hex[:12]
        rec = {"id": jid, "state": "queued", "error": None, "seconds": None, "saved": []}
        with self._lock:
            self._jobs[jid] = rec
            self._order.append(jid)
        self._q.put((jid, dict(job)))
        return jid

    def status(self) -> list[dict]:
        with self._lock:
            return [dict(self._jobs[i], saved=list(self._jobs[i]["saved"])) for i in self._order]

    def _set(self, jid, **kw):
        with self._lock:
            self._jobs[jid].update(kw)

    def _run(self):
        while True:
            jid, job = self._q.get()
            try:
                self._process(jid, job)
            # If this thread died, every later generation would stay "queued" forever with no error shown.
            except Exception as e:  # the worker must never die
                self._set(jid, state="failed", error=f"Внутрішня помилка: {e}")

    def _process(self, jid, job):
        self._set(jid, state="running")
        t0 = time.monotonic()
        saved, error = [], None
        try:
            paths = self._gen(self._cfg, job["prompt"], job["width"], job["height"],
                              job["seed"], job["prefix"], Path(job["out_dir"]))
            saved = [Path(p).name for p in paths]
        except comfy.ComfyError as e:
            error = str(e)
        except Exception as e:
            error = f"Несподівана помилка: {e}"
        seconds = round(time.monotonic() - t0, 2)
        self._set(jid, state="failed" if error else "done", error=error, seconds=seconds, saved=saved)
        line = {"utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "prefix": job["prefix"], "seed": job["seed"], "width": job["width"],
                "height": job["height"], "exit": 1 if error else 0, "saved": saved,
                "seconds": seconds, "prompt": job["prompt"]}
        try:
            self._log.parent.mkdir(parents=True, exist_ok=True)
            with self._log.open("a", encoding="utf-8") as f:
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
        except OSError as e:
            self._set(jid, error=(error or "") + f" (журнал не записано: {e})")
