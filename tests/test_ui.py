import json
import os
import tempfile
import unittest
import ui


class UiHelpers(unittest.TestCase):
    def test_alert_id_validation(self):
        self.assertTrue(ui.valid_alert_id("A-001"))
        for bad in ("A-1", "a-001", "A-001; DROP", "../x", "", "A-0011"):
            self.assertFalse(ui.valid_alert_id(bad), bad)

    def test_decision_record(self):
        card = {"alert_id": "A-002", "verdict": "eclipse_false_alarm", "confidence": "high"}
        rec = ui.build_decision(card, "approve", "x" * 900)
        self.assertEqual(rec["decision"], "approve")
        self.assertEqual(len(rec["note"]), 500)
        with self.assertRaises(ValueError):
            ui.build_decision(card, "delete", "")

    def test_write_decision_appends_json_lines(self):
        card = {"alert_id": "A-001", "verdict": "replay_attack", "confidence": "medium"}
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "decisions.jsonl")
            ui.write_decision(ui.build_decision(card, "reject", "n"), path)
            ui.write_decision(ui.build_decision(card, "approve", ""), path)
            lines = open(path, encoding="utf-8").read().splitlines()
            self.assertEqual([json.loads(x)["decision"] for x in lines], ["reject", "approve"])


if __name__ == "__main__":
    unittest.main()
