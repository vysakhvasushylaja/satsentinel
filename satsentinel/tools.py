"""Evidence tools over Zetaris Spark SQL. Answers are computed from query results."""

import re
from datetime import datetime, timedelta

from satsentinel.zetaris import query

SAT_ID_RE = re.compile(r"^SAT-\d{2}$")
TS_FMT = "%Y-%m-%d %H:%M:%S"


def _validate(sat_id: str, ts: str) -> datetime:
    if not SAT_ID_RE.fullmatch(sat_id):
        raise ValueError(f"invalid sat_id: {sat_id!r}")
    return datetime.strptime(ts, TS_FMT)


def _window_bounds(dt: datetime) -> tuple[str, str]:
    start = (dt - timedelta(minutes=2)).strftime(TS_FMT)
    end = (dt + timedelta(minutes=6)).strftime(TS_FMT)
    return start, end


def _cast(literal: str) -> str:
    return f"CAST('{literal}' AS TIMESTAMP)"


def _in_window(ts_expr: str, start: str, end: str) -> str:
    return f"{ts_expr} BETWEEN {_cast(start)} AND {_cast(end)}"


def replay_check(sat_id: str, ts: str) -> dict:
    dt = _validate(sat_id, ts)
    start, end = _window_bounds(dt)
    sql = f"""
SELECT sat_id, ts, seq, prev_seq
FROM (
  SELECT sat_id, ts, seq,
         LAG(seq) OVER (PARTITION BY sat_id ORDER BY CAST(ts AS TIMESTAMP)) AS prev_seq
  FROM SATSENTINEL.telemetry
  WHERE sat_id = '{sat_id}'
) t
WHERE seq <= prev_seq
  AND {_in_window('CAST(ts AS TIMESTAMP)', start, end)}
""".strip()
    rows = query(sql)
    n = len(rows)
    return {
        "tool": "replay_check",
        "source": "SATSENTINEL.telemetry",
        "supports": n > 0,
        "summary": f"{n} row(s) with seq <= prev_seq in window {start} .. {end}",
        "sql": sql,
        "rows": rows,
    }


def hmac_check(sat_id: str, ts: str) -> dict:
    dt = _validate(sat_id, ts)
    start, end = _window_bounds(dt)
    sql = f"""
SELECT COUNT(*) AS n
FROM SATSENTINEL.telemetry
WHERE sat_id = '{sat_id}'
  AND hmac_valid = 0
  AND {_in_window('CAST(ts AS TIMESTAMP)', start, end)}
""".strip()
    rows = query(sql)
    n = int(rows[0]["n"]) if rows else 0
    return {
        "tool": "hmac_check",
        "source": "SATSENTINEL.telemetry",
        "supports": n > 0,
        "summary": f"{n} frame(s) with hmac_valid = 0 in window {start} .. {end}",
        "sql": sql,
        "rows": rows,
    }


def eclipse_check(sat_id: str, ts: str) -> dict:
    dt = _validate(sat_id, ts)
    ts_lit = dt.strftime(TS_FMT)
    sql = f"""
SELECT sat_id, start_ts, end_ts, event
FROM SATSENTINEL.orbit_events
WHERE sat_id = '{sat_id}'
  AND {_cast(ts_lit)} BETWEEN CAST(start_ts AS TIMESTAMP) AND CAST(end_ts AS TIMESTAMP)
""".strip()
    rows = query(sql)
    inside = len(rows) > 0
    return {
        "tool": "eclipse_check",
        "source": "SATSENTINEL.orbit_events",
        "supports": inside,
        "summary": (
            f"ts {ts_lit} is inside an orbit_events window"
            if inside
            else f"ts {ts_lit} is not inside an orbit_events window"
        ),
        "sql": sql,
        "rows": rows,
    }


def rf_check(sat_id: str, ts: str) -> dict:
    dt = _validate(sat_id, ts)
    start, end = _window_bounds(dt)
    in_w = _in_window("CAST(ts AS TIMESTAMP)", start, end)
    sql = f"""
SELECT
  w_fo, w_rt, w_pn,
  b_fo, b_rt, b_pn,
  s_fo, s_rt, s_pn,
  z_fo, z_rt, z_pn,
  GREATEST(COALESCE(z_fo, 0), COALESCE(z_rt, 0), COALESCE(z_pn, 0)) AS max_z
FROM (
  SELECT
    w_fo, w_rt, w_pn, b_fo, b_rt, b_pn, s_fo, s_rt, s_pn,
    ABS(w_fo - b_fo) / NULLIF(s_fo, 0) AS z_fo,
    ABS(w_rt - b_rt) / NULLIF(s_rt, 0) AS z_rt,
    ABS(w_pn - b_pn) / NULLIF(s_pn, 0) AS z_pn
  FROM (
    SELECT
      AVG(CASE WHEN {in_w} THEN freq_offset_hz END) AS w_fo,
      AVG(CASE WHEN {in_w} THEN rise_time_us END) AS w_rt,
      AVG(CASE WHEN {in_w} THEN phase_noise_db END) AS w_pn,
      AVG(CASE WHEN NOT ({in_w}) THEN freq_offset_hz END) AS b_fo,
      AVG(CASE WHEN NOT ({in_w}) THEN rise_time_us END) AS b_rt,
      AVG(CASE WHEN NOT ({in_w}) THEN phase_noise_db END) AS b_pn,
      STDDEV_SAMP(CASE WHEN NOT ({in_w}) THEN freq_offset_hz END) AS s_fo,
      STDDEV_SAMP(CASE WHEN NOT ({in_w}) THEN rise_time_us END) AS s_rt,
      STDDEV_SAMP(CASE WHEN NOT ({in_w}) THEN phase_noise_db END) AS s_pn
    FROM SATSENTINEL.rf_observations_simulated
    WHERE sat_id = '{sat_id}'
  ) stats
) zscores
""".strip()
    rows = query(sql)
    max_z = float(rows[0]["max_z"]) if rows and rows[0]["max_z"] is not None else 0.0
    mismatch = max_z > 4
    return {
        "tool": "rf_check",
        "source": "SIMULATED RF",
        "supports": mismatch,
        "summary": (
            f"max |z|={max_z:.3f} vs own-sat baseline outside window "
            f"{start} .. {end}; mismatch={mismatch}"
        ),
        "sql": sql,
        "rows": rows,
    }
