"""SatSentinel one-screen UI (standard library only).
Recommendation only: the UI records the HUMAN decision, the agent never acts."""
import json
import os
import re
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

ALERT_RE = re.compile(r"^A-\d{3}$")
DECISIONS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "decisions.jsonl")
_CACHE = {}
_INVESTIGATOR = None


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
        if _INVESTIGATOR is None:
            _INVESTIGATOR = Investigator()
        _CACHE[alert_id] = apply_memory(_INVESTIGATOR.investigate(alert_id))
    return _CACHE[alert_id]


def get_alerts():
    from satsentinel.zetaris import query
    return query("SELECT alert_id, sat_id, ts FROM SATSENTINEL.alerts ORDER BY alert_id")


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SatSentinel</title><style>
:root{--bg:#0b1020;--panel:#141b33;--line:#26304f;--text:#e6e9f5;--mute:#93a0c4;--ok:#3ecf8e;--warn:#f5b84b;--bad:#ff6b6b;--acc:#6ea8ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,Segoe UI,sans-serif}
header{padding:16px 24px;border-bottom:1px solid var(--line)}header h1{margin:0;font-size:20px}header p{margin:2px 0 0;color:var(--mute)}
main{display:grid;grid-template-columns:280px 1fr;gap:16px;padding:16px 24px}
@media(max-width:800px){main{grid-template-columns:1fr}}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px}
.alert{padding:10px;border-radius:8px;cursor:pointer;border:1px solid transparent}.alert:hover{border-color:var(--line)}
.alert.sel{background:#1c2547;border-color:var(--acc)}.alert small{color:var(--mute);display:block}
.badge{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12px;font-weight:600;border:1px solid var(--line);margin-right:6px}
.v-replay_attack,.v-spoofing_attack{color:var(--bad);border-color:var(--bad)}.v-eclipse_false_alarm{color:var(--ok);border-color:var(--ok)}
.c-high{color:var(--ok)}.c-medium{color:var(--warn)}.c-low{color:var(--bad)}
h2{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--mute);margin:18px 0 6px}
.item{padding:8px 10px;border-left:3px solid var(--line);margin:6px 0;background:#10162b;border-radius:0 6px 6px 0}
.item b{color:var(--acc)}.sim{color:var(--warn);font-weight:700}.mem{border-left-color:var(--acc)}
.banner{margin-top:18px;padding:12px;border:1px dashed var(--warn);border-radius:8px}
button{background:var(--acc);color:#07112b;border:0;padding:8px 14px;border-radius:8px;font-weight:700;cursor:pointer;margin-right:8px}
button.rej{background:transparent;color:var(--bad);border:1px solid var(--bad)}button.sec{background:transparent;color:var(--acc);border:1px solid var(--acc)}
input{width:100%;margin:8px 0;padding:8px;border-radius:8px;border:1px solid var(--line);background:#0e1429;color:var(--text)}
.mute{color:var(--mute)}
.badge:empty{display:none}
</style></head><body>
<header><h1>SatSentinel</h1><p>Explainable satellite alert investigation</p></header>
<main><div class="panel"><div id="alerts" class="mute">Loading alerts...</div></div>
<div class="panel" id="case"><span class="mute">Select an alert on the left.</span></div></main>
<script>
function el(t,c,x){var e=document.createElement(t);if(c)e.className=c;if(x!==undefined&&x!==null)e.textContent=x;return e}
async function api(p,o){var r=await fetch(p,o);var j=await r.json();if(!r.ok)throw new Error(j.error||r.status);return j}
var verdicts={};
function section(box,title){box.append(el('h2',null,title))}
function item(text,head,source,cls){var d=el('div','item '+(cls||''));
 if(head){d.append(el('b',null,head+' '))}
 if(source){var s=el('span',/SIMULATED/i.test(source)?'sim':'mute','['+source+'] ');d.append(s)}
 var t=String(text);if(/SIMULATED/i.test(t)){d.style.borderLeftColor='var(--warn)'}
 d.append(el('span',null,t));return d}
function asText(o){return o.summary||o.text||JSON.stringify(o)}
async function loadAlerts(){var box=document.getElementById('alerts');
 try{var rows=await api('/api/alerts');box.replaceChildren();
  rows.forEach(function(a){var r=el('div','alert');r.id='row-'+a.alert_id;
   r.append(el('b',null,a.alert_id),el('small',null,a.sat_id+'  '+a.ts),el('span','badge','')); r.lastChild.id='bd-'+a.alert_id;
   r.onclick=function(){openCase(a.alert_id,false)};box.append(r)})}
 catch(e){box.textContent='Could not load alerts: '+e.message}}
async function openCase(id,refresh){var box=document.getElementById('case');
 document.querySelectorAll('.alert').forEach(function(x){x.classList.toggle('sel',x.id==='row-'+id)});
 box.replaceChildren(el('span','mute','Investigating '+id+' ...'));
 try{var c=await api('/api/case/'+id+(refresh?'?refresh=1':''));render(box,c)}
 catch(e){box.textContent='Error: '+e.message}}
function render(box,c){box.replaceChildren();
 var bd=document.getElementById('bd-'+c.alert_id);if(bd){bd.textContent=c.verdict;bd.className='badge v-'+c.verdict}
 box.append(el('h1',null,'Case '+c.alert_id+' - '+c.sat_id));
 box.append(el('div','mute',c.ts));
 var top=el('div');top.style.margin='10px 0';
 top.append(el('span','badge v-'+c.verdict,c.verdict),el('span','badge c-'+c.confidence,'confidence: '+c.confidence));box.append(top);
 box.append(el('div','mute',c.confidence_reason));
 section(box,'Recommended action');box.append(el('div',null,c.recommended_action));
 section(box,'Evidence');
 (c.evidence||[]).forEach(function(e){var head=[e.agent,e.tool||e.name].filter(Boolean).join(' / ');box.append(item(asText(e),head,e.source))});
 section(box,'Self-critique');
 if(!(c.critique||[]).length)box.append(el('div','mute','No critique items.'));
 (c.critique||[]).forEach(function(k){var head=(k.status?'['+k.status+'] ':'')+(k.name||k.check||'');box.append(item(asText(k),head,null))});
 section(box,'Not found');
 (c.not_found||[]).forEach(function(n){box.append(item(typeof n==='string'?n:asText(n),null,null))});
 section(box,'Analyst memory (prior knowledge, not an observation)');
 if(c.memory==='unavailable')box.append(el('div','mute','Memory unavailable. Decision made from data only.'));
 else if(!c.memory||!c.memory.length)box.append(el('div','mute','No matching analyst note.'));
 else c.memory.forEach(function(m){box.append(item(m.text,m.id,null,'mem'))});
 var b=el('div','banner');b.append(el('b',null,'Recommendation only. Human approval required.'));
 var note=el('input');note.placeholder='Optional note';b.append(note);
 var msg=el('div','mute');
 function send(d){return async function(){try{var r=await api('/api/decision',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({alert_id:c.alert_id,decision:d,note:note.value})});msg.textContent='Recorded: '+r.decision+' at '+r.time_utc}catch(e){msg.textContent='Error: '+e.message}}}
 var a=el('button',null,'Approve');a.onclick=send('approve');
 var r=el('button','rej','Reject');r.onclick=send('reject');
 var rr=el('button','sec','Re-run investigation');rr.onclick=function(){openCase(c.alert_id,true)};
 b.append(a,r,rr,msg);box.append(b)}
loadAlerts();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
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
            self._json(200, rec)
        except ValueError as e:
            self._json(400, {"error": str(e)})
        except Exception as e:
            self._json(500, {"error": str(e)[:300]})

    def log_message(self, *args):
        pass


def main():
    print("SatSentinel UI on http://localhost:8080  (Ctrl+C to stop)")
    HTTPServer(("127.0.0.1", 8080), Handler).serve_forever()


if __name__ == "__main__":
    main()
