"""SatSentinel entry point.
Server: python run.py            -> POST /run {"alert_id": "A-101"} on port 8000
CLI:    python run.py A-101      -> prints the case card as JSON
"""
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

def _load_env(path=".env"):
    try:
        for line in open(path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
    except OSError:
        pass


_load_env()

from satsentinel import trace  # noqa: E402
from satsentinel.agents import Investigator
from satsentinel.explainer import add_explanation
from satsentinel.real_agents import RealInvestigator

ID = re.compile(r"^A-\d{3}$")


def run_case(alert_id, explain=True):
    if not isinstance(alert_id, str) or not ID.match(alert_id):
        raise ValueError("alert_id must look like A-101")
    run_id = trace.new_run(alert_id)
    inv = RealInvestigator() if int(alert_id[2:]) >= 100 else Investigator()
    card = inv.investigate(alert_id)
    if explain:
        add_explanation(card)
    card["run_id"] = run_id
    trace.emit("run_end", verdict=card["verdict"], confidence=card["confidence"])
    return card


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj, default=str, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            return self._send(200, {"status": "ok"})
        self._send(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/run":
            return self._send(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n) or b"{}")
            card = run_case(req.get("alert_id"), req.get("explain", True))
            self._send(200, card)
        except (ValueError, json.JSONDecodeError) as ex:
            self._send(400, {"error": str(ex)})
        except Exception as ex:
            trace.emit("run_error", error=str(ex)[:300])
            self._send(500, {"error": str(ex)[:300]})

    def log_message(self, *args):
        pass


def main():
    if len(sys.argv) > 1:
        print(json.dumps(run_case(sys.argv[1]), default=str, indent=2))
        return
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    print("SatSentinel listening on %s:%d (POST /run)" % (host, port), file=sys.stderr)
    HTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
