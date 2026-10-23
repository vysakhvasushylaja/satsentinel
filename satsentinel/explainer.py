"""ExplainerAgent: explains a finished case card in plain language.
The LLM can only explain. It cannot change verdict or confidence."""
import re

from satsentinel import nightshift
from satsentinel.counterfactual import counterfactuals

SYSTEM = (
    "You explain satellite security alert investigations to a human analyst. "
    "Use ONLY the numbered evidence given. Cite evidence as [E1], [E2]. "
    "Do not add facts. Do not change the verdict or confidence. "
    "Say what could not be checked. If lines under 'What would change the verdict' are given, "
    "add one sentence using only those lines and their citations. Maximum 6 sentences."
)


def _as_list(x):
    if not x:
        return []
    return x if isinstance(x, list) else [x]


def _facts(card):
    lines = [
        "Verdict: %s" % card["verdict"],
        "Confidence: %s (%s)" % (card["confidence"], card["confidence_reason"]),
    ]
    for i, e in enumerate(card["evidence"], 1):
        lines.append("[E%d] %s: %s" % (i, e["agent"], e["summary"]))
    for c in _as_list(card.get("critique")):
        lines.append("Self-critique: %s" % c)
    for n in _as_list(card.get("not_found")):
        lines.append("Not found: %s" % n)
    cf = counterfactuals(card)
    if cf:
        lines.append("What would change the verdict (computed by the rules, not by you):")
        lines.extend("- " + c for c in cf)
    return "\n".join(lines)


def _template(card):
    parts = ["Verdict: %s (confidence: %s)." % (card["verdict"], card["confidence"])]
    for i, e in enumerate(card["evidence"], 1):
        parts.append("[E%d] %s" % (i, e["summary"]))
    parts.extend(counterfactuals(card)[:2])
    return " ".join(parts)


def explain(card, chat=None):
    chat = chat or nightshift.chat
    try:
        r = chat(
            [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": _facts(card)},
            ]
        )
        text = r["text"]
        cited = set(re.findall(r"\[E(\d+)\]", text))
        valid = {str(i) for i in range(1, len(card["evidence"]) + 1)}
        if not text or text.rstrip()[-1] not in '.!?' or not cited or not cited <= valid:
            raise ValueError("explanation not grounded in evidence")
        return {
            "text": text,
            "source": "llm",
            "model": r["model"],
            "receipt_id": r["receipt_id"],
            "latency_ms": r["latency_ms"],
        }
    except Exception as ex:
        return {"text": _template(card), "source": "template", "reason": str(ex)[:200]}


def add_explanation(card, chat=None):
    card["explanation"] = explain(card, chat)
    return card
