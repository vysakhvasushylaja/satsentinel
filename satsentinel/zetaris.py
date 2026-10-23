"""Zetaris JDBC access for SatSentinel. Password is read only from the environment."""

import os

JAR = os.environ.get(
    "ZETARIS_JDBC_JAR",
    "/home/vyshu/zetaris-platform/jdbc/ndp-jdbc-driver-2.4.3.1-7eff043-driver.jar",
)
URL = "jdbc:zetaris:lightning@localhost:10000"
CLASS = "com.zetaris.lightning.jdbc.LightningDriver"

_conn = None


def _connection():
    global _conn
    if _conn is not None:
        return _conn
    password = os.environ.get("ZETARIS_PASSWORD")
    if not password:
        raise RuntimeError("ZETARIS_PASSWORD is not set")
    user = os.environ.get("ZETARIS_USER", "admin@zetaris.com")
    import jaydebeapi

    _conn = jaydebeapi.connect(CLASS, URL, [user, password], JAR)
    return _conn


def _query_raw(sql: str) -> list[dict]:
    if os.environ.get("SAMPLE_MODE") == "1":
        return _sample_query(sql)
    cur = _connection().cursor()
    try:
        cur.execute(sql)
        cols = [str(d[0]).lower() for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    finally:
        cur.close()


import time as _time  # noqa: E402

from satsentinel import trace as _trace  # noqa: E402


def query(sql: str) -> list[dict]:
    t0 = _time.time()
    rows = _query_raw(sql)
    _trace.emit("zetaris_query", sql=sql, rows=len(rows), engine=("duckdb-sample" if os.environ.get("SAMPLE_MODE") == "1" else "zetaris"), ms=int((_time.time() - t0) * 1000))
    return rows


# ---- SAMPLE_MODE: same SQL, DuckDB over the CSV files, no Zetaris needed ----
_SAMPLE_TABLES = [
    "telemetry", "alerts", "orbit_events", "rf_observations_simulated",
    "telemetry_real", "alerts_real",
]
_duck = None


def _ensure_sample_data(data_dir):
    import subprocess
    import sys

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    for csv_name, script in (("telemetry.csv", "make_data.py"), ("telemetry_real.csv", "make_data_real.py")):
        if not os.path.exists(os.path.join(data_dir, csv_name)):
            subprocess.run([sys.executable, script], cwd=root, check=True, stdout=subprocess.DEVNULL)


def _sample_conn():
    global _duck
    if _duck is not None:
        return _duck
    import duckdb

    data_dir = os.environ.get("SATSENTINEL_DATA_DIR", "data")
    _ensure_sample_data(data_dir)
    con = duckdb.connect(":memory:")
    con.execute("CREATE SCHEMA SATSENTINEL")
    for t in _SAMPLE_TABLES:
        path = os.path.join(data_dir, t + ".csv")
        if not os.path.exists(path):
            continue
        con.execute("CREATE VIEW SATSENTINEL.%s AS SELECT * FROM read_csv_auto('%s')" % (t, path))
    _duck = con
    return con


def _sample_query(sql):
    cur = _sample_conn().execute(sql)
    cols = [str(d[0]).lower() for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]
