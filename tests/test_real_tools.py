import unittest
from unittest.mock import patch

from satsentinel import real_tools as rt


def fake(rows):
    return lambda sql: (sql, rows)


class RealTools(unittest.TestCase):
    def test_hmac_failures_support(self):
        with patch.object(rt, "_execute", fake([{"n": 4}])):
            r = rt.real_hmac_check("SAT-05", "2026-10-02 03:00:00")
        self.assertTrue(r["supports"])
        self.assertEqual(r["source"], "telemetry")
        self.assertIn("telemetry_real", r["sql"])

    def test_hmac_none(self):
        with patch.object(rt, "_execute", fake([{"n": 0}])):
            self.assertFalse(rt.real_hmac_check("SAT-05", "2026-10-02 03:00:00")["supports"])

    def test_value_threshold(self):
        for z, expected in ((4.2, True), (1.1, False), (3.0, False)):
            row = {"n": 9, "max_z": z, "b_avg": 0.0, "b_std": 1.0}
            with patch.object(rt, "_execute", fake([row])):
                r = rt.real_value_check("SAT-04", "2026-10-02 03:00:00")
            self.assertEqual(r["supports"], expected, z)

    def test_missing_baseline_is_not_evidence(self):
        with patch.object(rt, "_execute", fake([{"n": 0, "max_z": None}])):
            self.assertFalse(rt.real_value_check("SAT-04", "2026-10-02 03:00:00")["supports"])

    def test_replay_uses_real_table_and_proper_cast(self):
        with patch.object(rt, "_execute", fake([])):
            r = rt.real_replay_check("SAT-06", "2026-10-02 03:00:00")
        self.assertFalse(r["supports"])
        self.assertIn("telemetry_real", r["sql"])
        self.assertIn(" AS TIMESTAMP)", r["sql"])

    def test_bad_sat_id_rejected(self):
        with self.assertRaises(ValueError):
            rt.real_value_check("SAT-04'; DROP", "2026-10-02 03:00:00")


if __name__ == "__main__":
    unittest.main()
