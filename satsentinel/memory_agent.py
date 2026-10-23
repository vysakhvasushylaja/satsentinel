"""Applies analyst memory (H-MEM) to a finished case card.
Memory is PRIOR KNOWLEDGE supplied by an analyst, not an observation:
 - it never creates or changes a verdict;
 - it only matters when BOTH its sat and verdict tags match the data-driven verdict;
 - it raises confidence by at most one level, and the reason names the memory id."""
import re
from .memory import MemoryUnavailable, ask

TAG = re.compile(
    r"^\[sat=([^\]]+)\]\[verdict=([^\]]+)\](?:\[decision=(approve|reject)\])?\s*(.*)$", re.S)
LEVELS = ["low", "medium", "high"]


def apply_memory(card, ask_fn=ask):
    card = dict(card)
    if card["verdict"] == "unknown":
        card["memory"] = []
        card["decision_history"] = []
        return card
    try:
        result = ask_fn(f"{card['sat_id']} {card['verdict']}")
    except MemoryUnavailable as e:
        card["memory"] = "unavailable"
        card["memory_reason"] = str(e)
        return card
    matches = []
    history = []
    for m in result.get("memories", []):
        t = TAG.match(m["content"])
        if t and t.group(1) == card["sat_id"] and t.group(2) == card["verdict"]:
            if t.group(3):  # a recorded human decision: shown, never changes confidence
                history.append({"id": m["id"], "decision": t.group(3), "text": t.group(4)})
            else:
                matches.append({"id": m["id"], "text": t.group(4), "relevance": m["relevance"]})
    card["memory"] = matches
    card["decision_history"] = history
    if matches and card["confidence"] in LEVELS[:-1]:
        card["confidence"] = LEVELS[LEVELS.index(card["confidence"]) + 1]
        ids = ", ".join(m["id"] for m in matches)
        card["confidence_reason"] += (
            f"; raised one level by analyst memory {ids} (analyst-provided, not an observation)")
    return card
