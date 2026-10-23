"""Investigate a real-data alert and explain it via Nightshift: python explain_demo.py A-101"""
import json
import sys

from satsentinel.explainer import add_explanation
from satsentinel.real_agents import RealInvestigator

card = RealInvestigator().investigate(sys.argv[1])
add_explanation(card)
print("VERDICT:", card["verdict"], "| CONFIDENCE:", card["confidence"])
print(json.dumps(card["explanation"], indent=2))
