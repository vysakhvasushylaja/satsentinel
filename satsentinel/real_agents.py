"""Investigation for the REAL-data scenario (no LLM, transparent rules).

Data: real NASA SMAP/MSL telemetry values; seq/HMAC metadata and attacks are injected.
Only ONE independent source exists here (telemetry): no RF or orbit data for these channels.

Evidence flags (tool supports)
    R  replay_check: seq <= prev_seq in the window
    H  hmac_check: a frame with hmac_valid = 0 in the window
    V  value_check: real telemetry value beyond 3 sigma of the channel baseline

Verdict rules (in this order)
    1. R and H -> unknown (conflicting cyber signals)
    2. H       -> spoofing_attack
    3. R       -> replay_attack
    4. V       -> onboard_fault (anomalous values, valid HMAC, no replay: not a cyber attack)
    5. else    -> no_threat

Confidence: one source only, so never above medium. no_threat is low.
Self-critique: onboard_fault / no_threat re-check replay and HMAC in a +-30 min window;
replay_attack checks that the replayed seq was seen earlier. Contradiction -> unknown/low.
The investigator only recommends; a human must approve.
"""
from __future__ import annotations

import re

from satsentinel.agents import Finding, _critique_ev, _evidence_rows, _replay_first_seen_notes
from satsentinel.real_tools import real_hmac_check, real_replay_check, real_value_check
from satsentinel.tools import SOURCE_TELEMETRY, format_ts
from satsentinel.zetaris import query

ALERT_ID_RE = re.compile(r"^A-\d{3}$")
DATA_NOTE = (
    "Real NASA SMAP/MSL telemetry values; seq/HMAC metadata and attacks are injected "
    "and labelled. RF and orbit evidence are not available for this dataset."
)
ACTIONS = {
    "replay_attack": "Recommend quarantine of the affected link/session.",
    "spoofing_attack": "Recommend isolating the link and re-keying.",
    "onboard_fault": "Recommend routing to spacecraft operations as an onboard anomaly; no cyber action.",
    "no_threat": "Recommend closing as a false alarm after human review.",
    "unknown": "Recommend human review; do not auto-close or auto-quarantine.",
}


def _flags(evidence):
    by = {ev["tool"]: ev for ev in evidence if "tool" in ev}

    def get(name):
        return bool(by.get(name, {}).get("supports"))

    return get("replay_check"), get("hmac_check"), get("value_check")


def verdict_real(r, h, v):
    if r and h:
        return "unknown"
    if h:
        return "spoofing_attack"
    if r:
        return "replay_attack"
    if v:
        return "onboard_fault"
    return "no_threat"


def assess_real(evidence):
    r, h, v = _flags(evidence)
    verdict = verdict_real(r, h, v)
    one = "one independent source (" + SOURCE_TELEMETRY + "): "
    if verdict == "unknown":
        return verdict, "low", (
            "Conflicting cyber evidence: replay signature together with HMAC failures; "
            "human review needed."
        )
    if verdict == "replay_attack":
        return verdict, "medium", one + "sequence went backwards; no HMAC failure"
    if verdict == "spoofing_attack":
        extra = " and anomalous values" if v else ""
        return verdict, "medium", one + "HMAC failures" + extra
    if verdict == "onboard_fault":
        return verdict, "medium", (
            one + "telemetry values are anomalous while HMAC is valid and no sequence was "
            "replayed; consistent with an onboard fault rather than a cyber attack"
        )
    return verdict, "low", (
        "No replay, HMAC or value evidence in the window; absence of evidence in a single "
        "source is not proof of safety"
    )


def _not_found(r, h, v):
    items = []
    if not r:
        items.append("replay_check did not find seq <= prev_seq in the window")
    if not h:
        items.append("hmac_check found no frames with hmac_valid = 0 in the window")
    if not v:
        items.append("value_check found no real telemetry values beyond the 3-sigma threshold")
    items.append(
        "rf_check and eclipse_check are not available for this dataset (no RF or orbit data)"
    )
    return items


class RealCyberAgent:
    name = "CyberAgent"

    def run(self, alert):
        replay = real_replay_check(alert["sat_id"], alert["ts"])
        hmac = real_hmac_check(alert["sat_id"], alert["ts"])
        return Finding(
            agent=self.name,
            summary=replay["summary"] + "; " + hmac["summary"],
            evidence=[replay, hmac],
        )


class RealTelemetryAgent:
    name = "TelemetryAgent"

    def run(self, alert):
        val = real_value_check(alert["sat_id"], alert["ts"])
        return Finding(agent=self.name, summary=val["summary"], evidence=[val])


class RealInvestigator:
    def __init__(self):
        self.cyber = RealCyberAgent()
        self.telemetry = RealTelemetryAgent()

    def _load_alert(self, alert_id):
        if not ALERT_ID_RE.fullmatch(alert_id):
            raise ValueError("invalid alert_id: " + repr(alert_id))
        rows = query(
            "SELECT alert_id, sat_id, ts FROM SATSENTINEL.alerts_real WHERE alert_id = '"
            + alert_id
            + "'"
        )
        if not rows:
            raise KeyError("alert not found: " + alert_id)
        row = rows[0]
        return {
            "alert_id": str(row["alert_id"]).strip(),
            "sat_id": str(row["sat_id"]).strip(),
            "ts": format_ts(row["ts"]),
        }

    def _critique(self, alert, verdict, findings):
        sat_id, ts = alert["sat_id"], alert["ts"]
        if verdict in ("onboard_fault", "no_threat"):
            replay = real_replay_check(sat_id, ts, before=30, after=30)
            hmac = real_hmac_check(sat_id, ts, before=30, after=30)
            hit = [
                name
                for name, ev in (("replay_check", replay), ("hmac_check", hmac))
                if ev["supports"]
            ]
            if hit:
                summary = (
                    "Wider window (+-30 min) found cyber evidence: "
                    + ", ".join(hit)
                    + ". The first verdict ("
                    + verdict
                    + ") may be wrong."
                )
            elif verdict == "onboard_fault":
                summary = (
                    "Wider window (+-30 min) replay/HMAC checks found no cyber evidence; "
                    "an attack hiding behind the fault is not supported."
                )
            else:
                summary = (
                    "Wider window (+-30 min) replay/HMAC checks found no cyber evidence; "
                    "no threat remains consistent with the data."
                )
            return [
                {
                    "check": "wider_window_cyber",
                    "summary": summary,
                    "contradicts": bool(hit),
                    "evidence": [_critique_ev(replay), _critique_ev(hmac)],
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
            if earlier:
                summary = "Replay corroborated: " + "; ".join(earlier)
            elif not_earlier:
                summary = (
                    "Replay not corroborated: the replayed seq was not seen earlier ("
                    + "; ".join(not_earlier)
                    + ")."
                )
            else:
                summary = "Replay not corroborated: no earlier occurrence of the replayed seq was found."
            return [
                {
                    "check": "replay_seq_seen_earlier",
                    "summary": summary,
                    "contradicts": not earlier,
                    "evidence": [_critique_ev(replay)],
                }
            ]
        return []

    def investigate(self, alert_id):
        alert = self._load_alert(alert_id)
        findings = [self.cyber.run(alert), self.telemetry.run(alert)]
        evidence = [ev for f in findings for ev in f.evidence]
        verdict, confidence, reason = assess_real(evidence)
        r, h, v = _flags(evidence)
        critique = self._critique(alert, verdict, findings)
        if any(item.get("contradicts") for item in critique):
            why = "; ".join(i["summary"] for i in critique if i.get("contradicts"))
            verdict, confidence = "unknown", "low"
            reason = "Self-critique contradicted the first verdict. " + why
        return {
            "alert_id": alert["alert_id"],
            "sat_id": alert["sat_id"],
            "ts": alert["ts"],
            "mode": "real_data",
            "data_note": DATA_NOTE,
            "verdict": verdict,
            "confidence": confidence,
            "confidence_reason": reason,
            "evidence": _evidence_rows(findings),
            "critique": critique,
            "not_found": _not_found(r, h, v),
            "recommended_action": ACTIONS[verdict],
            "requires_human_approval": True,
        }
