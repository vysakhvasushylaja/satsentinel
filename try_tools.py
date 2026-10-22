"""Run the four evidence tools on every SATSENTINEL.alerts row."""

from datetime import datetime

from satsentinel.tools import eclipse_check, hmac_check, replay_check, rf_check
from satsentinel.zetaris import query

TOOLS = (replay_check, hmac_check, eclipse_check, rf_check)


def _tool_ts(raw) -> str:
    text = str(raw).strip().replace("T", " ").replace("Z", "")
    text = text.split(".")[0][:19]
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d %H:%M:%S")


def main() -> None:
    alerts = query(
        "SELECT alert_id, sat_id, ts, detector, score FROM SATSENTINEL.alerts"
    )
    for alert in alerts:
        sat_id = str(alert["sat_id"]).strip()
        ts = _tool_ts(alert["ts"])
        for tool in TOOLS:
            result = tool(sat_id, ts)
            print(
                f"{alert['alert_id']} {sat_id} {result['tool']} "
                f"supports={result['supports']} {result['summary']}"
            )


if __name__ == "__main__":
    main()
