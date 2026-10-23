import unittest

from satsentinel.explainer import add_explanation, explain

CARD = {
    "verdict": "replay_attack",
    "confidence": "high",
    "confidence_reason": "two independent sources agree",
    "evidence": [
        {"agent": "CyberAgent", "summary": "seq 41 seen earlier at 10:02"},
        {"agent": "RFAgent", "summary": "RF fingerprint matches SAT-03"},
    ],
    "critique": ["no orbit data checked"],
    "not_found": [],
}


def fake_ok(messages):
    return {"text": "Replay found [E1]; RF agrees [E2].", "model": "m", "receipt_id": "r1", "latency_ms": 5}


def fake_ungrounded(messages):
    return {"text": "Looks bad overall.", "model": "m", "receipt_id": "r2", "latency_ms": 5}


def fake_bad_ref(messages):
    return {"text": "See [E9].", "model": "m", "receipt_id": "r3", "latency_ms": 5}


def fake_error(messages):
    raise TimeoutError("slow")


class TestExplainer(unittest.TestCase):
    def test_llm_path(self):
        out = explain(CARD, fake_ok)
        self.assertEqual(out["source"], "llm")
        self.assertEqual(out["receipt_id"], "r1")

    def test_ungrounded_falls_back(self):
        self.assertEqual(explain(CARD, fake_ungrounded)["source"], "template")

    def test_bad_reference_falls_back(self):
        self.assertEqual(explain(CARD, fake_bad_ref)["source"], "template")

    def test_error_falls_back(self):
        self.assertEqual(explain(CARD, fake_error)["source"], "template")

    def test_verdict_unchanged(self):
        card = dict(CARD)
        add_explanation(card, fake_ok)
        self.assertEqual(card["verdict"], "replay_attack")
        self.assertEqual(card["confidence"], "high")


    def test_verdict_line_added_by_code(self):
        out = explain(dict(CARD), chat=fake_ok)
        self.assertEqual(out["source"], "llm")
        self.assertTrue(out["text"].startswith("Verdict: replay attack, "))

    def test_verdict_line_not_duplicated(self):
        def chat(messages, **kw):
            return {"text": "Verdict: replay attack, high confidence. Seen [E1].", "model": "m", "receipt_id": "r8", "latency_ms": 5}
        out = explain(dict(CARD), chat=chat)
        self.assertEqual(out["text"].lower().count("verdict:"), 1)


if __name__ == "__main__":
    unittest.main()
