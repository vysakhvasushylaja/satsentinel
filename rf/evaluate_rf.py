"""Honest check of the RF features (SatSentinel, 22 Oct 2026).
Time-based split (first 20 windows train, last 20 test). No hand-typed numbers."""
import csv, os, sys
import numpy as np
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.preprocessing import StandardScaler

FEATS = ["freq_offset", "phase_noise", "amplitude_variation"]
rows = list(csv.DictReader(open(sys.argv[1])))
X = np.array([[float(r[f]) for f in FEATS] for r in rows])
sat = np.array([r["sat"] for r in rows])
rec = np.array([os.path.splitext(r["recording"])[0] for r in rows])
order = np.array([int(r["window_order"]) for r in rows])
train, test = order < 20, order >= 20
Z = StandardScaler().fit(X[train]).transform(X)

print("== A. Which recording is this window from? (random forest, time split) ==")
clf = RandomForestClassifier(n_estimators=200, random_state=0).fit(Z[train], rec[train])
pred = clf.predict(Z[test])
print("overall accuracy: %.1f%%" % (100 * np.mean(pred == rec[test])))
for r in sorted(set(rec)):
    m = rec[test] == r
    print("  %-45s %.0f%%" % (r, 100 * np.mean(pred[m] == r)))

print("\n== B. Is this really X? (isolation forest trained on X's early windows) ==")
for r in sorted(set(rec)):
    iso = IsolationForest(contamination=0.05, random_state=0).fit(Z[train & (rec == r)])
    own = iso.predict(Z[test & (rec == r)]) == 1
    oth = iso.predict(Z[test & (rec != r)]) == -1
    print("  %-45s accepts own %.0f%% | rejects others %.0f%%" % (r, 100 * own.mean(), 100 * oth.mean()))

print("\n== C. Same satellite, different recording (generalises over time?) ==")
for s in sorted(set(sat)):
    recs = sorted(set(rec[sat == s]))
    if len(recs) < 2:
        continue
    a, b = recs[0], recs[1]
    iso = IsolationForest(contamination=0.05, random_state=0).fit(Z[rec == a])
    same = iso.predict(Z[rec == b]) == 1
    oth = iso.predict(Z[sat != s]) == -1
    print("  %s: train %s -> accepts %s %.0f%% | rejects other satellites %.0f%%" % (s, a, b, 100 * same.mean(), 100 * oth.mean()))
