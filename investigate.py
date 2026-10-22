"""CLI: python investigate.py A-001 | python investigate.py --all [--verbose]"""

from __future__ import annotations

import argparse
import textwrap

from satsentinel.agents import Investigator
from satsentinel.memory_agent import apply_memory
from satsentinel.zetaris import query


def _format_base(card: dict, verbose: bool = False) -> str:
    lines = [
        f"=== Case {card['alert_id']} ===",
        f"sat_id: {card['sat_id']}",
        f"ts: {card['ts']}",
        f"verdict: {card['verdict']}",
        f"confidence: {card['confidence']}",
        f"confidence_reason: {card['confidence_reason']}",
        f"recommended_action: {card['recommended_action']}",
        f"requires_human_approval: {card['requires_human_approval']}",
        "",
        "Evidence:",
    ]
    for ev in card["evidence"]:
        lines.append(f"  [{ev['agent']} / {ev['tool']}] {ev['summary']}")
        if verbose:
            lines.append(textwrap.indent(str(ev["sql"]).strip(), "    "))
            lines.append("")
    if not verbose:
        lines.append("")
    lines.append("Critique:")
    if not card["critique"]:
        lines.append("  (no extra self-critique rule for this verdict)")
    for item in card["critique"]:
        flag = "CONTRADICTS" if item.get("contradicts") else "ok"
        lines.append(f"  [{flag}] {item['check']}: {item['summary']}")
        for ev in item.get("evidence") or []:
            lines.append(f"    - {ev['tool']} supports={ev['supports']} {ev['summary']}")
            if verbose:
                lines.append(textwrap.indent(str(ev["sql"]).strip(), "      "))
    lines.append("")
    lines.append("Not found:")
    if not card["not_found"]:
        lines.append("  (all four tools reported support)")
    for item in card["not_found"]:
        lines.append(f"  - {item}")
    return "\n".join(lines)


def format_memory(card: dict) -> str:
    mem = card.get("memory")
    if mem is None:
        return ""
    if mem == "unavailable":
        return "memory: unavailable (decision made from data only)"
    if not mem:
        return "memory: no matching analyst note"
    lines = ["memory (analyst-provided prior knowledge, not an observation):"]
    for m in mem:
        lines.append(f"  - {m['id']}: {m['text']}")
    return "\n".join(lines)


def format_card(card: dict, verbose: bool = False) -> str:
    base = _format_base(card, verbose=verbose)
    extra = format_memory(card)
    return base + ("\n" + extra if extra else "")


def main() -> None:
    parser = argparse.ArgumentParser(description="Investigate SatSentinel alerts")
    parser.add_argument("alert_id", nargs="?", help="alert id, e.g. from SATSENTINEL.alerts")
    parser.add_argument("--all", action="store_true", help="investigate every alert")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="print the SQL that was executed",
    )
    args = parser.parse_args()
    if bool(args.all) == bool(args.alert_id):
        parser.error("provide an alert_id or --all")

    investigator = Investigator()
    if args.all:
        alerts = query("SELECT alert_id FROM SATSENTINEL.alerts")
        cards = [apply_memory(investigator.investigate(str(row["alert_id"]).strip())) for row in alerts]
        print("\n\n".join(format_card(card, verbose=args.verbose) for card in cards))
        return
    print(format_card(apply_memory(investigator.investigate(args.alert_id)), verbose=args.verbose))


if __name__ == "__main__":
    main()
