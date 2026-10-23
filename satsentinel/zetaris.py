"""Zetaris JDBC access for SatSentinel. Password is read only from the environment."""

import os

import jaydebeapi

JAR = "/home/vyshu/zetaris-platform/jdbc/ndp-jdbc-driver-2.4.3.1-7eff043-driver.jar"
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
    _conn = jaydebeapi.connect(CLASS, URL, [user, password], JAR)
    return _conn


def _query_raw(sql: str) -> list[dict]:
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
    _trace.emit("zetaris_query", sql=sql, rows=len(rows), ms=int((_time.time() - t0) * 1000))
    return rows
