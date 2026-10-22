# Loading SatSentinel data into Zetaris (UI steps)

1. `python make_data.py` creates the CSVs in `data/`.
2. Upload these 4 files to NDP File System > `file-store`:
   `telemetry.csv`, `orbit_events.csv`, `alerts.csv`, `rf_observations_simulated.csv`.
   **Do NOT upload `ground_truth_eval_only.csv`** (answers are for scoring only).
3. Data Explorer > File Source & API > `+` > create file source `SATSENTINEL`.
4. For each file: Create Table > File store > Storage provider "NDP File System",
   format CSV, header=true, inferSchema=true. Table names:
   `telemetry`, `orbit_events`, `alerts`, `rf_observations_simulated`.
5. Check: `SELECT COUNT(*) FROM SATSENTINEL.<table>` gives 4320, 46, 3, 4320.

Evidence queries used by the agents (checked 22 Oct 2026):
- replay: `LAG(seq) OVER (PARTITION BY sat_id ORDER BY ts)` then `seq <= prev_seq`
- HMAC: `WHERE hmac_valid = 0`
- eclipse: JOIN `alerts` to `orbit_events` on sat_id and `ts BETWEEN start_ts AND end_ts`
