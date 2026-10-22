"""Evidence tools for the REAL-data scenario (SATSENTINEL.telemetry_real).
Values are real NASA SMAP/MSL telemetry; seq/hmac metadata and attacks are injected."""
from satsentinel.tools import (
    SOURCE_TELEMETRY,
    _cast_col,
    _execute,
    _in_window,
    _replay_seen_earlier,
    _validate,
    _window_bounds,
)

TABLE = "SATSENTINEL.telemetry_real"
Z_THRESHOLD = 3.0  # fixed a priori, not tuned on evaluation results


def real_replay_check(sat_id: str, ts: str, before: int = 2, after: int = 6) -> dict:
    dt = _validate(sat_id, ts)
    start, end = _window_bounds(dt, before, after)
    sql = "\n".join(
        [
            "SELECT sat_id, ts, seq, prev_seq, first_seen_ts",
            "FROM (",
            "  SELECT sat_id, ts, seq,",
            "         LAG(seq) OVER (PARTITION BY sat_id ORDER BY " + _cast_col("ts") + ") AS prev_seq,",
            "         MIN(" + _cast_col("ts") + ") OVER (PARTITION BY sat_id, seq) AS first_seen_ts",
            "  FROM " + TABLE,
            "  WHERE sat_id = '" + sat_id + "'",
            ") t",
            "WHERE seq <= prev_seq",
            "  AND " + _in_window(_cast_col("ts"), start, end),
        ]
    )
    sql, rows = _execute(sql)
    n = len(rows)
    summary = str(n) + " row(s) with seq <= prev_seq in window " + start + " .. " + end
    notes = _replay_seen_earlier(rows)
    if notes:
        summary = summary + "; " + "; ".join(notes)
    return {"tool": "replay_check", "source": SOURCE_TELEMETRY, "supports": n > 0,
            "summary": summary, "sql": sql, "rows": rows}


def real_hmac_check(sat_id: str, ts: str, before: int = 2, after: int = 6) -> dict:
    dt = _validate(sat_id, ts)
    start, end = _window_bounds(dt, before, after)
    sql = "\n".join(
        [
            "SELECT COUNT(*) AS n",
            "FROM " + TABLE,
            "WHERE sat_id = '" + sat_id + "'",
            "  AND hmac_valid = 0",
            "  AND " + _in_window(_cast_col("ts"), start, end),
        ]
    )
    sql, rows = _execute(sql)
    n = int(rows[0]["n"]) if rows else 0
    return {"tool": "hmac_check", "source": SOURCE_TELEMETRY, "supports": n > 0,
            "summary": str(n) + " frame(s) with hmac_valid = 0 in window " + start + " .. " + end,
            "sql": sql, "rows": rows}


def real_value_check(sat_id: str, ts: str, before: int = 2, after: int = 6) -> dict:
    dt = _validate(sat_id, ts)
    start, end = _window_bounds(dt, before, after)
    sql = "\n".join(
        [
            "SELECT COUNT(*) AS n,",
            "       MAX(ABS(t.value - s.b_avg)) / NULLIF(MAX(s.b_std), 0) AS max_z,",
            "       MAX(s.b_avg) AS b_avg, MAX(s.b_std) AS b_std",
            "FROM " + TABLE + " t",
            "CROSS JOIN (",
            "  SELECT AVG(value) AS b_avg, STDDEV_SAMP(value) AS b_std",
            "  FROM " + TABLE,
            "  WHERE sat_id = '" + sat_id + "'",
            "    AND NOT (" + _in_window(_cast_col("ts"), start, end) + ")",
            ") s",
            "WHERE t.sat_id = '" + sat_id + "'",
            "  AND " + _in_window(_cast_col("t.ts"), start, end),
        ]
    )
    sql, rows = _execute(sql)
    row = rows[0] if rows else {}
    max_z = float(row["max_z"]) if row.get("max_z") is not None else 0.0
    anomalous = max_z > Z_THRESHOLD
    summary = (
        "real telemetry value: max |z|=" + format(max_z, ".3f")
        + " vs own-channel baseline outside window " + start + " .. " + end
        + "; anomalous=" + str(anomalous) + " (threshold " + str(Z_THRESHOLD) + ")"
    )
    return {"tool": "value_check", "source": SOURCE_TELEMETRY, "supports": anomalous,
            "summary": summary, "sql": sql, "rows": rows}
