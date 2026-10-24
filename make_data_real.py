"""REAL-data scenario.
REAL: telemetry values + real anomaly intervals (NASA SMAP/MSL, Hundman et al. 2018).
SYNTHETIC (added by me, labelled): seq/hmac_valid metadata, injected replay/spoofing events, benign alert times."""
import csv
import random
from collections import defaultdict
from datetime import datetime, timedelta

random.seed(42)
START = datetime(2026, 10, 1, 0, 0, 0)
STEP_S = 60
WIN = 4
REPLAY_LAG = 300


def ts(i):
    return (START + timedelta(seconds=STEP_S * i)).strftime("%Y-%m-%d %H:%M:%S")


def runs(lab):
    out, s = [], None
    for i, v in enumerate(lab):
        if v and s is None:
            s = i
        if not v and s is not None:
            out.append((s, i - 1))
            s = None
    if s is not None:
        out.append((s, len(lab) - 1))
    return out


by_ch = defaultdict(list)
with open("data/smap_msl_subset.csv") as f:
    for r in csv.DictReader(f):
        by_ch[r["channel"]].append((float(r["value"]), int(r["is_anomaly"])))

tel_rows, alerts, truth_counts = [], [], defaultdict(int)
for k, (ch, rows) in enumerate(by_ch.items()):
    sat = "SAT-%02d" % (4 + k)
    vals = [v for v, _ in rows]
    lab = [l for _, l in rows]
    n = len(vals)
    mean = sum(vals) / n
    std = (sum((x - mean) ** 2 for x in vals) / n) ** 0.5 or 1.0
    faults = runs(lab)

    def clean(p):
        return all(not (s - 100 <= p + d <= e + 100) for s, e in faults for d in (0, WIN))

    seq = list(range(n))
    value = list(vals)
    hmac = [1] * n
    ev = [(sat, ch, ts(s + 1), "onboard_fault") for s, e in faults[:2]]
    taken = []
    for kind in ["replay", "spoof", "benign"] * 2:
        p = None
        for _ in range(300):
            c = random.randint(REPLAY_LAG + 10, n - WIN - 10)
            if clean(c) and all(abs(c - t) >= 150 for t in taken):
                p = c
                break
        if p is None:
            continue
        taken.append(p)
        if kind == "replay":
            for j in range(WIN):
                seq[p + j] = p - REPLAY_LAG + j
                value[p + j] = vals[p - REPLAY_LAG + j]
            ev.append((sat, ch, ts(p + 1), "replay_attack"))
        elif kind == "spoof":
            sign = 1 if random.random() < 0.5 else -1
            for j in range(WIN):
                hmac[p + j] = 0
                value[p + j] = vals[p + j] + sign * 4 * std
            ev.append((sat, ch, ts(p + 1), "spoofing_attack"))
        else:
            ev.append((sat, ch, ts(p + 1), "no_threat"))
    n_replay = sum(1 for e in ev if e[3] == "replay_attack")
    n_spoof = sum(1 for e in ev if e[3] == "spoofing_attack")
    assert sum(1 for i in range(1, n) if seq[i] <= seq[i - 1]) == n_replay, ch
    assert hmac.count(0) == WIN * n_spoof, ch
    for i in range(n):
        tel_rows.append((sat, ch, ts(i), seq[i], "%.6f" % value[i], hmac[i]))
    alerts += ev

alerts.sort(key=lambda e: (e[0], e[2]))
with open("data/telemetry_real.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["sat_id", "channel", "ts", "seq", "value", "hmac_valid"])
    w.writerows(tel_rows)
with open("data/alerts_real.csv", "w", newline="") as fa, open("data/ground_truth_real_eval_only.csv", "w", newline="") as fg:
    wa, wg = csv.writer(fa), csv.writer(fg)
    wa.writerow(["alert_id", "sat_id", "ts"])
    wg.writerow(["alert_id", "sat_id", "channel", "ts", "truth"])
    for i, (sat, ch, t, truth) in enumerate(alerts):
        aid = "A-%03d" % (101 + i)
        wa.writerow([aid, sat, t])
        wg.writerow([aid, sat, ch, t, truth])
        truth_counts[truth] += 1
print("telemetry rows:", len(tel_rows), " alerts:", len(alerts))
for t, c in sorted(truth_counts.items()):
    print(" ", t, c)
