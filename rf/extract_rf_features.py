"""Extract RF features from real IQ recordings (SatSentinel, written 22 Oct 2026).
Idea (freq offset / phase noise / amplitude variation per 20k-sample window) is from the earlier
LEO Telemetry Guard project (Sep 2026): declared as pre-existing in the README.
Change: windows are chosen by ENERGY only, never by phase noise (avoids selection bias).
Limits: freq_offset is in cycles/sample (depends on sample rate) and includes Doppler.
SigMF recordings: Daniel Estevez, Vega-C MEO cubesats 2022-07-24, CC BY 4.0."""
import csv, glob, os, sys
import numpy as np
from scipy.io import wavfile

W, N_CAND, N_KEEP = 20000, 400, 40
NAMES = {"BY02": "BY70-2"}  # file BY02_...436152kHz is taken to be BY70-2

def open_iq(path):
    if path.lower().endswith(".wav"):
        _, data = wavfile.read(path, mmap=True)
        def get(a, b):
            return (np.asarray(data[a:b, 0], dtype=np.float32),
                    np.asarray(data[a:b, 1], dtype=np.float32))
        return get, data.shape[0]
    if path.lower().endswith(".raw"):  # RTL-SDR style unsigned 8-bit IQ (checked: byte mean ~127)
        raw = np.memmap(path, dtype="u1", mode="r")
        def get(a, b):
            seg = np.asarray(raw[2 * a:2 * b], dtype=np.float32) - 127.5
            return seg[0::2], seg[1::2]
        return get, raw.shape[0] // 2
    raw = np.memmap(path, dtype="<i2", mode="r")
    def get(a, b):
        seg = np.asarray(raw[2 * a:2 * b], dtype=np.float32)
        return seg[0::2], seg[1::2]
    return get, raw.shape[0] // 2

def features(I, Q):
    I = I / (np.max(np.abs(I)) + 1e-9)
    Q = Q / (np.max(np.abs(Q)) + 1e-9)
    d = np.diff(np.unwrap(np.arctan2(Q, I)))
    return (float(np.mean(d) / (2 * np.pi)), float(np.std(d)),
            float(np.std(np.sqrt(I ** 2 + Q ** 2))))

def main(folder, out):
    files = []
    for ext in ("*.sigmf-data", "*.raw", "*.wav"):
        files += sorted(glob.glob(os.path.join(folder, ext)))
    rows = []
    for path in files:
        fname = os.path.basename(path)
        key = os.path.splitext(fname)[0].split("_")[0]
        sat = NAMES.get(key, key)
        get, n = open_iq(path)
        n_win = n // W
        idx = np.linspace(0, n_win - 1, min(N_CAND, n_win)).astype(int)
        energy = []
        for w in idx:
            I, Q = get(w * W, (w + 1) * W)
            energy.append(float(np.mean(I ** 2 + Q ** 2)))
        med = np.median(energy)
        strong = [int(w) for w, e in zip(idx, energy) if e >= med]
        if len(strong) > N_KEEP:
            strong = [strong[i] for i in np.linspace(0, len(strong) - 1, N_KEEP).astype(int)]
        for order, w in enumerate(strong):
            I, Q = get(w * W, (w + 1) * W)
            fo, pn, av = features(I, Q)
            rows.append([sat, fname, order, w * W, round(fo, 6), round(pn, 6), round(av, 6)])
        print(sat, fname, "windows:", len(strong))
    with open(out, "w", newline="") as f:
        c = csv.writer(f)
        c.writerow(["sat", "recording", "window_order", "sample_start",
                    "freq_offset", "phase_noise", "amplitude_variation"])
        c.writerows(rows)
    print("wrote", out, len(rows), "rows")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
