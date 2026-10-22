"""Evaluate the real-data investigator against ground truth.
Ground truth is read only AFTER each verdict is produced; the agent never sees it."""
import csv
import os

from satsentinel.real_agents import RealInvestigator
from satsentinel.zetaris import query

TRUTH_FILE = "data/ground_truth_real_eval_only.csv"
CLASSES = ["onboard_fault", "replay_attack", "spoofing_attack", "no_threat"]
PRED = CLASSES + ["unknown", "error"]
ATTACKS = {"replay_attack", "spoofing_attack"}


def pct(a, b):
    return "%d/%d = %.1f%%" % (a, b, 100.0 * a / b) if b else "0/0"


def summarize(rows):
    total = len(rows)
    correct = sum(1 for r in rows if r["truth"] == r["pred"])
    unknown = sum(1 for r in rows if r["pred"] == "unknown")
    errors = sum(1 for r in rows if r["pred"] == "error")
    answered = total - unknown - errors
    correct_answered = correct
    lines = []
    lines.append("alerts evaluated: %d" % total)
    lines.append("strict accuracy (unknown counted wrong): " + pct(correct, total))
    lines.append("abstained (unknown): %d, errors: %d" % (unknown, errors))
    lines.append("accuracy on answered alerts: " + pct(correct_answered, answered))
    attacks = [r for r in rows if r["truth"] in ATTACKS]
    others = [r for r in rows if r["truth"] not in ATTACKS]
    lines.append("cyber attacks flagged as an attack: "
                 + pct(sum(1 for r in attacks if r["pred"] in ATTACKS), len(attacks)))
    lines.append("non-attacks wrongly flagged as an attack: "
                 + pct(sum(1 for r in others if r["pred"] in ATTACKS), len(others)))
    faults = [r for r in rows if r["truth"] == "onboard_fault"]
    lines.append("real onboard faults wrongly flagged as an attack: "
                 + pct(sum(1 for r in faults if r["pred"] in ATTACKS), len(faults)))
    lines.append("")
    lines.append("per-class recall:")
    for c in CLASSES:
        sub = [r for r in rows if r["truth"] == c]
        lines.append("  %-16s %s" % (c, pct(sum(1 for r in sub if r["pred"] == c), len(sub))))
    lines.append("")
    lines.append("confusion matrix (rows = truth, columns = prediction)")
    lines.append("%-16s" % "" + "".join("%16s" % p for p in PRED))
    for c in CLASSES:
        sub = [r for r in rows if r["truth"] == c]
        lines.append("%-16s" % c + "".join("%16d" % sum(1 for r in sub if r["pred"] == p) for p in PRED))
    return lines


def main():
    with open(TRUTH_FILE, newline="") as f:
        truth = {r["alert_id"]: r for r in csv.DictReader(f)}
    ids = sorted(str(r["alert_id"]).strip() for r in query("SELECT alert_id FROM SATSENTINEL.alerts_real"))
    missing = [i for i in ids if i not in truth]
    if missing:
        raise SystemExit("no ground truth for: " + ", ".join(missing))
    inv = RealInvestigator()
    rows = []
    for k, aid in enumerate(ids, 1):
        try:
            card = inv.investigate(aid)
            pred, conf, reason = card["verdict"], card["confidence"], card["confidence_reason"]
        except Exception as e:
            pred, conf, reason = "error", "", str(e)[:200]
        t = truth[aid]["truth"]
        rows.append({
            "alert_id": aid,
            "sat_id": truth[aid]["sat_id"],
            "channel": truth[aid]["channel"],
            "truth": t,
            "pred": pred,
            "confidence": conf,
            "reason": reason,
        })
        print("%d/%d %s truth=%s pred=%s" % (k, len(ids), aid, t, pred), flush=True)
    os.makedirs("eval", exist_ok=True)
    with open("eval/real_results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    lines = summarize(rows)
    with open("eval/real_summary.txt", "w") as f:
        f.write("\n".join(lines) + "\n")
    print()
    print("\n".join(lines))


if __name__ == "__main__":
    main()
