"""Verdict and confidence rules from fake tool results. No Zetaris, no password."""

import unittest
from unittest.mock import patch

from satsentinel.agents import Finding, Investigator, assess


def ev(tool, source, supports, **extra):
    row = {
        "tool": tool,
        "source": source,
        "supports": supports,
        "summary": extra.get("summary", tool),
        "sql": extra.get("sql", "SELECT 1"),
        "rows": extra.get("rows", []),
    }
    return row


def bundle(r=False, h=False, f=False, e=False, replay_rows=None):
    return [
        ev(
            "replay_check",
            "telemetry",
            r,
            rows=replay_rows or [],
            summary="replay",
        ),
        ev("hmac_check", "telemetry", h, summary="hmac"),
        ev("rf_check", "SIMULATED RF", f, summary="rf"),
        ev("eclipse_check", "orbit", e, summary="eclipse"),
    ]


class TestAssess(unittest.TestCase):
    def test_replay_only_telemetry_is_medium(self):
        verdict, conf, reason = assess(bundle(r=True, h=False, f=False, e=False))
        self.assertEqual(verdict, "replay_attack")
        self.assertEqual(conf, "medium")
        self.assertIn("one independent source (telemetry)", reason)
        self.assertIn("sequence went backwards", reason)
        self.assertIn("RF and orbit show no contradiction", reason)

    def test_spoofing_hmac_and_rf_is_high(self):
        verdict, conf, reason = assess(bundle(r=False, h=True, f=True, e=False))
        self.assertEqual(verdict, "spoofing_attack")
        self.assertEqual(conf, "high")
        self.assertIn("two independent sources (telemetry, SIMULATED RF)", reason)
        self.assertIn("HMAC failures and RF mismatch", reason)
        self.assertIn("orbit shows no contradiction", reason)

    def test_spoofing_hmac_only_is_medium(self):
        verdict, conf, reason = assess(bundle(h=True))
        self.assertEqual(verdict, "spoofing_attack")
        self.assertEqual(conf, "medium")
        self.assertIn("one independent source (telemetry)", reason)
        self.assertIn("HMAC failures", reason)

    def test_spoofing_rf_only_is_medium(self):
        verdict, conf, reason = assess(bundle(f=True))
        self.assertEqual(verdict, "spoofing_attack")
        self.assertEqual(conf, "medium")
        self.assertIn("one independent source (SIMULATED RF)", reason)
        self.assertIn("RF mismatch", reason)

    def test_eclipse_is_medium(self):
        verdict, conf, reason = assess(bundle(e=True))
        self.assertEqual(verdict, "eclipse_false_alarm")
        self.assertEqual(conf, "medium")
        self.assertIn("one independent source (orbit)", reason)
        self.assertIn("inside an", reason)
        self.assertIn("telemetry and RF show no contradiction", reason)

    def test_conflict_is_unknown_low(self):
        verdict, conf, reason = assess(bundle(r=True, h=False, f=True))
        self.assertEqual(verdict, "unknown")
        self.assertEqual(conf, "low")
        self.assertIn("Conflicting evidence", reason)

    def test_no_evidence_is_unknown_low(self):
        verdict, conf, reason = assess(bundle())
        self.assertEqual(verdict, "unknown")
        self.assertEqual(conf, "low")
        self.assertIn("No supporting evidence", reason)

    def test_replay_plus_hmac_failure_is_spoofing_not_replay(self):
        verdict, conf, reason = assess(bundle(r=True, h=True, f=False))
        self.assertEqual(verdict, "spoofing_attack")
        self.assertEqual(conf, "medium")
        self.assertIn("telemetry", reason)

    def test_eclipse_does_not_override_spoofing(self):
        verdict, conf, _ = assess(bundle(h=True, e=True))
        self.assertEqual(verdict, "spoofing_attack")
        self.assertEqual(conf, "medium")


class TestReplayCritique(unittest.TestCase):
    def test_earlier_seq_does_not_re_run_hmac(self):
        replay_rows = [
            {
                "seq": 51,
                "ts": "2026-10-22 04:10:00",
                "first_seen_ts": "2026-10-22 00:50:00",
            }
        ]
        findings = [
            Finding(
                agent="CyberAgent",
                summary="",
                evidence=bundle(r=True, replay_rows=replay_rows)[:2],
            )
        ]
        inv = Investigator()
        with patch(
            "satsentinel.agents.hmac_check",
            side_effect=AssertionError("hmac_check must not be re-run"),
        ):
            critique = inv._critique(
                {"sat_id": "SAT-01", "ts": "2026-10-22 04:10:00"},
                "replay_attack",
                findings,
            )
        self.assertEqual(len(critique), 1)
        self.assertFalse(critique[0]["contradicts"])
        self.assertEqual(critique[0]["check"], "replay_seq_seen_earlier")
        self.assertIn("seq 51 was already seen at 2026-10-22 00:50:00", critique[0]["summary"])

    def test_no_earlier_seq_contradicts(self):
        replay_rows = [
            {
                "seq": 51,
                "ts": "2026-10-22 04:10:00",
                "first_seen_ts": "2026-10-22 04:10:00",
            }
        ]
        findings = [
            Finding(
                agent="CyberAgent",
                summary="",
                evidence=[
                    ev("replay_check", "telemetry", True, rows=replay_rows),
                ],
            )
        ]
        critique = Investigator()._critique(
            {"sat_id": "SAT-01", "ts": "2026-10-22 04:10:00"},
            "replay_attack",
            findings,
        )
        self.assertTrue(critique[0]["contradicts"])


class TestCliVerbose(unittest.TestCase):
    def test_sql_hidden_unless_verbose(self):
        from investigate import format_card

        card = {
            "alert_id": "A-001",
            "sat_id": "SAT-01",
            "ts": "2026-10-22 04:10:00",
            "verdict": "replay_attack",
            "confidence": "medium",
            "confidence_reason": "one independent source (telemetry): sequence went backwards; RF and orbit show no contradiction",
            "recommended_action": "Recommend quarantine of the affected link/session.",
            "requires_human_approval": True,
            "evidence": [
                {
                    "agent": "CyberAgent",
                    "tool": "replay_check",
                    "summary": "seq 51 was already seen at 2026-10-22 00:50:00",
                    "sql": "SELECT sat_id FROM SATSENTINEL.telemetry",
                }
            ],
            "critique": [],
            "not_found": [],
        }
        hidden = format_card(card, verbose=False)
        shown = format_card(card, verbose=True)
        self.assertNotIn("SELECT sat_id FROM SATSENTINEL.telemetry", hidden)
        self.assertIn("SELECT sat_id FROM SATSENTINEL.telemetry", shown)


if __name__ == "__main__":
    unittest.main()
