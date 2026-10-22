"""SatSentinel synthetic data (written 22 Oct 2026, hackathon window).
RF values are SIMULATED. ground_truth_eval_only.csv is for scoring, never for the agent."""
import csv, os, random
from datetime import datetime, timedelta

random.seed(7)
os.makedirs("data", exist_ok=True)
T0 = datetime(2026, 10, 22, 0, 0, 0)
PHASE = {"SAT-01": 10, "SAT-02": 20, "SAT-03": 30}
PERIOD, ECL = 95, 35
EVENT = {"SAT-01": 250, "SAT-02": 130, "SAT-03": 400}

def ts(m): return (T0 + timedelta(minutes=m)).strftime("%Y-%m-%dT%H:%M:%SZ")
def in_ecl(ph, m): return m >= ph and ((m - ph) % PERIOD) < ECL

assert not in_ecl(10, 250) and in_ecl(20, 130) and not in_ecl(30, 400)

tele, rf, orbit = [], [], []
for sat, ph in PHASE.items():
    seq = 0
    for m in range(1440):
        seq += 1
        ecl = in_ecl(ph, m)
        batt = 3.95 + random.gauss(0, 0.01) - (0.25 if ecl else 0)
        solar = 0.02 if ecl else 1.2 + random.gauss(0, 0.03)
        temp = 21 + random.gauss(0, 0.3) - (6 if ecl else 0)
        hm, s = 1, seq
        fo, rise, pn = random.gauss(0, 40), random.gauss(12, 0.4), random.gauss(-95, 1.0)
        if sat == "SAT-02" and 130 <= m <= 134:
            batt -= 0.12; temp -= 3
        if sat == "SAT-01" and m == 250:
            s = seq - 200
        if sat == "SAT-03" and 400 <= m <= 404:
            hm = 0
            fo, rise, pn = 900 + random.gauss(0, 30), 15.5 + random.gauss(0, 0.2), -88 + random.gauss(0, 0.5)
        tele.append([sat, ts(m), s, round(batt, 3), round(temp, 2), round(solar, 3), hm])
        rf.append([sat, ts(m), round(fo, 1), round(rise, 2), round(pn, 2)])
    st = ph
    while st < 1440:
        orbit.append([sat, ts(st), ts(min(st + ECL, 1439)), "eclipse"])
        st += PERIOD

alerts = [
    ["A-001", "SAT-01", ts(250), "sequence_check", 0.97],
    ["A-002", "SAT-02", ts(130), "isolation_forest", 0.91],
    ["A-003", "SAT-03", ts(400), "hmac_check", 1.00],
]
truth = [["A-001", "replay_attack"], ["A-002", "eclipse_false_alarm"], ["A-003", "spoofing_attack"]]

def w(name, head, rows):
    with open("data/" + name, "w", newline="") as f:
        c = csv.writer(f); c.writerow(head); c.writerows(rows)
    print(name, len(rows), "rows")

w("telemetry.csv", ["sat_id", "ts", "seq", "battery_v", "temp_c", "solar_current_a", "hmac_valid"], tele)
w("rf_observations_simulated.csv", ["sat_id", "ts", "freq_offset_hz", "rise_time_us", "phase_noise_db"], rf)
w("orbit_events.csv", ["sat_id", "start_ts", "end_ts", "event"], orbit)
w("alerts.csv", ["alert_id", "sat_id", "ts", "detector", "score"], alerts)
w("ground_truth_eval_only.csv", ["alert_id", "true_cause"], truth)
