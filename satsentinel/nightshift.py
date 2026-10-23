"""Minimal Nightshift (Meterless) client. Stdlib only."""
import json
import os
import time
import urllib.request

BASE = os.environ.get("METERLESS_BASE_URL", "http://127.0.0.1:8088/v1")
MODEL = os.environ.get("METERLESS_MODEL", "nvidia/nemotron-3-ultra-550b-a55b")


def chat(messages, max_tokens=800, timeout=60):
    token = os.environ.get("METERLESS_RUNTIME_TOKEN", "")
    body = json.dumps(
        {"model": MODEL, "messages": messages, "max_tokens": max_tokens}
    ).encode()
    req = urllib.request.Request(
        BASE + "/chat/completions",
        data=body,
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
        },
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.load(r)
    text = data["choices"][0]["message"]["content"] or ""
    if "</think>" in text:
        text = text.split("</think>")[-1]
    meta = data.get("meterless", {})
    return {
        "text": text.strip(),
        "model": data.get("model", MODEL),
        "latency_ms": int((time.time() - t0) * 1000),
        "receipt_id": meta.get("receipt_id"),
    }
