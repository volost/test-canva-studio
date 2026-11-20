import dataclasses
import json
import tempfile
import threading
import time
import unittest
from pathlib import Path

from app.comfy import ComfyError
from app.config import load_config
from app.genqueue import GenQueue
from tests.test_comfy import closed_port_cfg

FIXTURE = Path(__file__).parent / "fixtures" / "config.json"


def job(n=1):
    return {"prompt": f"p{n}", "width": 512, "height": 512, "seed": n, "prefix": f"j{n}", "out_dir": "."}


def wait_done(q, ids, timeout=5):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        st = {s["id"]: s for s in q.status()}
        if all(st[i]["state"] in ("done", "failed") for i in ids):
            return st
        time.sleep(0.01)
    raise AssertionError("queue did not finish: %r" % q.status())


class GenQueueTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.log = Path(self._tmp.name) / "logs" / "generations.jsonl"
        self.cfg = load_config(FIXTURE)

    def lines(self):
        return [json.loads(x) for x in self.log.read_text(encoding="utf-8").splitlines()]

    def test_queue_reports_comfy_down(self):
        q = GenQueue(closed_port_cfg(), self.log)
        jid = q.submit(job())
        st = wait_done(q, [jid])[jid]
        self.assertEqual(st["state"], "failed")
        self.assertIn("ComfyUI недоступний", st["error"])
        (line,) = self.lines()
        self.assertNotEqual(line["exit"], 0)
        self.assertEqual(line["saved"], [])

    def test_queue_sequential(self):
        spans, lock = [], threading.Lock()

        def fake(cfg, prompt, width, height, seed, prefix, out_dir):
            t0 = time.monotonic()
            time.sleep(0.05)
            with lock:
                spans.append((t0, time.monotonic()))
            return [Path(out_dir) / f"{prefix}.png"]

        q = GenQueue(self.cfg, self.log, generate_fn=fake)
        ids = [q.submit(job(1)), q.submit(job(2))]
        st = wait_done(q, ids)
        self.assertEqual([st[i]["state"] for i in ids], ["done", "done"])
        spans.sort()
        self.assertLessEqual(spans[0][1], spans[1][0])
        self.assertEqual(st[ids[0]]["saved"], ["j1.png"])

    def test_failed_job_does_not_stop_queue_and_log_keys(self):
        def fake(cfg, prompt, width, height, seed, prefix, out_dir):
            if seed == 1:
                raise ComfyError("boom")
            return [Path(out_dir) / "ok.png"]

        q = GenQueue(self.cfg, self.log, generate_fn=fake)
        a, b = q.submit(job(1)), q.submit(job(2))
        st = wait_done(q, [a, b])
        self.assertEqual(st[a]["state"], "failed")
        self.assertEqual(st[a]["error"], "boom")
        self.assertEqual(st[b]["state"], "done")
        la, lb = self.lines()
        keys = ["utc", "prefix", "seed", "width", "height", "exit", "saved", "seconds", "prompt"]
        self.assertEqual(sorted(la), sorted(keys))
        self.assertEqual(sorted(lb), sorted(keys))
        self.assertEqual((la["exit"] != 0, lb["exit"]), (True, 0))

    def test_unexpected_exception_is_failed_not_fatal(self):
        def fake(cfg, prompt, width, height, seed, prefix, out_dir):
            if seed == 1:
                raise RuntimeError("weird")
            return []

        q = GenQueue(self.cfg, self.log, generate_fn=fake)
        a, b = q.submit(job(1)), q.submit(job(2))
        st = wait_done(q, [a, b])
        self.assertEqual((st[a]["state"], st[b]["state"]), ("failed", "done"))


if __name__ == "__main__":
    unittest.main()
