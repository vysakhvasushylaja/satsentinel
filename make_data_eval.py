"""SatSentinel synthetic BENCHMARK (written 23 Oct 2026, hackathon window).
80 alerts over 10 satellites, 10 cause types including hard cases. RF values are SIMULATED.
Ground truth comes from what was injected, never from the agents' rules.
Writes data_eval/*.csv with the same table names as data/.  Run: python make_data_eval.py"""
import csv
import os
import random
from datetime import datetime, timedelta

OUT = "data_eval"
random.seed(11)
T0 = datetime(2026, 10, 22, 0, 0, 0)
N_SATS, PERIOD, ECL, SLOTS = 10, 95, 35, 8
PHASE = {"SAT-%02d" % (i + 1): 5 + 9 * i for i in range(N_SATS)}

# (subtype, true cause, alert must be inside an eclipse window)
TYPES = [
    ("replay_clean", "replay_attack", False),
    ("replay_rf_mismatch", "replay_attack", False),
    ("replay_in_eclipse", "replay_attack", True),
    ("spoof_hmac_rf", "spoofing_attack", False),
    ("spoof_hmac_only", "spoofing_attack", False),
    ("spoof_rf_only", "spoofing_attack", False),
    ("eclipse_benign", "eclipse_false_alarm", True),
    ("eclipse_rf_glitch", "eclipse_false_alarm", True),
    ("onboard_fault", "other", False),
    ("benign_noise", "other", False),
]


def ts(m):
    return (T0 + timedelta(minutes=m)).strftime("%Y-%m-%dT%H:%M:%SZ")


def in_ecl(ph, m):
    return m >= ph and ((m - ph) % PERIOD) < ECL


def pick_minute(ph, base, want):
    ok = [
        m
        for m in range(base + 6, base + 90)
        if all(in_ecl(ph, m + k) == want for k in range(-6, 7))
    ]
    assert ok, "no suitable minute"
    return random.choice(ok)


def plan(sub):
    p = dict(replay=False, hm_fail=0, rf_n=0, rf_sigma=0.0, dip=False)
    if sub.startswith("replay"):
        p["replay"] = True
    if sub == "replay_rf_mismatch":
        p.update(rf_n=3, rf_sigma=8.0)
    if sub == "spoof_hmac_rf":
        p.update(hm_fail=5, rf_n=5, rf_sigma=random.uniform(6, 14))
    if sub == "spoof_hmac_only":
        p.update(hm_fail=5)
    if sub == "spoof_rf_only":
        p.update(rf_n=5, rf_sigma=random.uniform(2, 12))
    if sub.startswith("eclipse"):
        p["dip"] = True
    if sub == "eclipse_rf_glitch":
        p.update(rf_n=3, rf_sigma=random.uniform(3, 6))
    if sub == "onboard_fault":
        p["dip"] = True
    return p


slots_types = [t for t in TYPES for _ in range(8)]
random.shuffle(slots_types)
cases, i = [], 0
for sat, ph in PHASE.items():
    for slot in range(SLOTS):
        sub, cause, ecl = slots_types[i]
        i += 1
        m = pick_minute(ph, 100 + 160 * slot, ecl)
        cases.append(dict(id="A-%d" % (200 + i), sat=sat, m=m, sub=sub, cause=cause, p=plan(sub)))

tele, rf, orbit = [], [], []
for sat, ph in PHASE.items():
    replay, hm0, dip, rfs = set(), set(), set(), {}
    for c in (c for c in cases if c["sat"] == sat):
        p, m = c["p"], c["m"]
        if p["replay"]:
            replay.add(m)
        for k in range(p["hm_fail"]):
            hm0.add(m + k)
        for k in range(p["rf_n"]):
            rfs[m + k] = p["rf_sigma"]
        if p["dip"]:
            for k in range(5):
                dip.add(m + k)
    seq = 0
    for m in range(1440):
        seq += 1
        ecl = in_ecl(ph, m)
        batt = 3.95 + random.gauss(0, 0.01) - (0.25 if ecl else 0)
        solar = 0.02 if ecl else 1.2 + random.gauss(0, 0.03)
        temp = 21 + random.gauss(0, 0.3) - (6 if ecl else 0)
        fo, rise, pn = random.gauss(0, 40), random.gauss(12, 0.4), random.gauss(-95, 1.0)
        if m in dip:
            batt -= 0.12
            temp -= 3
        if m in rfs:
            fo += rfs[m] * 40
            rise += rfs[m] * 0.4
            pn += rfs[m] * 1.0
        s = seq - min(200, m - 50) if m in replay else seq
        hm = 0 if m in hm0 else 1
        tele.append([sat, ts(m), s, round(batt, 3), round(temp, 2), round(solar, 3), hm])
        rf.append([sat, ts(m), round(fo, 1), round(rise, 2), round(pn, 2)])
    st = ph
    while st < 1440:
        orbit.append([sat, ts(st), ts(min(st + ECL, 1439)), "eclipse"])
        st += PERIOD

alerts = [
    [c["id"], c["sat"], ts(c["m"]), random.choice(["isolation_forest", "sequence_check", "hmac_check"]),
     round(random.uniform(0.8, 1.0), 2)]
    for c in cases
]
truth = [[c["id"], c["cause"], c["sub"], round(c["p"]["rf_sigma"], 2)] for c in cases]


def w(name, head, rows):
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, name), "w", newline="") as f:
        cw = csv.writer(f)
        cw.writerow(head)
        cw.writerows(rows)
    print(name, len(rows), "rows")


w("telemetry.csv", ["sat_id", "ts", "seq", "battery_v", "temp_c", "solar_current_a", "hmac_valid"], tele)
w("rf_observations_simulated.csv", ["sat_id", "ts", "freq_offset_hz", "rise_time_us", "phase_noise_db"], rf)
w("orbit_events.csv", ["sat_id", "start_ts", "end_ts", "event"], orbit)
w("alerts.csv", ["alert_id", "sat_id", "ts", "detector", "score"], alerts)
w("ground_truth_eval_only.csv", ["alert_id", "true_cause", "subtype", "rf_sigma"], truth)
