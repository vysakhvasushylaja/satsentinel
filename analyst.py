"""Analyst notes into H-MEM:
   python analyst.py note A-002 "text" --verdict eclipse_false_alarm"""
import argparse
import re
import sys
from satsentinel.memory import remember
from satsentinel.zetaris import query

VERDICTS = ("replay_attack", "spoofing_attack", "eclipse_false_alarm")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["note"])
    p.add_argument("alert_id")
    p.add_argument("text")
    p.add_argument("--verdict", required=True, choices=VERDICTS)
    a = p.parse_args()
    if not re.fullmatch(r"A-\d{3}", a.alert_id):
        sys.exit("bad alert id")
    rows = query(f"SELECT sat_id FROM SATSENTINEL.alerts WHERE alert_id = '{a.alert_id}'")
    if not rows:
        sys.exit("alert not found")
    sat = rows[0]["sat_id"]
    r = remember(f"[sat={sat}][verdict={a.verdict}] {a.text}")
    print("remembered", r["id"], "for", sat)


if __name__ == "__main__":
    main()
