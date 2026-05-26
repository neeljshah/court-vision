"""tests/test_mobile_html_server.py — R18_K4.

Coverage for the mobile HTML dashboard server:
  1. ``GET /`` renders the source markdown to HTML with tables + auto-refresh.
  2. ``GET /`` returns 404 when the source markdown is missing.
  3. ``GET /api/state`` returns aggregated JSON: bankroll_state, live_bets, lineups.
  4. Bearer-token auth: missing/invalid token => 401, correct token => 200.
  5. ``render_html`` is self-contained — inlines CSS, no external URLs.

Tests use ``aiohttp.test_utils.TestServer`` + ``TestClient`` directly so we
don't need the optional ``pytest-aiohttp`` plugin.
"""
from __future__ import annotations

import asyncio
import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))
sys.path.insert(0, str(PROJECT_DIR / "scripts"))

import mobile_html_server as mhs  # noqa: E402


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #
def _run(coro):
    """Drive an async coro to completion on a fresh event loop."""
    return asyncio.new_event_loop().run_until_complete(coro)


@asynccontextmanager
async def _client_for(app):
    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()
    try:
        yield client
    finally:
        await client.close()


# --------------------------------------------------------------------------- #
# Fixtures                                                                    #
# --------------------------------------------------------------------------- #
@pytest.fixture()
def tmp_layout(tmp_path: Path) -> dict:
    md_path = tmp_path / "TONIGHT.md"
    md_path.write_text(
        "# Tonight — 2026-05-26\n\n"
        "**Bankroll:** $3,670,097.48\n\n"
        "## Top Bets\n\n"
        "| # | Player | Edge% |\n"
        "|---|---|---|\n"
        "| 1 | Wemby | 51.1% |\n"
        "| 2 | Keldon | 40.6% |\n",
        encoding="utf-8",
    )

    bankroll_path = tmp_path / "bankroll_state.json"
    bankroll_path.write_text(
        json.dumps({"bankroll": 3670097.48, "available": 3670097.48}),
        encoding="utf-8",
    )

    live_bets_dir = tmp_path / "live_bets"
    live_bets_dir.mkdir()
    (live_bets_dir / "sas_okc.json").write_text(
        json.dumps({"slate_id": "sas_okc_2026-05-26", "ranked_bets": []}),
        encoding="utf-8",
    )

    lineups_dir = tmp_path / "lineups"
    lineups_dir.mkdir()
    (lineups_dir / "2026-05-26.json").write_text(
        json.dumps({"confirmation": "PROJECTED", "teams": {"OKC": [], "SAS": []}}),
        encoding="utf-8",
    )

    return {
        "md_path": md_path,
        "bankroll_path": bankroll_path,
        "live_bets_dir": live_bets_dir,
        "lineups_dir": lineups_dir,
    }


def _build_app(layout, token=None):
    return mhs.create_app(
        md_path=layout["md_path"],
        bankroll_path=layout["bankroll_path"],
        live_bets_dir=layout["live_bets_dir"],
        lineups_dir=layout["lineups_dir"],
        refresh_sec=30,
        token=token,
    )


# --------------------------------------------------------------------------- #
# Tests                                                                       #
# --------------------------------------------------------------------------- #
def test_index_renders_markdown_to_html(tmp_layout):
    async def _go():
        async with _client_for(_build_app(tmp_layout)) as client:
            resp = await client.get("/")
            assert resp.status == 200
            assert resp.content_type == "text/html"
            body = await resp.text()
            assert "<h1>" in body and "Tonight" in body
            assert "<h2>" in body and "Top Bets" in body
            assert "<table>" in body
            assert "<td>" in body and "Wemby" in body
            assert '<meta http-equiv="refresh" content="30">' in body
            assert "width=device-width" in body

    _run(_go())


def test_index_404_when_markdown_missing(tmp_path):
    app = mhs.create_app(
        md_path=tmp_path / "absent.md",
        bankroll_path=tmp_path / "absent_bankroll.json",
        live_bets_dir=tmp_path / "absent_live",
        lineups_dir=tmp_path / "absent_lineups",
    )

    async def _go():
        async with _client_for(app) as client:
            resp = await client.get("/")
            assert resp.status == 404
            assert "vault markdown missing" in (await resp.text())

    _run(_go())


def test_api_state_returns_aggregated_json(tmp_layout):
    async def _go():
        async with _client_for(_build_app(tmp_layout)) as client:
            resp = await client.get("/api/state")
            assert resp.status == 200
            assert resp.content_type == "application/json"
            data = await resp.json()
            assert set(data.keys()) == {"bankroll_state", "live_bets", "lineups"}
            assert data["bankroll_state"]["bankroll"] == 3670097.48
            assert "sas_okc" in data["live_bets"]
            assert data["live_bets"]["sas_okc"]["slate_id"] == "sas_okc_2026-05-26"
            assert "2026-05-26" in data["lineups"]
            assert data["lineups"]["2026-05-26"]["confirmation"] == "PROJECTED"

    _run(_go())


def test_bearer_token_required_when_set(tmp_layout):
    async def _go():
        async with _client_for(_build_app(tmp_layout, token="s3cr3t")) as client:
            # No header -> 401
            resp = await client.get("/")
            assert resp.status == 401
            assert resp.headers.get("WWW-Authenticate") == "Bearer"

            # Wrong header -> 401
            resp = await client.get("/", headers={"Authorization": "Bearer wrong"})
            assert resp.status == 401

            # Correct header -> 200
            resp = await client.get("/", headers={"Authorization": "Bearer s3cr3t"})
            assert resp.status == 200

            # /api/state also gated
            resp = await client.get("/api/state")
            assert resp.status == 401
            resp = await client.get(
                "/api/state", headers={"Authorization": "Bearer s3cr3t"}
            )
            assert resp.status == 200

            # Query-string token works (phone convenience)
            resp = await client.get("/?token=s3cr3t")
            assert resp.status == 200

            # /healthz always open even with auth on
            resp = await client.get("/healthz")
            assert resp.status == 200
            assert (await resp.text()) == "OK"

    _run(_go())


def test_render_html_is_self_contained():
    html = mhs.render_html("# Hello\n\nWorld.", auto_refresh_sec=15)
    assert html.startswith("<!DOCTYPE html>")
    assert "<h1>" in html and "Hello" in html
    assert 'content="15"' in html
    # No external assets — must be safe to serve over a private tunnel
    assert "http://" not in html
    assert "https://" not in html
    # CSS is inlined
    assert "<style>" in html and "font-family" in html


def test_collect_state_handles_missing_dirs(tmp_path):
    state = mhs.collect_state(
        bankroll_path=tmp_path / "absent.json",
        live_bets_dir=tmp_path / "absent_live",
        lineups_dir=tmp_path / "absent_lineups",
    )
    assert state == {"bankroll_state": None, "live_bets": {}, "lineups": {}}
