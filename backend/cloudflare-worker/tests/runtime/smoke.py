"""Runtime smoke test for the chat API.

    uv run python tests/runtime/smoke.py http://localhost:8787   # local: full flow (test key)
    uv run python tests/runtime/smoke.py https://abinaya-chat-api.dentcare-demo.workers.dev

Against production the session step can only check the rejection path (a real session needs a real
Turnstile token from the browser widget). Exits non-zero if any check fails.
"""

from __future__ import annotations

import json
import sys

import httpx

SITE_ORIGIN = "https://abinayagarment.dentcare-demo.workers.dev"


def call(base, method, path, body=None, headers=None):
    content = None if body is None else (body if isinstance(body, bytes) else json.dumps(body))
    resp = httpx.request(
        method,
        base + path,
        content=content,
        headers={"content-type": "application/json", **(headers or {})},
        timeout=60,
    )
    return resp.status_code, dict(resp.headers), resp.text


def sse_events(text):
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n") if ": " in line)
        events.append((lines.get("event"), json.loads(lines.get("data", "null"))))
    return events


def main(base: str) -> int:
    local = "localhost" in base or "127.0.0.1" in base
    failures = []

    def check(name, ok, detail=""):
        print(f"{'PASS' if ok else 'FAIL'}  {name}{'  ' + detail if detail and not ok else ''}")
        if not ok:
            failures.append(name)

    status, _, body = call(base, "GET", "/api/health")
    check("health 200", status == 200 and json.loads(body)["status"] == "ok", body)

    status, _, body = call(base, "GET", "/api/health/ready")
    check("ready 200", status == 200, body)

    status, headers, _ = call(base, "OPTIONS", "/api/chat", headers={"Origin": SITE_ORIGIN})
    if not local:
        allow = {k.lower(): v for k, v in headers.items()}.get("access-control-allow-origin")
        check(
            "CORS preflight for website origin", status == 204 and allow == SITE_ORIGIN, str(status)
        )

    status, _, _ = call(base, "GET", "/api/health", headers={"Origin": "https://evil.example"})
    check("disallowed origin 403", status == 403)

    status, _, body = call(base, "POST", "/api/chat", {"message": "hi"})
    check("chat without session 401", status == 401, body)

    status, _, _ = call(base, "POST", "/api/chat", b"x" * 40_000)
    check("oversized body 413", status == 413)

    status, _, body = call(base, "POST", "/api/session", {"turnstile_token": "invalid-token"})
    if not local:
        check("fake Turnstile token 403", status == 403, body)
        return report(failures)

    # Local only: Cloudflare's test secret accepts any token, so the full flow can run.
    check("session issued", status == 200, body)
    token = json.loads(body).get("session_token", "")
    auth = {"Authorization": f"Bearer {token}"}

    status, _, body = call(base, "POST", "/api/chat", {"message": "hi", "history": "bad"}, auth)
    check("invalid history 422", status == 422, body)

    status, headers, body = call(
        base, "POST", "/api/chat", {"message": "Are you open on Sundays?"}, auth
    )
    ctype = {k.lower(): v for k, v in headers.items()}.get("content-type", "")
    events = sse_events(body) if status == 200 else []
    names = [e[0] for e in events]
    check("chat streams SSE", status == 200 and ctype.startswith("text/event-stream"), body[:200])
    check(
        "event order start -> token+ -> complete",
        bool(names) and names[0] == "start" and names[-1] == "complete" and "token" in names,
        str(names),
    )
    answer = "".join(e[1]["text"] for e in events if e[0] == "token")
    check("answer mentions Sunday", "sunday" in answer.lower(), answer)
    return report(failures)


def report(failures):
    print(f"\n{'ALL CHECKS PASSED' if not failures else f'{len(failures)} FAILED: {failures}'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(
        main(sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8787")
    )
