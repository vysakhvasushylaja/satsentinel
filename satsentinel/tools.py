"""Evidence tools over Zetaris Spark SQL. Answers are computed from query results."""

import re
from datetime import datetime, timedelta

from satsentinel.zetaris import query

SAT_ID_RE = re.compile(r"^SAT-\d{2}$")
TS_FMT = "%Y-%m-%d %H:%M:%S"
SOURCE_TELEMETRY = "telemetry"
SOURCE_RF = "SIMULATED RF"
SOURCE_ORBIT = "orbit"
# Runtime spaces so "AS"/"TIMESTAMP", "inside"/"an", "already"/"seen" cannot glue.
AS_TIMESTAMP = "AS" + " " + "TIMESTAMP"
INSIDE_AN = "inside" + " " + "an"
ALREADY_SEEN = "already" + " " + "seen"


def format_ts(raw) -> str:
    text = str(raw).strip().replace("T", " ").replace("Z", "")
    text = text.split(".")[0][:19]
    return datetime.strptime(text, TS_FMT).strftime(TS_FMT)


def _validate(sat_id: str, ts: str) -> datetime:
    if not SAT_ID_RE.fullmatch(sat_id):
        raise ValueError(f"invalid sat_id: {sat_id!r}")
    return datetime.strptime(ts, TS_FMT)


def _window_bounds(dt: datetime, before: int = 2, after: int = 6) -> tuple[str, str]:
    start = (dt - timedelta(minutes=before)).strftime(TS_FMT)
    end = (dt + timedelta(minutes=after)).strftime(TS_FMT)
    return start, end


def _cast(literal: str) -> str:
    return "CAST('" + literal + "' " + AS_TIMESTAMP + ")"


def _cast_col(expr: str) -> str:
    return "CAST(" + expr + " " + AS_TIMESTAMP + ")"


def _in_window(ts_expr: str, start: str, end: str) -> str:
    return ts_expr + " BETWEEN " + _cast(start) + " AND " + _cast(end)


def _execute(sql: str) -> tuple[str, list[dict]]:
    """Run one statement. Returned sql is exactly the string passed to query()."""
    rows = query(sql)
    return sql, rows


def _replay_seen_earlier(rows: list[dict]) -> list[str]:
    notes = []
    seen = set()
    for row in rows:
        seq = row.get("seq")
        first_raw, ts_raw = row.get("first_seen_ts"), row.get("ts")
        if seq is None or first_raw is None or ts_raw is None:
            continue
        first = datetime.strptime(format_ts(first_raw), TS_FMT)
        ts = datetime.strptime(format_ts(ts_raw), TS_FMT)
        key = (str(seq), first.strftime(TS_FMT))
        if key in seen:
            continue
        seen.add(key)
        if first < ts:
            notes.append("seq " + str(seq) + " was " + ALREADY_SEEN + " at " + first.strftime(TS_FMT))
        else:
            notes.append("seq " + str(seq) + " was not seen earlier for this satellite")
    return notes


def replay_check(sat_id: str, ts: str, before: int = 2, after: int = 6) -> dict:
    dt = _validate(sat_id, ts)
    start, end = _window_bounds(dt, before, after)
    sql = "\n".join(
        [
            "SELECT sat_id, ts, seq, prev_seq, first_seen_ts",
            "FROM (",
            "  SELECT sat_id, ts, seq,",
            "         LAG(seq) OVER (PARTITION BY sat_id ORDER BY " + _cast_col("ts") + ") AS prev_seq,",
            "         MIN(" + _cast_col("ts") + ") OVER (PARTITION BY sat_id, seq) AS first_seen_ts",
            "  FROM SATSENTINEL.telemetry",
            "  WHERE sat_id = '" + sat_id + "'",
            ") t",
            "WHERE seq <= prev_seq",
            "  AND " + _in_window(_cast_col("ts"), start, end),
        ]
    )
    sql, rows = _execute(sql)
    n = len(rows)
    summary = f"{n} row(s) with seq <= prev_seq in window {start} .. {end}"
    notes = _replay_seen_earlier(rows)
    if notes:
        summary = summary + "; " + "; ".join(notes)
    return {
        "tool": "replay_check",
        "source": SOURCE_TELEMETRY,
        "supports": n > 0,
        "summary": summary,
        "sql": sql,
        "rows": rows,
    }


def hmac_check(sat_id: str, ts: str, before: int = 2, after: int = 6) -> dict:
    dt = _validate(sat_id, ts)
    start, end = _window_bounds(dt, before, after)
    sql = "\n".join(
        [
            "SELECT COUNT(*) AS n",
            "FROM SATSENTINEL.telemetry",
            "WHERE sat_id = '" + sat_id + "'",
            "  AND hmac_valid = 0",
            "  AND " + _in_window(_cast_col("ts"), start, end),
        ]
    )
    sql, rows = _execute(sql)
    n = int(rows[0]["n"]) if rows else 0
    return {
        "tool": "hmac_check",
        "source": SOURCE_TELEMETRY,
        "supports": n > 0,
        "summary": f"{n} frame(s) with hmac_valid = 0 in window {start} .. {end}",
        "sql": sql,
        "rows": rows,
    }


def eclipse_check(sat_id: str, ts: str, before: int = 2, after: int = 6) -> dict:
    # Orbit membership is at the alert timestamp; before/after are accepted
    # for a uniform tool signature and do not change this check.
    del before, after
    dt = _validate(sat_id, ts)
    ts_lit = dt.strftime(TS_FMT)
    sql = "\n".join(
        [
            "SELECT sat_id, start_ts, end_ts, event",
            "FROM SATSENTINEL.orbit_events",
            "WHERE sat_id = '" + sat_id + "'",
            "  AND " + _cast(ts_lit) + " BETWEEN " + _cast_col("start_ts") + " AND " + _cast_col("end_ts"),
        ]
    )
    sql, rows = _execute(sql)
    inside = len(rows) > 0
    if inside:
        summary = "ts " + ts_lit + " is " + INSIDE_AN + " orbit_events window"
    else:
        summary = "ts " + ts_lit + " is not " + INSIDE_AN + " orbit_events window"
    return {
        "tool": "eclipse_check",
        "source": SOURCE_ORBIT,
        "supports": inside,
        "summary": summary,
        "sql": sql,
        "rows": rows,
    }


def rf_check(sat_id: str, ts: str, before: int = 2, after: int = 6) -> dict:
    dt = _validate(sat_id, ts)
    start, end = _window_bounds(dt, before, after)
    in_w = _in_window(_cast_col("ts"), start, end)
    sql = "\n".join(
        [
            "SELECT",
            "  w_fo, w_rt, w_pn,",
            "  b_fo, b_rt, b_pn,",
            "  s_fo, s_rt, s_pn,",
            "  z_fo, z_rt, z_pn,",
            "  GREATEST(COALESCE(z_fo, 0), COALESCE(z_rt, 0), COALESCE(z_pn, 0)) AS max_z",
            "FROM (",
            "  SELECT",
            "    w_fo, w_rt, w_pn, b_fo, b_rt, b_pn, s_fo, s_rt, s_pn,",
            "    ABS(w_fo - b_fo) / NULLIF(s_fo, 0) AS z_fo,",
            "    ABS(w_rt - b_rt) / NULLIF(s_rt, 0) AS z_rt,",
            "    ABS(w_pn - b_pn) / NULLIF(s_pn, 0) AS z_pn",
            "  FROM (",
            "    SELECT",
            "      AVG(CASE WHEN " + in_w + " THEN freq_offset_hz END) AS w_fo,",
            "      AVG(CASE WHEN " + in_w + " THEN rise_time_us END) AS w_rt,",
            "      AVG(CASE WHEN " + in_w + " THEN phase_noise_db END) AS w_pn,",
            "      AVG(CASE WHEN NOT (" + in_w + ") THEN freq_offset_hz END) AS b_fo,",
            "      AVG(CASE WHEN NOT (" + in_w + ") THEN rise_time_us END) AS b_rt,",
            "      AVG(CASE WHEN NOT (" + in_w + ") THEN phase_noise_db END) AS b_pn,",
            "      STDDEV_SAMP(CASE WHEN NOT (" + in_w + ") THEN freq_offset_hz END) AS s_fo,",
            "      STDDEV_SAMP(CASE WHEN NOT (" + in_w + ") THEN rise_time_us END) AS s_rt,",
            "      STDDEV_SAMP(CASE WHEN NOT (" + in_w + ") THEN phase_noise_db END) AS s_pn",
            "    FROM SATSENTINEL.rf_observations_simulated",
            "    WHERE sat_id = '" + sat_id + "'",
            "  ) stats",
            ") zscores",
        ]
    )
    sql, rows = _execute(sql)
    max_z = float(rows[0]["max_z"]) if rows and rows[0]["max_z"] is not None else 0.0
    mismatch = max_z > 4
    return {
        "tool": "rf_check",
        "source": SOURCE_RF,
        "supports": mismatch,
        "summary": (
            "max |z|=" + f"{max_z:.3f}" + " vs own-sat baseline outside window "
            + start + " .. " + end + "; mismatch=" + str(mismatch)
        ),
        "sql": sql,
        "rows": rows,
    }
