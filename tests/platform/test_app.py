"""test_app.py — self-contained honest frontend app (NO network, NO slow loads).

Uses create_app(repo_root=tmp_path, feed=StubFeed(mode="empty")) so
build_all_board returns empty lists per sport (corpora absent under tmp_path) and
no feed ever touches the network — the fast path the spec prescribes.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.platformkit.frontend import app as app_module  # noqa: E402
from scripts.platformkit.frontend.app import create_app  # noqa: E402
from scripts.platformkit.frontend.board import _SPORT_REGISTRY  # noqa: E402
from scripts.platformkit.frontend.feed import OddsFeed, StubFeed  # noqa: E402

_BANNED = ("guaranteed", "profit", "beat the market", "+ev edge", "lock")


@pytest.fixture()
def client(tmp_path):
    app = create_app(repo_root=tmp_path, feed=StubFeed(mode="empty"))
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _no_banned(text: str) -> None:
    low = text.lower()
    for bad in _BANNED:
        assert bad not in low, f"banned substring {bad!r} present in payload"


def test_healthz_ok(client) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["feed"] == "stub"
    assert body["live"] is False


def test_feed_status_not_configured(client) -> None:
    r = client.get("/api/feed/status")
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is False
    assert body["blocked"]
    assert any("ODDS_API_KEY" in step for step in body["blocked"])


def test_board_endpoint_has_banner_and_no_edge_claim(client) -> None:
    r = client.get("/api/board")
    assert r.status_code == 200
    body = r.json()
    assert "no model edge" in body["_banner"].lower()
    _no_banned(r.text)


def test_board_all_sports_keys(client) -> None:
    r = client.get("/api/board")
    assert r.status_code == 200
    board = r.json()["board"]
    assert set(board.keys()) == set(_SPORT_REGISTRY.keys())


def test_board_unknown_sport_error_not_500(client) -> None:
    r = client.get("/api/board/not_a_sport")
    assert r.status_code == 200  # graceful, not 500
    body = r.json()
    assert "error" in body
    assert "note" in body


def test_board_html_served(client) -> None:
    r = client.get("/board.html")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "markets are efficient" in r.text.lower()


def test_arb_clv_dormant_without_feed(client) -> None:
    for path in ("/api/arb", "/api/clv"):
        r = client.get(path)
        assert r.status_code == 200, f"{path} returned {r.status_code}"
        body = r.json()
        assert body["status"] == "dormant"
        assert body["rows"] == []


def test_ev_endpoint_empty_with_stub(client) -> None:
    r = client.get("/api/ev")
    assert r.status_code == 200
    body = r.json()
    assert body["rows"] == []
    assert "note" in body


def test_create_app_injectable_feed_is_live_flag(tmp_path) -> None:
    class _FakeLive(OddsFeed):
        name = "fake-live"
        note = "fake live note"

        def fetch(self, sport, *, date=None):
            return []

        def is_live(self):
            return True

    app = create_app(repo_root=tmp_path, feed=_FakeLive())
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/healthz")
        assert r.status_code == 200
        assert r.json()["live"] is True


def test_app_separate_from_api_main() -> None:
    assert app_module.app.title.startswith("Honest Board")
    # The module must not pull in the human's live app: no `import api.main`
    # in the source (a docstring textual reference is fine), and api.main must
    # not be bound into the module namespace.
    import ast

    src = Path(app_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    imported: set = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert "api.main" not in imported
    assert not any(m.startswith("api.main") for m in imported)
    assert not hasattr(app_module, "main") or app_module.main.__module__ != "api.main"
