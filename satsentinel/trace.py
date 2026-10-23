"""JSONL trace log. One event per line, to stdout and logs/trace.jsonl."""
import json
import os
import sys
import time

LOG_DIR = os.environ.get("SATSENTINEL_LOG_DIR", "logs")
_run_id = None


def new_run(alert_id=None):
    global _run_id
    _run_id = "run_%d" % int(time.time() * 1000)
    emit("run_start", alert_id=alert_id)
    return _run_id


def emit(event, **fields):
    rec = {"ts": time.time(), "run_id": _run_id, "event": event}
    rec.update(fields)
    line = json.dumps(rec, default=str)
    print(line, file=sys.stderr, flush=True)
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(os.path.join(LOG_DIR, "trace.jsonl"), "a") as f:
            f.write(line + "\n")
    except OSError:
        pass
