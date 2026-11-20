"""Generation tickets, persisted per template in templates/<t>/gen_tickets.json (R14).

File: {"pending": [ticket, ...], "recent": [result, ...]}. A ticket is what assets.submit_generations
returns; a result is what assets.process_finished returns (status done|failed) or a ticket this process
cannot account for (status "lost"). The GenQueue lives in memory, so after a server restart no pending
ticket is known to it: such tickets are turned into "lost" results at the next sync, never left pending.

Lock order: GEN_LOCK first, then store.STATE_LOCK (assets.py takes STATE_LOCK inside process_finished).
"""
import threading
from pathlib import Path

from app import assets
from app.store import STATE_LOCK, CorruptJSON, read_json, template_dir, write_json_atomic

LOST_MESSAGE = "генерацію перервано перезапуском — згенеруйте ще раз"
RECENT_MAX = 50
GEN_LOCK = threading.RLock()


def _path(cfg, name) -> Path:
    return template_dir(cfg, name) / "gen_tickets.json"


def load(cfg, name) -> dict:
    """{"pending": [...], "recent": [...]}; a missing or corrupt file reads as empty (the tickets in a
    corrupt file cannot be recovered; the next save replaces it)."""
    try:
        data = read_json(_path(cfg, name))
    except (FileNotFoundError, CorruptJSON):
        data = {}
    pending = [t for t in data.get("pending", []) if isinstance(t, dict) and isinstance(t.get("job_id"), str)]
    recent = [r for r in data.get("recent", []) if isinstance(r, dict)]
    return {"pending": pending, "recent": recent[-RECENT_MAX:]}


def _save(cfg, name, data) -> None:
    with STATE_LOCK:
        write_json_atomic(_path(cfg, name), {"pending": data["pending"], "recent": data["recent"][-RECENT_MAX:]})


def add(cfg, name, new_tickets) -> None:
    with GEN_LOCK:
        data = load(cfg, name)
        data["pending"] += list(new_tickets)
        _save(cfg, name, data)


def _lost(ticket) -> dict:
    return {"asset": ticket.get("asset"), "job_id": ticket["job_id"], "seed": ticket.get("seed"), "status": "lost",
            "files": [], "problems": [LOST_MESSAGE]}


def sync(cfg, queue, name, m) -> dict:
    """Mark tickets the queue does not know as lost, postprocess the finished ones (`m` = the skeleton
    map, None if unreadable: then known tickets just stay pending), persist, return the new data."""
    with GEN_LOCK:
        data = load(cfg, name)
        if not data["pending"]:
            return data
        known = {s["id"] for s in queue.status()}
        lost = [t for t in data["pending"] if t["job_id"] not in known]
        pending = [t for t in data["pending"] if t["job_id"] in known]
        results = [_lost(t) for t in lost]
        if m is not None and pending:
            pending, done = assets.process_finished(queue, template_dir(cfg, name), m, pending)
            results += done
        if lost or results or len(pending) != len(data["pending"]):
            data = {"pending": pending, "recent": data["recent"] + results}
            _save(cfg, name, data)
        return data


def with_queue_state(queue, pending) -> list:
    """Pending tickets with the queue's current state (queued|running|done|failed) for the UI."""
    by_id = {s["id"]: s for s in queue.status()}
    return [dict(t, state=by_id.get(t["job_id"], {}).get("state", "unknown")) for t in pending]
