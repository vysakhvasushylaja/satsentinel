"""Evaluate SatSentinel on the synthetic benchmark in data_eval/ (SAMPLE_MODE, DuckDB).
Run: python evaluate_synthetic.py   -> eval/synthetic_summary.txt, eval/synthetic_results.csv
Includes an ablation: each configuration switches off one evidence source (its agent's evidence is discarded)."""
import csv
import dataclasses
import os
import subprocess
import sys
from collections import Counter, defaultdict

os.environ["SAMPLE_MODE"] = "1"
os.environ["SATSENTINEL_DATA_DIR"] = "data_eval"
os.environ["SATSENTINEL_LOG_DIR"] = "/tmp/satsentinel_eval_logs"
if not os.path.exists("data_eval/telemetry.csv"):
    subprocess.run([sys.executable, "make_data_eval.py"], check=True, stdout=subprocess.DEVNULL)

from satsentinel import trace  # noqa: E402

trace.emit = lambda *a, **k: None

from satsentinel.agents import Investigator  # noqa: E402

CONFIGS = [
    ("full", ()),
    ("no_rf", ("rf",)),
    ("no_orbit", ("orbit",)),
    ("no_cyber", ("cyber",)),
    ("cyber_only", ("rf", "orbit")),
]
ATTACKS = ("replay_attack", "spoofing_attack")
CLASSES = ["replay_attack", "spoofing_attack", "eclipse_false_alarm", "other"]
PREDS = ["replay_attack", "spoofing_attack", "eclipse_false_alarm", "unknown", "error"]


class Off:
    """Runs the real agent but throws its evidence away (ablation)."""

    def __init__(self, inner):
        self.inner = inner

    def run(self, alert):
        return dataclasses.replace(self.inner.run(alert), evidence=[])


def run_config(ids, off):
    inv = Investigator()
    for name in off:
        setattr(inv, name, Off(getattr(inv, name)))
    out = {}
    for a in ids:
        try:
            card = inv.investigate(a)
            out[a] = (card["verdict"], card["confidence"])
        except Exception as ex:  # keep going, count as error
            out[a] = ("error", str(ex)[:60])
    return out


truth = {r["alert_id"]: r for r in csv.DictReader(open("data_eval/ground_truth_eval_only.csv"))}
ids = sorted(truth)
results = {name: run_config(ids, off) for name, off in CONFIGS}


def expected(a):
    t = truth[a]["true_cause"]
    return "unknown" if t == "other" else t


def score(res):
    n = len(ids)
    ok = sum(res[a][0] == expected(a) for a in ids)
    att = [a for a in ids if truth[a]["true_cause"] in ATTACKS]
    non = [a for a in ids if truth[a]["true_cause"] not in ATTACKS]
    att_ok = sum(res[a][0] == expected(a) for a in att)
    ecl = [a for a in ids if truth[a]["true_cause"] == "eclipse_false_alarm"]
    ecl_ok = sum(res[a][0] == "eclipse_false_alarm" for a in ecl)
    false_att = sum(res[a][0] in ATTACKS for a in non)
    unk = sum(res[a][0] == "unknown" for a in ids)
    return dict(n=n, ok=ok, att=len(att), att_ok=att_ok, ecl=len(ecl), ecl_ok=ecl_ok,
                non=len(non), false_att=false_att, unk=unk)


L = []


def P(s=""):
    L.append(s)
    print(s)


full = results["full"]
s = score(full)
P("synthetic benchmark: %d alerts, 10 satellites, 10 cause types (RF is SIMULATED; truth = what was injected)" % s["n"])
P("'other' (onboard fault, benign noise) is correct only when the agent abstains (unknown).")
P("")
P("FULL SYSTEM")
P("strict accuracy: %d/%d = %.1f%%" % (s["ok"], s["n"], 100.0 * s["ok"] / s["n"]))
P("attacks given the correct attack verdict: %d/%d = %.1f%%" % (s["att_ok"], s["att"], 100.0 * s["att_ok"] / s["att"]))
P("eclipse false alarms recognised: %d/%d = %.1f%%" % (s["ecl_ok"], s["ecl"], 100.0 * s["ecl_ok"] / s["ecl"]))
P("non-attacks wrongly called an attack: %d/%d = %.1f%%" % (s["false_att"], s["non"], 100.0 * s["false_att"] / s["non"]))
P("")
P("per cause type (full system)")
by = defaultdict(list)
for a in ids:
    by[truth[a]["subtype"]].append(a)
for sub in sorted(by):
    aa = by[sub]
    c = Counter(full[a][0] for a in aa)
    ok = sum(full[a][0] == expected(a) for a in aa)
    P("  %-20s %d/%d correct   verdicts: %s" % (sub, ok, len(aa), dict(c)))
P("")
P("confusion matrix (rows = truth, columns = prediction)")
P("%-20s" % "" + "".join("%20s" % p for p in PREDS))
for cl in CLASSES:
    row = Counter(full[a][0] for a in ids if truth[a]["true_cause"] == cl)
    P("%-20s" % cl + "".join("%20d" % row.get(p, 0) for p in PREDS))
P("")
P("accuracy by confidence level (full system)")
for lvl in ("high", "medium", "low"):
    aa = [a for a in ids if full[a][1] == lvl]
    ok = sum(full[a][0] == expected(a) for a in aa)
    P("  %-7s n=%d correct=%d" % (lvl, len(aa), ok))
P("")
P("ABLATION (one evidence source switched off)")
P("%-12s %9s %10s %9s %12s %9s" % ("config", "accuracy", "attacks", "eclipse", "false-attack", "unknown"))
for name, _ in CONFIGS:
    r = score(results[name])
    P("%-12s %8.1f%% %6d/%-3d %5d/%-3d %8d/%-3d %9d" % (
        name, 100.0 * r["ok"] / r["n"], r["att_ok"], r["att"], r["ecl_ok"], r["ecl"],
        r["false_att"], r["non"], r["unk"]))

os.makedirs("eval", exist_ok=True)
open("eval/synthetic_summary.txt", "w").write("\n".join(L) + "\n")
with open("eval/synthetic_results.csv", "w", newline="") as f:
    cw = csv.writer(f)
    cw.writerow(["alert_id", "subtype", "true_cause", "expected"] +
                [n + "_verdict" for n, _ in CONFIGS] + ["full_confidence"])
    for a in ids:
        cw.writerow([a, truth[a]["subtype"], truth[a]["true_cause"], expected(a)] +
                    [results[n][a][0] for n, _ in CONFIGS] + [full[a][1]])
