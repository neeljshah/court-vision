"""test_intel_panel.py — Unit tests for scripts.platformkit.frontend.intel_panel.

Uses a synthetic tmp fixture brain (archetype/scheme/trend notes +
a _World_Model note + a NBA/_Digest.md).  No real vault is touched.
"""
from __future__ import annotations

import re
import textwrap
from pathlib import Path
from typing import Generator

import pytest

from scripts.platformkit.frontend.intel_panel import (
    attach_intel_routes,
    build_intel_panel,
    normalize_sport,
    render_intel_html,
)

# ── fixture helpers ───────────────────────────────────────────────────────────
_ARCH = textwrap.dedent("""\
    ---\ntags: [archetype, organized]\n---\n# High-Usage Scorer
    archetype: "High-Usage Scorer"\n**Usage**: high\n## Stat Signature\n- pts/g: 25+
""")
_SCH = textwrap.dedent("""\
    ---\ntags: [scheme, organized]\n---\n# Switch-Everything Defense
    scheme: "Switch-Everything Defense"\n**Coverage**: all screens switched
""")
_TRD = textwrap.dedent("""\
    ---\ntags: [trend, organized]\n---\n# Three-Point Explosion Trend
    trend: "Three-Point Explosion Trend"\n**Pattern**: 3PA per game rising
""")
_WM = textwrap.dedent("""\
    # _World_Model\nmarket_efficiency: efficient\ntested_signals: REJECT
    edge_claimed: False\nno edge claimed; markets efficient; calibration not edge
""")
_DIGEST = textwrap.dedent("""\
    ---\ntags: [organized, digest]\n---\n# NBA — Dense Intelligence Digest
    ## Counts\n\n- **Teams / entities tracked:** 30\n- **Archetypes:** 5
    - **Schemes / tactical notes:** 3\n- **Trend notes:** 2
""")


@pytest.fixture()
def fixture_root(tmp_path: Path) -> Generator[Path, None, None]:
    org = tmp_path / "_Organized"
    nba = org / "NBA"
    for subdir, name, content in [
        ("Archetypes", "high_usage_scorer.md", _ARCH),
        ("Schemes", "switch_everything.md", _SCH),
        ("Trends", "three_point_explosion.md", _TRD),
    ]:
        d = nba / subdir; d.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(content, encoding="utf-8")
    (org / "_World_Model.md").write_text(_WM, encoding="utf-8")
    (nba / "_Digest.md").write_text(_DIGEST, encoding="utf-8")
    yield org


# ── normalize_sport ───────────────────────────────────────────────────────────
class TestNormalizeSport:
    def test_basketball_nba(self) -> None:
        assert normalize_sport("basketball_nba") == "nba"

    def test_mlb_sbro(self) -> None:
        assert normalize_sport("mlb_sbro") == "mlb"

    def test_soccer_epl(self) -> None:
        assert normalize_sport("soccer_epl") == "soccer"

    def test_tennis_atp(self) -> None:
        assert normalize_sport("tennis_atp") == "tennis"

    def test_case_insensitive(self) -> None:
        assert normalize_sport("NBA") == "nba"
        assert normalize_sport("TENNIS_WTA") == "tennis"

    def test_unknown_passthrough(self) -> None:
        result = normalize_sport("cricket_ipl")
        assert isinstance(result, str)


# ── build_intel_panel ─────────────────────────────────────────────────────────
class TestBuildIntelPanel:
    def test_normalises_sport(self, fixture_root: Path) -> None:
        assert build_intel_panel("basketball_nba", root=fixture_root)["sport"] == "nba"

    def test_banner_contains_no_model_edge(self, fixture_root: Path) -> None:
        panel = build_intel_panel("basketball_nba", root=fixture_root)
        assert "no model edge" in panel["banner"].lower()

    def test_edge_claimed_false(self, fixture_root: Path) -> None:
        assert build_intel_panel("basketball_nba", root=fixture_root)["edge_claimed"] is False

    def test_read_is_dict(self, fixture_root: Path) -> None:
        assert isinstance(build_intel_panel("basketball_nba", root=fixture_root)["read"], dict)

    def test_no_top_level_pick_key(self, fixture_root: Path) -> None:
        panel = build_intel_panel("basketball_nba", root=fixture_root)
        forbidden = {"pick", "bet", "roi", "edge_pct", "ev", "kelly", "odds", "probability"}
        assert not {k.lower() for k in panel.keys()} & forbidden

    def test_digest_counts(self, fixture_root: Path) -> None:
        digest = build_intel_panel("basketball_nba", root=fixture_root).get("digest", {})
        if digest:  # only assert when parsing succeeded
            assert digest.get("archetypes") == 5
            assert digest.get("teams") == 30
            assert digest.get("schemes") == 3
            assert digest.get("trends") == 2

    def test_provenance_is_list(self, fixture_root: Path) -> None:
        assert isinstance(build_intel_panel("basketball_nba", root=fixture_root)["provenance"], list)

    def test_read_edge_claimed_false(self, fixture_root: Path) -> None:
        assert build_intel_panel("basketball_nba", root=fixture_root)["read"].get("edge_claimed") is False


# ── render_intel_html ─────────────────────────────────────────────────────────
_ROI_RE = re.compile(r"\broi\s*[:=]\s*[\d.]+", re.I)
_EDGE_PCT_RE = re.compile(r"edge\s*%", re.I)
_EV_PICK_RE = re.compile(r"\+\s*(?:EV|ROI|edge)\s*(?:pick|bet|%|\d)", re.I)


class TestRenderIntelHtml:
    def _panel(self, fixture_root: Path) -> dict:
        return build_intel_panel("basketball_nba", root=fixture_root)

    def test_contains_no_model_edge(self, fixture_root: Path) -> None:
        assert "NO model edge" in render_intel_html(self._panel(fixture_root))

    def test_contains_archetypes(self, fixture_root: Path) -> None:
        assert "Archetypes" in render_intel_html(self._panel(fixture_root))

    def test_no_roi_claim(self, fixture_root: Path) -> None:
        assert not _ROI_RE.search(render_intel_html(self._panel(fixture_root)))

    def test_no_edge_pct(self, fixture_root: Path) -> None:
        assert not _EDGE_PCT_RE.search(render_intel_html(self._panel(fixture_root)))

    def test_no_ev_pick(self, fixture_root: Path) -> None:
        assert not _EV_PICK_RE.search(render_intel_html(self._panel(fixture_root)))

    def test_valid_html_structure(self, fixture_root: Path) -> None:
        out = render_intel_html(self._panel(fixture_root))
        assert "<!DOCTYPE html>" in out and "</html>" in out


# ── attach_intel_routes ───────────────────────────────────────────────────────
class TestAttachIntelRoutes:
    def test_registers_three_paths(self) -> None:
        from fastapi import FastAPI  # noqa: PLC0415
        app = FastAPI(); attach_intel_routes(app)
        paths = {r.path for r in app.routes}  # type: ignore[attr-defined]
        assert "/api/intel" in paths
        assert "/api/intel/{sport}" in paths
        assert "/intel/{sport}.html" in paths

    def test_testclient_index(self) -> None:
        try:
            from fastapi import FastAPI  # noqa: PLC0415
            from fastapi.testclient import TestClient  # noqa: PLC0415
        except ImportError:
            pytest.skip("fastapi/testclient unavailable")
        app = FastAPI(); attach_intel_routes(app)
        r = TestClient(app).get("/api/intel")
        assert r.status_code == 200
        assert r.json().get("edge_claimed") is False

    def test_testclient_sport_json(self) -> None:
        try:
            from fastapi import FastAPI  # noqa: PLC0415
            from fastapi.testclient import TestClient  # noqa: PLC0415
        except ImportError:
            pytest.skip("fastapi/testclient unavailable")
        app = FastAPI(); attach_intel_routes(app)
        r = TestClient(app).get("/api/intel/nba")
        assert r.status_code == 200
        data = r.json()
        assert data.get("edge_claimed") is False
        assert data.get("sport") == "nba"

    def test_testclient_html(self) -> None:
        try:
            from fastapi import FastAPI  # noqa: PLC0415
            from fastapi.testclient import TestClient  # noqa: PLC0415
        except ImportError:
            pytest.skip("fastapi/testclient unavailable")
        app = FastAPI(); attach_intel_routes(app)
        r = TestClient(app).get("/intel/nba.html")
        assert r.status_code == 200
        assert "NO model edge" in r.text
