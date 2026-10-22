"""Investigate alerts from the real-data scenario: python investigate_real.py A-101"""
import argparse

from investigate import format_card
from satsentinel.real_agents import RealInvestigator


def main():
    p = argparse.ArgumentParser()
    p.add_argument("alert_id")
    a = p.parse_args()
    print(format_card(RealInvestigator().investigate(a.alert_id)))


if __name__ == "__main__":
    main()
