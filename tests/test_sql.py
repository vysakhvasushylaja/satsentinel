"""SQL round-trip tests. No Zetaris, no password."""

import unittest
from unittest.mock import patch

from satsentinel.tools import eclipse_check, hmac_check, replay_check, rf_check


def _assert_sql_spacing(test, sql: str) -> None:
    test.assertIn("AS TIMESTAMP", sql)
    test.assertNotIn("ASTIMESTAMP", sql.replace("AS TIMESTAMP", ""))
    test.assertNotIn("insidean", sql)


class TestSqlRoundTrip(unittest.TestCase):
    def _run(self, fn, fake_rows):
        executed = []

        def fake_query(sql):
            executed.append(sql)
            return fake_rows

        with patch("satsentinel.tools.query", fake_query):
            result = fn("SAT-01", "2026-10-22 04:10:00")
        self.assertEqual(len(executed), 1)
        self.assertEqual(result["sql"], executed[0])
        _assert_sql_spacing(self, result["sql"])
        return result

    def test_replay_reported_sql_equals_executed(self):
        rows = [
            {
                "sat_id": "SAT-01",
                "ts": "2026-10-22 04:10:00",
                "seq": 51,
                "prev_seq": 250,
                "first_seen_ts": "2026-10-22 00:50:00",
            }
        ]
        result = self._run(replay_check, rows)
        self.assertEqual(result["source"], "telemetry")
        self.assertIn("seq 51 was already seen at 2026-10-22 00:50:00", result["summary"])
        self.assertIn("first_seen_ts", result["sql"])
        self.assertIn("CAST(ts AS TIMESTAMP)", result["sql"])

    def test_hmac_reported_sql_equals_executed(self):
        result = self._run(hmac_check, [{"n": 0}])
        self.assertEqual(result["source"], "telemetry")
        self.assertFalse(result["supports"])

    def test_eclipse_reported_sql_equals_executed_and_summary_spacing(self):
        result = self._run(eclipse_check, [])
        self.assertEqual(result["source"], "orbit")
        self.assertIn("inside an", result["summary"])
        self.assertNotIn("insidean", result["summary"].replace("inside an", ""))
        self.assertIn("not inside an", result["summary"])

        inside = self._run(eclipse_check, [{"sat_id": "SAT-01"}])
        self.assertTrue(inside["supports"])
        self.assertIn("inside an", inside["summary"])
        self.assertNotIn("not inside an", inside["summary"])

    def test_rf_reported_sql_equals_executed(self):
        result = self._run(rf_check, [{"max_z": 0.3}])
        self.assertEqual(result["source"], "SIMULATED RF")
        self.assertIn("AS TIMESTAMP", result["sql"])
        self.assertIn("COALESCE(z_pn, 0)", result["sql"])


if __name__ == "__main__":
    unittest.main()
