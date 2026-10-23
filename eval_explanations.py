"""Evaluate the ExplainerAgent on the synthetic benchmark (needs Nightshift running and METERLESS_RUNTIME_TOKEN).
Per alert: LLM answer accepted (not template fallback), cites valid evidence, every number in the text
appears in the facts given to the model, rule-computed counterfactual
verdicts appear in the text.
Run: SAMPLE_MODE=1 python eval_explanations.py [N]  ->  eval/explanation_summary.txt, eval/explanation_results.csv"""
import csv
import os
import re
import statistics
import subprocess
import sys

os.environ["SAMPLE_MODE"] = "1"
os.environ["SATSENTINEL_DATA_DIR"] = "data_eval"
os.environ["SATSENTINEL_LOG_DIR"] = "/tmp/satsentinel_expl_logs"
if not os.path.exists("data_eval/telemetry.csv"):
    subprocess.run([sys.executable, "make_data_eval.py"], check=True, stdout=subprocess.DEVNULL)

from satsentinel.agents import Investigator  # noqa: E402
from satsentinel.counterfactual import counterfactuals  # noqa: E402
from satsentinel.explainer import _facts, explain  # noqa: E402

NUM = re.compile(r"\d+(?:\.\d+)?")


def numbers(t):
    return set(NUM.findall(re.sub(r"\[E\d+\]", "", t)))


ids = sorted(r["alert_id"] for r in csv.DictReader(open("data_eval/ground_truth_eval_only.csv")))
if len(sys.argv) > 1:
    ids = ids[: int(sys.argv[1])]
inv = Investigator()
rows = []
for k, a in enumerate(ids, 1):
    card = inv.investigate(a)
    facts = _facts(card)
    r = explain(card)
    text = r["text"]
    llm = r.get("source") == "llm"
    cited = set(re.findall(r"\[E(\d+)\]", text))
    ev_ids = {str(i) for i in range(1, len(card["evidence"]) + 1)}
    cfs = counterfactuals(card)
    cf_verdicts = {c.split("would give ")[1].split(" instead")[0] for c in cfs}
    rows.append(dict(
        alert_id=a, verdict=card["verdict"], source=r.get("source"),
        cites_valid=bool(cited) and cited <= ev_ids,
        numbers_in_facts=numbers(text) <= numbers(facts),
        cf_n=len(cfs), cf_in_text=(all(v.replace("_", " ") in text.lower().replace("_", " ") for v in cf_verdicts) if cfs else ""),
        latency_ms=r.get("latency_ms") or "", reason=r.get("reason", "")))
    print("%d/%d %s %s" % (k, len(ids), a, r.get("source")), flush=True)

n = len(rows)
llm_rows = [x for x in rows if x["source"] == "llm"]
L = []


def P(s=""):
    L.append(s)
    print(s)


def pct(c, d):
    return "%d/%d = %.1f%%" % (c, d, 100.0 * c / d) if d else "n/a"


P("explanation evaluation: %d synthetic alerts, model nvidia/nemotron-3-ultra-550b via Meterless Nightshift" % n)
P("LLM answer accepted (not template fallback): " + pct(len(llm_rows), n))
P("  of accepted answers:")
P("  cite valid evidence ids: " + pct(sum(x["cites_valid"] for x in llm_rows), len(llm_rows)))
P("  every number appears in the facts given: " + pct(sum(x["numbers_in_facts"] for x in llm_rows), len(llm_rows)))
cf_rows = [x for x in llm_rows if x["cf_n"]]
P("  mentions every rule-computed counterfactual verdict: " + pct(sum(1 for x in cf_rows if x["cf_in_text"]), len(cf_rows)))
lat = [x["latency_ms"] for x in llm_rows if x["latency_ms"] != ""]
if lat:
    P("median latency: %.1f s (max %.1f s)" % (statistics.median(lat) / 1000.0, max(lat) / 1000.0))
fb = [x for x in rows if x["source"] != "llm"]
if fb:
    P("template fallbacks: %d (reasons: %s)" % (len(fb), "; ".join(sorted({x["reason"] for x in fb}))))
os.makedirs("eval", exist_ok=True)
open("eval/explanation_summary.txt", "w").write("\n".join(L) + "\n")
with open("eval/explanation_results.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
