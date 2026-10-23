"""Counterfactuals: which single change in the evidence would change the verdict.
Computed by the same rules that decide the verdict. The LLM only puts them into words."""
from satsentinel.agents import _verdict
from satsentinel.real_agents import verdict_real

_SYN = {
    "R": ("replay_check", "a replayed sequence number"),
    "H": ("hmac_check", "an HMAC failure"),
    "F": ("rf_check", "an RF mismatch (simulated RF)"),
    "E": ("eclipse_check", "the alert falling inside an eclipse window"),
}
_REAL = {
    "R": ("replay_check", "a replayed sequence number"),
    "H": ("hmac_check", "an HMAC failure"),
    "V": ("value_check", "real telemetry values beyond 3 sigma"),
}


def _rule(flags, real):
    if real:
        return verdict_real(flags["R"], flags["H"], flags["V"])
    return _verdict(flags["R"], flags["H"], flags["F"], flags["E"])


def counterfactuals(card, limit=4):
    flags = card.get("flags")
    if not flags:
        return []
    real = card.get("mode") == "real_data"
    table = _REAL if real else _SYN
    base = _rule(flags, real)
    index = {e.get("tool"): i for i, e in enumerate(card.get("evidence", []), 1)}
    out = []
    for key, (tool, desc) in table.items():
        if key not in flags or tool not in index:
            continue
        flipped = dict(flags)
        flipped[key] = not flags[key]
        new = _rule(flipped, real)
        if new == base:
            continue
        had = "had not been found" if flags[key] else "had also been found"
        out.append("If %s %s [E%d], the rules would give %s instead of %s."
                   % (desc, had, index[tool], new, base))
    return out[:limit]
