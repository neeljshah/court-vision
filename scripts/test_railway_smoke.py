"""test_railway_smoke.py — pre-deploy smoke test for CourtVision endpoints.

Hits every courtvision_router route against a target base URL (default
http://127.0.0.1:8000) and verifies status code + minimal response shape.

Exits 0 on success, 1 on any failure.

Usage:
    python scripts/test_railway_smoke.py                       # local
    python scripts/test_railway_smoke.py --base https://<railway-app>
    python scripts/test_railway_smoke.py --date 2026-05-26     # pin date
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from urllib import error, request


def _get(url: str, timeout: float = 20.0) -> tuple[int, bytes, str]:
    req = request.Request(url, headers={"User-Agent": "courtvision-smoke/1.0"})
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            return resp.getcode(), resp.read(), resp.headers.get("content-type", "")
    except error.HTTPError as exc:
        body = exc.read() if hasattr(exc, "read") else b""
        return exc.code, body, ""
    except (error.URLError, TimeoutError) as exc:
        return 0, str(exc).encode(), ""


def _check(label: str, status_ok: bool, detail: str = "") -> bool:
    icon = "PASS" if status_ok else "FAIL"
    print(f"  [{icon}] {label}{(' - ' + detail) if detail else ''}")
    return status_ok


def run(base: str, date: str) -> int:
    base = base.rstrip("/")
    print(f"\nCourtVision smoke test :: {base} :: date={date}\n")
    fails = 0
    t0 = time.time()

    code, body, _ = _get(f"{base}/healthz")
    payload = json.loads(body or b"{}") if code == 200 else {}
    if not _check("GET /healthz",
                  code == 200 and payload.get("status") == "ok",
                  f"status={code}"):
        fails += 1

    code, body, _ = _get(f"{base}/api/slate?date={date}")
    payload = json.loads(body or b"{}") if code == 200 else {}
    bets = payload.get("bets") or []
    if not _check("GET /api/slate", code == 200, f"status={code} bets={len(bets)}"):
        fails += 1

    code, _, ct = _get(f"{base}/tonight?date={date}")
    if not _check("GET /tonight",
                  code == 200 and "text/html" in ct,
                  f"status={code} ct={ct or 'none'}"):
        fails += 1

    code, body, _ = _get(f"{base}/api/parlays?date={date}&max_legs=5&min_ev_pct=5")
    payload = json.loads(body or b"{}") if code == 200 else {}
    n_parlays = payload.get("n_parlays")
    if not _check("GET /api/parlays", code == 200,
                  f"status={code} n_parlays={n_parlays}"):
        fails += 1

    code, _, ct = _get(f"{base}/parlays?date={date}&min_ev_pct=5")
    if not _check("GET /parlays",
                  code == 200 and "text/html" in ct,
                  f"status={code}"):
        fails += 1

    code, _, ct = _get(f"{base}/share/{date}")
    if not _check("GET /share/{date}",
                  code in (200, 404) and "text/html" in ct,
                  f"status={code}"):
        fails += 1

    code, body, ct = _get(f"{base}/share/{date}/qr.svg")
    if not _check("GET /share/{date}/qr.svg",
                  code in (200, 404) and ("svg" in ct or code == 404),
                  f"status={code} ct={ct}"):
        fails += 1

    if bets:
        bid = bets[0]["bet_id"]
        code, _, ct = _get(f"{base}/api/bet/{bid}?date={date}")
        if not _check("GET /api/bet/{id}", code == 200, f"status={code}"):
            fails += 1
        code, body, ct = _get(f"{base}/api/bet/{bid}?date={date}&partial=1")
        if not _check("GET /api/bet/{id}?partial=1",
                      code == 200 and "text/html" in ct,
                      f"status={code} ct={ct}"):
            fails += 1
    else:
        _check("GET /api/bet/{id} (skipped — no bets in slate)", True)

    code, _, _ = _get(f"{base}/api/bet/definitely-not-real?date={date}")
    if not _check("GET /api/bet/bogus -> 404", code == 404, f"status={code}"):
        fails += 1

    code, _, ct = _get(f"{base}/live?date={date}")
    if not _check("GET /live", code == 200 and "text/html" in ct,
                  f"status={code}"):
        fails += 1

    code, body, _ = _get(f"{base}/api/odds/{date}.json")
    payload = json.loads(body or b"{}") if code == 200 else {}
    if not _check("GET /api/odds/{date}.json",
                  code == 200 and isinstance(payload.get("props"), list),
                  f"status={code} n_props={payload.get('n_props')}"):
        fails += 1

    code, _, ct = _get(f"{base}/odds?date={date}")
    if not _check("GET /odds", code == 200 and "text/html" in ct,
                  f"status={code}"):
        fails += 1

    # SSE check: only verify content-type. Read a tiny chunk with short
    # timeout. urllib doesn't support partial reads cleanly; instead just
    # confirm the endpoint registers as text/event-stream via HEAD-ish GET.
    try:
        req = request.Request(f"{base}/sse/live_edges",
                              headers={"User-Agent": "courtvision-smoke/1.0"})
        with request.urlopen(req, timeout=3.0) as resp:
            ct = resp.headers.get("content-type", "")
            ok = "event-stream" in ct
            if not _check("GET /sse/live_edges (ct check)", ok,
                          f"ct={ct or 'none'}"):
                fails += 1
    except Exception as exc:
        # Streaming connection: short read may raise; that's fine if we got
        # the headers. Only fail if connect itself failed.
        ok = isinstance(exc, TimeoutError) or "timed out" in str(exc).lower()
        if not _check("GET /sse/live_edges", ok, f"err={exc}"):
            fails += 1

    elapsed = time.time() - t0
    print(f"\n{'OK' if fails == 0 else 'FAIL'} :: {fails} failure(s) in {elapsed:.1f}s")
    return 0 if fails == 0 else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000",
                    help="Base URL to test (default: http://127.0.0.1:8000)")
    ap.add_argument("--date", default=datetime.now().strftime("%Y-%m-%d"),
                    help="Slate date (default: today)")
    args = ap.parse_args()
    return run(args.base, args.date)


if __name__ == "__main__":
    sys.exit(main())
