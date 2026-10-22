import unittest
from satsentinel.memory import MemoryUnavailable
from satsentinel.memory_agent import apply_memory


def card(verdict="eclipse_false_alarm", conf="medium"):
    return {"sat_id": "SAT-02", "verdict": verdict, "confidence": conf, "confidence_reason": "base"}


def fake(memories):
    return lambda q: {"memories": memories}


GOOD = {"id": "mem-1", "content": "[sat=SAT-02][verdict=eclipse_false_alarm] dips are normal", "relevance": 0.5}


class MemoryRules(unittest.TestCase):
    def test_matching_memory_raises_one_level(self):
        c = apply_memory(card(), fake([GOOD]))
        self.assertEqual(c["confidence"], "high")
        self.assertIn("mem-1", c["confidence_reason"])
        self.assertIn("not an observation", c["confidence_reason"])
        self.assertEqual(c["memory"][0]["id"], "mem-1")

    def test_wrong_sat_or_verdict_ignored(self):
        other = [
            {"id": "mem-2", "content": "[sat=SAT-01][verdict=eclipse_false_alarm] x", "relevance": 0.5},
            {"id": "mem-3", "content": "[sat=SAT-02][verdict=replay_attack] x", "relevance": 0.5},
            {"id": "mem-4", "content": "untagged note about SAT-02", "relevance": 0.5},
        ]
        c = apply_memory(card(), fake(other))
        self.assertEqual(c["confidence"], "medium")
        self.assertEqual(c["memory"], [])

    def test_memory_never_creates_a_verdict(self):
        c = apply_memory(card("unknown", "low"), fake([GOOD]))
        self.assertEqual(c["verdict"], "unknown")
        self.assertEqual(c["confidence"], "low")

    def test_never_above_high(self):
        c = apply_memory(card(conf="high"), fake([GOOD]))
        self.assertEqual(c["confidence"], "high")

    def test_unavailable_falls_back(self):
        def boom(q):
            raise MemoryUnavailable("no node")
        c = apply_memory(card(), boom)
        self.assertEqual(c["memory"], "unavailable")
        self.assertEqual(c["confidence"], "medium")


if __name__ == "__main__":
    unittest.main()
