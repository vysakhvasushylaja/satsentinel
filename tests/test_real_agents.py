import unittest
from unittest.mock import patch

from satsentinel import real_agents as ra


def ev(tool, supports, rows=None):
    return {
        "tool": tool,
        "source": "telemetry",
        "supports": supports,
        "summary": tool + " summary",
        "sql": "SELECT 1",
        "rows": rows or [],
    }


def evidence(r=False, h=False, v=False):
    return [ev("replay_check", r), ev("hmac_check", h), ev("value_check", v)]


class Verdicts(unittest.TestCase):
    def test_rules(self):
        cases = [
            (dict(r=True), "replay_attack", "medium"),
            (dict(h=True), "spoofing_attack", "medium"),
            (dict(h=True, v=True), "spoofing_attack", "medium"),
            (dict(v=True), "onboard_fault", "medium"),
            (dict(), "no_threat", "low"),
            (dict(r=True, h=True), "unknown", "low"),
        ]
        for flags, verdict, conf in cases:
            v, c, reason = ra.assess_real(evidence(**flags))
            self.assertEqual((v, c), (verdict, conf), flags)
            self.assertTrue(reason)

    def test_never_high_with_one_source(self):
        for flags in (dict(r=True), dict(h=True, v=True), dict(v=True), dict()):
            self.assertNotEqual(ra.assess_real(evidence(**flags))[1], "high")


class Critique(unittest.TestCase):
    def run_case(self, first, wide_replay=False, wide_hmac=False):
        def rc(sat, ts, before=2, after=6):
            return ev("replay_check", wide_replay if before == 30 else first.get("r", False))

        def hc(sat, ts, before=2, after=6):
            return ev("hmac_check", wide_hmac if before == 30 else first.get("h", False))

        def vc(sat, ts, before=2, after=6):
            return ev("value_check", first.get("v", False))

        inv = ra.RealInvestigator()
        alert = {"alert_id": "A-101", "sat_id": "SAT-04", "ts": "2026-10-02 03:00:00"}
        with patch.object(inv, "_load_alert", return_value=alert), \
                patch.object(ra, "real_replay_check", rc), \
                patch.object(ra, "real_hmac_check", hc), \
                patch.object(ra, "real_value_check", vc):
            return inv.investigate("A-101")

    def test_fault_confirmed_by_wide_window(self):
        card = self.run_case({"v": True})
        self.assertEqual(card["verdict"], "onboard_fault")
        self.assertTrue(card["requires_human_approval"])
        self.assertEqual(card["mode"], "real_data")

    def test_fault_contradicted_by_wide_window(self):
        card = self.run_case({"v": True}, wide_replay=True)
        self.assertEqual((card["verdict"], card["confidence"]), ("unknown", "low"))

    def test_no_threat_contradicted(self):
        card = self.run_case({}, wide_hmac=True)
        self.assertEqual(card["verdict"], "unknown")

    def test_not_found_mentions_missing_sources(self):
        card = self.run_case({})
        self.assertTrue(any("not available for this dataset" in x for x in card["not_found"]))


if __name__ == "__main__":
    unittest.main()
