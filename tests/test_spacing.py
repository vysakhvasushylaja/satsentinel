"""Forbidden glued substrings in tool and critique summaries. No Zetaris, no password."""

import unittest
from unittest.mock import patch

from satsentinel.agents import Finding, Investigator
from satsentinel.tools import eclipse_check, hmac_check, replay_check, rf_check

FORBIDDEN = ("insidean", "alreadyseen", "ASTIMESTAMP")
TS = "2026-10-22 04:10:00"
SAT = "SAT-01"


def _assert_clean(test, *texts):
    for text in texts:
        blob = "" if text is None else str(text)
        for bad in FORBIDDEN:
            test.assertNotIn(bad, blob, msg=repr(blob))


class TestForbiddenSubstrings(unittest.TestCase):
    def test_every_tool_summary_and_critique_summary(self):
        replay_rows = [
            {
                "sat_id": SAT,
                "ts": TS,
                "seq": 51,
                "prev_seq": 250,
                "first_seen_ts": "2026-10-22 00:50:00",
            }
        ]
        replay_same = [
            {
                "sat_id": SAT,
                "ts": TS,
                "seq": 51,
                "prev_seq": 250,
                "first_seen_ts": TS,
            }
        ]
        tool_results = []
        with patch("satsentinel.tools.query") as mocked:
            mocked.side_effect = lambda sql: replay_rows
            tool_results.append(replay_check(SAT, TS))
            mocked.side_effect = lambda sql: replay_same
            tool_results.append(replay_check(SAT, TS, before=30, after=30))
            mocked.side_effect = lambda sql: [{"n": 0}]
            tool_results.append(hmac_check(SAT, TS))
            mocked.side_effect = lambda sql: [{"n": 2}]
            tool_results.append(hmac_check(SAT, TS, before=30, after=30))
            mocked.side_effect = lambda sql: []
            tool_results.append(eclipse_check(SAT, TS))
            mocked.side_effect = lambda sql: [{"sat_id": SAT, "event": "eclipse"}]
            tool_results.append(eclipse_check(SAT, "2026-10-22 02:10:00"))
            mocked.side_effect = lambda sql: [{"max_z": 0.3}]
            tool_results.append(rf_check(SAT, TS))
            mocked.side_effect = lambda sql: [{"max_z": 11.5}]
            tool_results.append(rf_check(SAT, TS, before=30, after=30))

        for result in tool_results:
            _assert_clean(self, result["summary"], result["sql"])
            self.assertIn("AS TIMESTAMP", result["sql"])

        inv = Investigator()
        findings_ok = [
            Finding(agent="CyberAgent", summary=tool_results[0]["summary"], evidence=[tool_results[0]])
        ]
        findings_bad = [
            Finding(agent="CyberAgent", summary=tool_results[1]["summary"], evidence=[tool_results[1]])
        ]
        alert = {"sat_id": SAT, "ts": TS}
        critiques = []
        critiques.extend(inv._critique(alert, "replay_attack", findings_ok))
        critiques.extend(inv._critique(alert, "replay_attack", findings_bad))

        with patch("satsentinel.agents.replay_check", return_value=tool_results[2]):
            with patch("satsentinel.agents.hmac_check", return_value=tool_results[3]):
                with patch("satsentinel.agents.rf_check", return_value=tool_results[6]):
                    critiques.extend(inv._critique(alert, "eclipse_false_alarm", []))
        with patch("satsentinel.agents.replay_check", return_value=tool_results[0]):
            with patch("satsentinel.agents.hmac_check", return_value=tool_results[3]):
                with patch("satsentinel.agents.rf_check", return_value=tool_results[7]):
                    critiques.extend(inv._critique(alert, "eclipse_false_alarm", []))

        self.assertTrue(critiques)
        for item in critiques:
            _assert_clean(self, item["summary"])
            for ev in item.get("evidence") or []:
                _assert_clean(self, ev.get("summary"), ev.get("sql"))


if __name__ == "__main__":
    unittest.main()
