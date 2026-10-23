import unittest

from satsentinel.counterfactual import counterfactuals

EV = [{"tool": t} for t in ("replay_check", "hmac_check", "rf_check", "eclipse_check")]


def card(**flags):
    f = {"R": False, "H": False, "F": False, "E": False}
    f.update(flags)
    return {"flags": f, "evidence": EV}


class TestCounterfactual(unittest.TestCase):
    def test_replay_with_hmac_would_be_spoofing(self):
        cf = counterfactuals(card(R=True))
        self.assertTrue(any("HMAC" in c and "spoofing_attack" in c and "[E2]" in c for c in cf))

    def test_replay_with_rf_would_be_unknown(self):
        cf = counterfactuals(card(R=True))
        self.assertTrue(any("RF" in c and "unknown" in c for c in cf))

    def test_eclipse_cannot_hide_hmac_failure(self):
        cf = counterfactuals(card(E=True))
        self.assertTrue(any("HMAC" in c and "spoofing_attack" in c for c in cf))
        self.assertTrue(any("eclipse" in c and "had not been found" in c and "unknown" in c for c in cf))

    def test_irrelevant_flag_not_listed(self):
        cf = counterfactuals(card(R=True, E=True))
        self.assertFalse(any("falling inside an eclipse window" in c for c in cf))

    def test_no_flags_no_counterfactuals(self):
        self.assertEqual(counterfactuals({"evidence": EV}), [])

    def test_real_mode(self):
        ev = [{"tool": t} for t in ("replay_check", "hmac_check", "value_check")]
        c = {"mode": "real_data", "flags": {"R": False, "H": False, "V": True}, "evidence": ev}
        cf = counterfactuals(c)
        self.assertTrue(any("HMAC" in x and "spoofing_attack" in x for x in cf))


if __name__ == "__main__":
    unittest.main()
