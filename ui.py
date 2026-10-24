"""SatSentinel one-screen UI (standard library only).
Recommendation only: the UI records the HUMAN decision, the agent never acts."""
import json
import os
import re
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

ALERT_RE = re.compile(r"^A-\d{3}$")
DECISIONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "decisions.jsonl")
_CACHE = {}
_INVESTIGATOR = None
_REAL_INVESTIGATOR = [None]


def valid_alert_id(value):
    return bool(ALERT_RE.fullmatch(str(value)))


def build_decision(card, decision, note):
    if decision not in ("approve", "reject"):
        raise ValueError("decision must be approve or reject")
    return {
        "time_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "alert_id": card["alert_id"],
        "verdict": card["verdict"],
        "confidence": card["confidence"],
        "decision": decision,
        "note": str(note or "")[:500],
    }


def write_decision(record, path=DECISIONS):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def get_case(alert_id, refresh=False):
    global _INVESTIGATOR
    if refresh or alert_id not in _CACHE:
        from satsentinel.agents import Investigator
        from satsentinel.memory_agent import apply_memory
        if int(alert_id[2:]) >= 100:
            from satsentinel.real_agents import RealInvestigator
            if _REAL_INVESTIGATOR[0] is None:
                _REAL_INVESTIGATOR[0] = RealInvestigator()
            card = _REAL_INVESTIGATOR[0].investigate(alert_id)
        else:
            if _INVESTIGATOR is None:
                _INVESTIGATOR = Investigator()
            card = _INVESTIGATOR.investigate(alert_id)
        card = apply_memory(card)
        from satsentinel.counterfactual import counterfactuals
        card["counterfactuals"] = counterfactuals(card)
        _CACHE[alert_id] = card
    return _CACHE[alert_id]


_EXPLAIN = {}


def get_explanation(alert_id):
    card = get_case(alert_id)
    key = (alert_id, card["verdict"], card["confidence"])
    if key not in _EXPLAIN:
        from satsentinel.explainer import explain
        _EXPLAIN[key] = explain(card)
    return _EXPLAIN[key]


def get_alerts():
    from satsentinel.zetaris import query
    rows = query("SELECT alert_id, sat_id, ts FROM SATSENTINEL.alerts")
    rows += query("SELECT alert_id, sat_id, ts FROM SATSENTINEL.alerts_real")
    return sorted(rows, key=lambda r: str(r["alert_id"]))


PAGE = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui_page.html"), encoding="utf-8").read()


class Handler(BaseHTTPRequestHandler):
    timeout = 15  # drop idle browser pre-connections

    def _send(self, code, body, ctype="application/json"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj, default=str))

    def do_GET(self):
        u = urlparse(self.path)
        try:
            if u.path == "/":
                self._send(200, PAGE, "text/html")
            elif u.path == "/api/alerts":
                self._json(200, get_alerts())
            elif u.path.startswith("/api/case/"):
                aid = u.path[len("/api/case/"):]
                if not valid_alert_id(aid):
                    return self._json(400, {"error": "bad alert id"})
                refresh = parse_qs(u.query).get("refresh") == ["1"]
                self._json(200, get_case(aid, refresh))
            elif u.path.startswith("/api/explain/"):
                aid = u.path[len("/api/explain/"):]
                if not valid_alert_id(aid):
                    return self._json(400, {"error": "bad alert id"})
                self._json(200, get_explanation(aid))
            else:
                self._json(404, {"error": "not found"})
        except Exception as e:  # shown locally only
            self._json(500, {"error": str(e)[:300]})

    def do_POST(self):
        if self.path != "/api/decision":
            return self._json(404, {"error": "not found"})
        try:
            n = int(self.headers.get("Content-Length", "0"))
            if n > 10000:
                return self._json(400, {"error": "body too large"})
            body = json.loads(self.rfile.read(n) or b"{}")
            aid = body.get("alert_id")
            if not valid_alert_id(aid):
                return self._json(400, {"error": "bad alert id"})
            rec = build_decision(get_case(aid), body.get("decision"), body.get("note"))
            write_decision(rec)
            try:
                from satsentinel.decision_memory import record_decision
                record_decision(get_case(aid), rec["decision"], rec["note"])
            except Exception:
                pass
            self._json(200, rec)
        except ValueError as e:
            self._json(400, {"error": str(e)})
        except Exception as e:
            self._json(500, {"error": str(e)[:300]})

    def log_message(self, *args):
        pass


def main():
    print("SatSentinel UI on http://localhost:8080  (Ctrl+C to stop)")
    ThreadingHTTPServer(("127.0.0.1", 8080), Handler).serve_forever()


if __name__ == "__main__":
    main()
