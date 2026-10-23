"""Minimal Nightshift (Meterless) client. Stdlib only."""
import json
import os
import time
import urllib.request

BASE = os.environ.get("METERLESS_BASE_URL", "http://127.0.0.1:8088/v1")
MODEL = os.environ.get("METERLESS_MODEL", "nvidia/nemotron-3-ultra-550b-a55b")


def _chat_raw(messages, max_tokens=2000, timeout=90):
    token = os.environ.get("METERLESS_RUNTIME_TOKEN", "")
    body = json.dumps(
        {"model": MODEL, "messages": messages, "max_tokens": max_tokens}
    ).encode()
    req = urllib.request.Request(
        BASE + "/chat/completions",
        data=body,
        headers={
            "Authorization": "Bearer " + token,
            "meterless-app": "satsentinel",
            "meterless-scope": "user",
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


from satsentinel import trace as _trace  # noqa: E402


def chat(messages, max_tokens=2000, timeout=90):
    chars = sum(len(m.get("content", "")) for m in messages)
    try:
        r = _chat_raw(messages, max_tokens, timeout)
    except Exception as ex:
        _trace.emit("nightshift_error", model=MODEL, prompt_chars=chars, error=str(ex)[:200])
        raise
    _trace.emit(
        "nightshift_request",
        model=r["model"],
        prompt_chars=chars,
        latency_ms=r["latency_ms"],
        receipt_id=r["receipt_id"],
    )
    return r
