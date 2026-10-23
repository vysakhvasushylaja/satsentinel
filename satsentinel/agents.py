"""Multi-agent investigation over the four evidence tools (no LLM).

Hypotheses
    replay_attack, spoofing_attack, eclipse_false_alarm, unknown.

Evidence flags (tool ``supports``; no alert ids are hardcoded)
    R  replay_check: seq <= prev_seq in the time window
    H  hmac_check: at least one frame with hmac_valid = 0 in the window
    F  rf_check: SIMULATED RF window vs that satellite's own baseline, max |z| > 4
    E  eclipse_check: alert ts inside an orbit_events window

Verdict rules (transparent; evaluated in this order)
    1. Conflicting evidence -> unknown
       Conflict means a clean-replay signature together with RF mismatch:
       R and not H and F (valid HMAC + old sequence, but SIMULATED RF disagrees).
    2. replay_attack: R and not H
       Valid HMAC but an old sequence number. F is already excluded by (1).
    3. spoofing_attack: H and/or F
       HMAC failures and/or RF mismatch. Both H and F is stronger.
    4. eclipse_false_alarm: E and not R and not H and not F
       In eclipse, and no replay / HMAC / RF attack evidence.
    5. unknown: anything else (including no supporting flags).

Confidence (independent *sources*, not tools)
    Count distinct ``source`` values on tool results: telemetry, SIMULATED RF, orbit.
    replay_check and hmac_check share source 'telemetry' and count as ONE source.
    high   = at least 2 independent sources agree on the verdict and none contradict
    medium = exactly 1 agreeing source and none contradict
    low    = conflict or no support
    A replay_attack backed only by telemetry is medium unless another independent
    source also supports it.
    spoofing_attack: HMAC (telemetry) and RF (SIMULATED RF) are independent; both = high.
    eclipse_false_alarm: orbit is one source (medium).
    confidence_reason names the sources, e.g.
    "one independent source (telemetry): sequence went backwards; RF and orbit show no contradiction".

Self-critique (after the first verdict)
    (a) eclipse_false_alarm: re-run replay / HMAC / RF with before=30, after=30.
        Any supports means an attack may hide behind the eclipse.
    (b) replay_attack: use replay_check first-seen seq (earliest ts with that seq).
        Confirm the replayed seq already appeared earlier. Do not re-run hmac_check.
    (c) Contradicting critique evidence downgrades the verdict to unknown.

The investigator only recommends; a human must approve
    replay_attack       -> recommend quarantine
    spoofing_attack     -> recommend isolating the link and re-keying
    eclipse_false_alarm -> recommend closing as false alarm
    unknown             -> recommend human review
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from satsentinel.tools import (
    ALREADY_SEEN,
    INSIDE_AN,
    SOURCE_ORBIT,
    SOURCE_RF,
    SOURCE_TELEMETRY,
    eclipse_check,
    format_ts,
    hmac_check,
    replay_check,
    rf_check,
)
from satsentinel.zetaris import query

ALERT_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
SOURCE_ORDER = (SOURCE_TELEMETRY, SOURCE_RF, SOURCE_ORBIT)
ACTIONS = {
    "replay_attack": "Recommend quarantine of the affected link/session.",
    "spoofing_attack": "Recommend isolating the link and re-keying.",
    "eclipse_false_alarm": "Recommend closing as false alarm (eclipse).",
    "unknown": "Recommend human review; do not auto-close or auto-quarantine.",
}
DEFAULT_SOURCE = {
    "replay_check": SOURCE_TELEMETRY,
    "hmac_check": SOURCE_TELEMETRY,
    "rf_check": SOURCE_RF,
    "eclipse_check": SOURCE_ORBIT,
}


@dataclass
class Finding:
    agent: str
    summary: str
    evidence: list


def normalize_ts(raw) -> str:
    return format_ts(raw)


def _source(ev: dict) -> str:
    return ev.get("source") or DEFAULT_SOURCE.get(ev.get("tool"), "unknown")


def _by_tool(evidence: list[dict]) -> dict:
    return {ev["tool"]: ev for ev in evidence if "tool" in ev}


def _flags(evidence: list[dict]) -> dict:
    by_tool = _by_tool(evidence)
    return {
        "R": bool(by_tool.get("replay_check", {}).get("supports")),
        "H": bool(by_tool.get("hmac_check", {}).get("supports")),
        "F": bool(by_tool.get("rf_check", {}).get("supports")),
        "E": bool(by_tool.get("eclipse_check", {}).get("supports")),
    }


def _verdict(r: bool, h: bool, f: bool, e: bool) -> str:
    if r and (not h) and f:
        return "unknown"
    if r and not h:
        return "replay_attack"
    if h or f:
        return "spoofing_attack"
    if e:
        return "eclipse_false_alarm"
    return "unknown"


def _agreeing_sources(verdict: str, evidence: list[dict]) -> list[str]:
    by_tool = _by_tool(evidence)
    names = set()
    if verdict == "replay_attack":
        if by_tool.get("replay_check", {}).get("supports"):
            names.add(_source(by_tool["replay_check"]))
    elif verdict == "spoofing_attack":
        hmac = by_tool.get("hmac_check")
        rf = by_tool.get("rf_check")
        if hmac and hmac.get("supports"):
            names.add(_source(hmac))
        if rf and rf.get("supports"):
            names.add(_source(rf))
    elif verdict == "eclipse_false_alarm":
        ecl = by_tool.get("eclipse_check")
        if ecl and ecl.get("supports"):
            names.add(_source(ecl))
    return [s for s in SOURCE_ORDER if s in names]


def _contradicting_sources(verdict: str, r: bool, h: bool, f: bool, e: bool) -> list[str]:
    if verdict == "unknown":
        if r and (not h) and f:
            return [SOURCE_TELEMETRY, SOURCE_RF]
        return []
    if verdict == "replay_attack":
        bad = []
        if f:
            bad.append(SOURCE_RF)
        return bad
    if verdict == "spoofing_attack":
        return []
    if verdict == "eclipse_false_alarm":
        bad = []
        if r or h:
            bad.append(SOURCE_TELEMETRY)
        if f:
            bad.append(SOURCE_RF)
        return bad
    return []


def _source_count_phrase(sources: list[str]) -> str:
    if not sources:
        return "no independent source"
    if len(sources) == 1:
        return f"one independent source ({sources[0]})"
    words = {2: "two", 3: "three"}
    n = words.get(len(sources), str(len(sources)))
    return f"{n} independent sources ({', '.join(sources)})"


def _rf_short(name: str) -> str:
    return "RF" if name == SOURCE_RF else name


def _no_contradiction_clause(agreeing: list[str]) -> str:
    others = [_rf_short(s) for s in SOURCE_ORDER if s not in agreeing]
    if not others:
        return "no remaining source to contradict"
    if len(others) == 1:
        return f"{others[0]} shows no contradiction"
    if len(others) == 2:
        return f"{others[0]} and {others[1]} show no contradiction"
    return f"{others[0]}, {others[1]} and {others[2]} show no contradiction"


def _what_happened(verdict: str, r: bool, h: bool, f: bool, e: bool) -> str:
    if verdict == "replay_attack":
        return "sequence went backwards"
    if verdict == "spoofing_attack":
        bits = []
        if h:
            bits.append("HMAC failures")
        if f:
            bits.append("RF mismatch")
        return " and ".join(bits) if bits else "spoofing evidence"
    if verdict == "eclipse_false_alarm":
        return "ts is " + INSIDE_AN + " orbit_events window"
    if r and (not h) and f:
        return (
            "telemetry shows a valid-HMAC replay signature while SIMULATED RF "
            + "shows a mismatch"
        )
    return "no supporting evidence for replay, spoofing, or eclipse"


def _confidence(verdict: str, evidence: list[dict]) -> tuple[str, str]:
    flags = _flags(evidence)
    r, h, f, e = flags["R"], flags["H"], flags["F"], flags["E"]
    agreeing = _agreeing_sources(verdict, evidence)
    contradicting = _contradicting_sources(verdict, r, h, f, e)
    happened = _what_happened(verdict, r, h, f, e)

    if verdict == "unknown" and r and (not h) and f:
        return (
            "low",
            "Conflicting evidence: " + happened + "; independent sources disagree.",
        )
    if verdict == "unknown":
        return "low", "No supporting evidence for replay, spoofing, or eclipse."
    if contradicting:
        return (
            "low",
            _source_count_phrase(agreeing)
            + ": "
            + happened
            + "; contradicted by "
            + ", ".join(contradicting)
            + ".",
        )
    if len(agreeing) >= 2:
        level = "high"
    elif len(agreeing) == 1:
        level = "medium"
    else:
        level = "low"
    reason = (
        _source_count_phrase(agreeing)
        + ": "
        + happened
        + "; "
        + _no_contradiction_clause(agreeing)
    )
    return level, reason


def assess(evidence: list[dict]) -> tuple[str, str, str]:
    """Verdict, confidence, confidence_reason from fake or real tool result dicts."""
    flags = _flags(evidence)
    verdict = _verdict(flags["R"], flags["H"], flags["F"], flags["E"])
    confidence, reason = _confidence(verdict, evidence)
    return verdict, confidence, reason


def _not_found(r: bool, h: bool, f: bool, e: bool) -> list[str]:
    items = []
    if not r:
        items.append("replay_check did not find seq <= prev_seq in the window")
    if not h:
        items.append("hmac_check found no frames with hmac_valid = 0 in the window")
    if not f:
        items.append(
            "rf_check (SIMULATED RF) found no window vs own-sat baseline mismatch"
        )
    if not e:
        items.append("eclipse_check: ts is not " + INSIDE_AN + " orbit_events window")
    return items


def _evidence_rows(findings: list[Finding]) -> list[dict]:
    rows = []
    for finding in findings:
        for ev in finding.evidence:
            summary = ev["summary"]
            if _source(ev) == SOURCE_RF and "SIMULATED RF" not in summary:
                summary = "SIMULATED RF: " + summary
            rows.append(
                {
                    "agent": finding.agent,
                    "tool": ev["tool"],
                    "summary": summary,
                    "sql": ev["sql"],
                }
            )
    return rows


def _critique_ev(ev: dict) -> dict:
    summary = ev["summary"]
    if _source(ev) == SOURCE_RF and "SIMULATED RF" not in summary:
        summary = "SIMULATED RF: " + summary
    return {
        "tool": ev["tool"],
        "source": _source(ev),
        "supports": bool(ev["supports"]),
        "summary": summary,
        "sql": ev["sql"],
    }


def _replay_first_seen_notes(replay: dict) -> tuple[list[str], list[str]]:
    earlier, not_earlier = [], []
    for row in replay.get("rows") or []:
        seq, first_raw, ts_raw = row.get("seq"), row.get("first_seen_ts"), row.get("ts")
        if seq is None or first_raw is None or ts_raw is None:
            continue
        first = datetime.strptime(format_ts(first_raw), "%Y-%m-%d %H:%M:%S")
        ts = datetime.strptime(format_ts(ts_raw), "%Y-%m-%d %H:%M:%S")
        if first < ts:
            earlier.append(
                "seq " + str(seq) + " was " + ALREADY_SEEN + " at " + first.strftime("%Y-%m-%d %H:%M:%S")
            )
        else:
            not_earlier.append("seq " + str(seq) + " was not seen earlier for this satellite")
    return earlier, not_earlier


class CyberAgent:
    name = "CyberAgent"

    def run(self, alert: dict) -> Finding:
        replay = replay_check(alert["sat_id"], alert["ts"])
        hmac = hmac_check(alert["sat_id"], alert["ts"])
        return Finding(
            agent=self.name,
            summary=f"{replay['summary']}; {hmac['summary']}",
            evidence=[replay, hmac],
        )


class RFAgent:
    name = "RFAgent"

    def run(self, alert: dict) -> Finding:
        rf = rf_check(alert["sat_id"], alert["ts"])
        return Finding(
            agent=self.name,
            summary=f"SIMULATED RF: {rf['summary']}",
            evidence=[rf],
        )


class OrbitAgent:
    name = "OrbitAgent"

    def run(self, alert: dict) -> Finding:
        ecl = eclipse_check(alert["sat_id"], alert["ts"])
        return Finding(
            agent=self.name,
            summary=ecl["summary"],
            evidence=[ecl],
        )


class Investigator:
    def __init__(self) -> None:
        self.cyber = CyberAgent()
        self.rf = RFAgent()
        self.orbit = OrbitAgent()

    def _load_alert(self, alert_id: str) -> dict:
        if not ALERT_ID_RE.fullmatch(alert_id):
            raise ValueError(f"invalid alert_id: {alert_id!r}")
        rows = query(
            "SELECT alert_id, sat_id, ts, detector, score FROM SATSENTINEL.alerts WHERE alert_id = '"
            + alert_id
            + "'"
        )
        if not rows:
            raise KeyError(f"alert not found: {alert_id}")
        row = rows[0]
        return {
            "alert_id": str(row["alert_id"]).strip(),
            "sat_id": str(row["sat_id"]).strip(),
            "ts": normalize_ts(row["ts"]),
            "detector": row.get("detector"),
            "score": row.get("score"),
        }

    def _critique(self, alert: dict, verdict: str, findings: list[Finding]) -> list[dict]:
        sat_id, ts = alert["sat_id"], alert["ts"]
        if verdict == "eclipse_false_alarm":
            replay = replay_check(sat_id, ts, before=30, after=30)
            hmac = hmac_check(sat_id, ts, before=30, after=30)
            rf = rf_check(sat_id, ts, before=30, after=30)
            hit = [
                name
                for name, ev in (
                    ("replay_check", replay),
                    ("hmac_check", hmac),
                    ("rf_check", rf),
                )
                if ev["supports"]
            ]
            contradicts = bool(hit)
            if contradicts:
                summary = (
                    "Wider window (±30 min) found attack evidence during/around eclipse: "
                    + ", ".join(hit)
                    + ". An attack may hide behind the eclipse."
                )
            else:
                summary = (
                    "Wider window (±30 min) replay/HMAC/SIMULATED RF checks did not "
                    + "support an attack hiding behind the eclipse."
                )
            return [
                {
                    "check": "eclipse_wider_window",
                    "summary": summary,
                    "contradicts": contradicts,
                    "evidence": [
                        _critique_ev(replay),
                        _critique_ev(hmac),
                        _critique_ev(rf),
                    ],
                }
            ]
        if verdict == "replay_attack":
            replay = None
            for finding in findings:
                for ev in finding.evidence:
                    if ev.get("tool") == "replay_check":
                        replay = ev
            if replay is None:
                return []
            earlier, not_earlier = _replay_first_seen_notes(replay)
            contradicts = not earlier
            if earlier:
                summary = "Replay corroborated: " + "; ".join(earlier)
            elif not_earlier:
                summary = (
                    "Replay not corroborated: the replayed seq was not seen earlier ("
                    + "; ".join(not_earlier)
                    + ")."
                )
            else:
                summary = (
                    "Replay not corroborated: no earlier occurrence of the replayed "
                    + "seq was found."
                )
            return [
                {
                    "check": "replay_seq_seen_earlier",
                    "summary": summary,
                    "contradicts": contradicts,
                    "evidence": [_critique_ev(replay)],
                }
            ]
        return []

    def investigate(self, alert_id: str) -> dict:
        alert = self._load_alert(alert_id)
        findings = [
            self.cyber.run(alert),
            self.rf.run(alert),
            self.orbit.run(alert),
        ]
        evidence = [ev for finding in findings for ev in finding.evidence]
        verdict, confidence, reason = assess(evidence)
        flags = _flags(evidence)
        critique = self._critique(alert, verdict, findings)
        if any(item.get("contradicts") for item in critique):
            why = "; ".join(
                item["summary"] for item in critique if item.get("contradicts")
            )
            verdict = "unknown"
            confidence = "low"
            reason = f"Self-critique contradicted the first verdict. {why}"
        return {
            "alert_id": alert["alert_id"],
            "sat_id": alert["sat_id"],
            "ts": alert["ts"],
            "verdict": verdict,
            "confidence": confidence,
            "confidence_reason": reason,
            "evidence": _evidence_rows(findings),
            "critique": critique,
            "not_found": _not_found(flags["R"], flags["H"], flags["F"], flags["E"]),
            "flags": flags,
            "recommended_action": ACTIONS[verdict],
            "requires_human_approval": True,
        }
