import unittest

from satsentinel.decision_memory import record_decision
from satsentinel.memory_agent import apply_memory


def card(v="replay_attack"):
    return {"alert_id": "A-1", "sat_id": "SAT-01", "verdict": v, "confidence": "medium",
            "confidence_reason": "r", "evidence": []}


def ask_returning(content):
    return lambda q: {"memories": [{"id": "m1", "content": content, "relevance": 0.9}]}


class TestDecisionMemory(unittest.TestCase):
    def test_record_writes_tagged_text(self):
        got = []
        self.assertTrue(record_decision(card(), "reject", "bad\nnote", remember_fn=got.append))
        self.assertEqual(got, ["[sat=SAT-01][verdict=replay_attack][decision=reject] A-1: bad note"])

    def test_unknown_and_bad_decision_not_recorded(self):
        got = []
        self.assertFalse(record_decision(card("unknown"), "approve", remember_fn=got.append))
        self.assertFalse(record_decision(card(), "maybe", remember_fn=got.append))
        self.assertEqual(got, [])

    def test_decision_history_shown_but_confidence_unchanged(self):
        c = apply_memory(card(), ask_fn=ask_returning(
            "[sat=SAT-01][verdict=replay_attack][decision=approve] A-9: ok"))
        self.assertEqual(c["confidence"], "medium")
        self.assertEqual(c["memory"], [])
        self.assertEqual(len(c["decision_history"]), 1)
        self.assertEqual(c["decision_history"][0]["decision"], "approve")

    def test_reject_also_unchanged(self):
        c = apply_memory(card(), ask_fn=ask_returning(
            "[sat=SAT-01][verdict=replay_attack][decision=reject] A-9: no"))
        self.assertEqual(c["confidence"], "medium")
        self.assertEqual(c["decision_history"][0]["decision"], "reject")

    def test_analyst_note_still_raises_one_level(self):
        c = apply_memory(card(), ask_fn=ask_returning(
            "[sat=SAT-01][verdict=replay_attack] known maintenance replay"))
        self.assertEqual(c["confidence"], "high")
        self.assertEqual(len(c["memory"]), 1)
        self.assertEqual(c["decision_history"], [])

    def test_other_verdict_ignored(self):
        c = apply_memory(card(), ask_fn=ask_returning(
            "[sat=SAT-01][verdict=spoofing_attack][decision=approve] A-9: x"))
        self.assertEqual(c["decision_history"], [])


if __name__ == "__main__":
    unittest.main()
