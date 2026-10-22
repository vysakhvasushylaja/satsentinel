"""Python wrapper around the Meterless H-MEM bridge (meterless-starter/satsentinel_memory.ts)."""
import json
import os
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRIDGE_DIR = os.path.join(ROOT, "meterless-starter")


class MemoryUnavailable(RuntimeError):
    pass


def _run(command, arg):
    try:
        p = subprocess.run(
            ["npx", "--yes", "tsx", "satsentinel_memory.ts", command, str(arg)],
            cwd=BRIDGE_DIR, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise MemoryUnavailable(str(e))
    if p.returncode != 0:
        raise MemoryUnavailable(p.stderr.strip()[-300:] or "bridge failed")
    lines = [ln for ln in p.stdout.splitlines() if ln.strip().startswith("{")]
    if not lines:
        raise MemoryUnavailable("no JSON from bridge")
    return json.loads(lines[-1])


def remember(text):
    return _run("remember", text)


def ask(text):
    return _run("ask", text)


def audit(memory_id):
    return _run("audit", memory_id)
