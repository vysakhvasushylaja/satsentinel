"""Records the human decision in H-MEM so later cases for the same satellite and verdict show it.
Decision history is displayed only. It never changes a verdict or a confidence level."""
from .memory import remember


def record_decision(card, decision, note="", remember_fn=remember):
    if decision not in ("approve", "reject") or card.get("verdict") == "unknown":
        return False
    note = " ".join(str(note or "").split())[:300] or "(no note)"
    remember_fn("[sat=%s][verdict=%s][decision=%s] %s: %s"
                % (card["sat_id"], card["verdict"], decision, card["alert_id"], note))
    return True
