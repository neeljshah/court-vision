"""Per-file tests for the in-game SNAPSHOT read-model (Milestone-6 spine).

Covers, with NO network, NO corpus, tmp-dir writes:
  * market_set.build() from a reprice() output -> correct shape, freshness
    invariant (variance field present), no edge_claimed;
  * market_set.build() from an unavailable reprice -> clean unavailable sentinel;
  * market_set.build() with optional game_meta merged (no reserved-key collision);
  * snapshot.write_live + read_live atomic round-trip -> written envelope readable;
  * snapshot.read_live_part assembles per-sport "live" block from all written games;
  * snapshot.read_live on a missing file -> None (never raises);
  * snapshot.read_live_part with no files -> None (caller falls back to live_board);
  * partial/corrupt file -> unavailable sentinel / None (never raises, never tears);
  * edge_claimed is False everywhere (honesty invariant).

Run (per-file ONLY -- full pytest freezes this box):
  cd /c/Users/neelj/nba-ai-system && \
    python -m pytest tests/platformkit/test_ingame_snapshot.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.platformkit.ingame import market_set as ms_mod
from scripts.platformkit.ingame import snapshot as snap_mod
from scripts.platformkit.ingame.state_bus import GameState

# ---- helpers -----------------------------------------------------------------

_PERIOD_LEN = 720.0  # NBA 12-min quarters


def _state(period: int, clock_sec: float, home: int, away: int) -> GameState:
    return GameState(
        sport="nba", game_id="G_TEST", period=period, clock_sec=clock_sec,
        home_score=home, away_score=away, status="live",
        extras={"period_len_sec": _PERIOD_LEN},
    )


_PRIOR = {"p0": 0.52, "variance": 0.25, "regulation_min": 48.0,
          "pregame_params": {"mu_home": 113.0, "mu_away": 113.0}}


def _reprice_like(available: bool = True, basis: str = "blend", **kw: object):
    """Minimal dict that looks like a repricer_router.reprice() output."""
    if not available:
        return {
            "available": False, "sport": "nba", "reason": "missing prior",
            "probs": {}, "markets": [], "variance": None,
            "remaining_frac": None, "basis": "unavailable",
            "edge_claimed": False, "_honest_note": "unavailable",
        }
    base = {
        "available": True, "sport": "nba",
        "probs": {"p_home": 0.61, "p_away": 0.39, "w": 0.40, "p_live": 0.72},
        "markets": [
            {"market": "win_home", "prob": 0.61},
            {"market": "over_224.5", "prob": 0.51},
            {"market": "proj_total", "value": 225.3},
        ],
        "variance": 0.09, "remaining_frac": 0.35,
        "basis": basis, "edge_claimed": False,
        "_honest_note": "test reprice",
    }
    base.update(kw)
    return base


# ===========================================================================
# market_set.build() tests
# ===========================================================================

def test_build_from_available_reprice_has_required_keys():
    rp = _reprice_like(available=True)
    out = ms_mod.build("G1", "nba", rp)
    for key in ("game_id", "sport", "status", "available", "basis", "as_of",
                "edge_claimed", "probs", "markets", "variance", "remaining_frac",
                "_honest_note"):
        assert key in out, f"missing key: {key}"
    assert out["game_id"] == "G1"
    assert out["sport"] == "nba"
    assert out["available"] is True
    assert out["status"] == "live"
    assert out["edge_claimed"] is False


def test_build_probs_block_clamped():
    rp = _reprice_like(available=True)
    out = ms_mod.build("G1", "nba", rp)
    probs = out["probs"]
    assert 0.0 <= probs["p_home"] <= 1.0
    assert 0.0 <= probs["p_away"] <= 1.0
    assert 0.0 <= probs["p_live"] <= 1.0
    assert 0.0 <= probs["w"] <= 1.0


def test_build_markets_list_valid_rows():
    rp = _reprice_like(available=True)
    out = ms_mod.build("G1", "nba", rp)
    markets = out["markets"]
    assert isinstance(markets, list) and len(markets) == 3
    keys_per_row = [set(m.keys()) for m in markets]
    assert {"market", "prob"} in keys_per_row or any("prob" in k for k in keys_per_row)
    for m in markets:
        assert "market" in m
        assert "prob" in m or "value" in m


def test_build_variance_and_remaining_frac():
    rp = _reprice_like(available=True, variance=0.09, remaining_frac=0.35)
    out = ms_mod.build("G1", "nba", rp)
    assert out["variance"] == pytest.approx(0.09)
    assert out["remaining_frac"] == pytest.approx(0.35)


def test_build_unavailable_reprice_gives_sentinel():
    rp = _reprice_like(available=False)
    out = ms_mod.build("G1", "nba", rp)
    assert out["available"] is False
    assert out["status"] == "unavailable"
    assert out["probs"] == {}
    assert out["markets"] == []
    assert out["variance"] is None
    assert out["remaining_frac"] is None
    assert out["edge_claimed"] is False
    assert "reason" in out


def test_build_game_meta_merged_no_collision():
    rp = _reprice_like(available=True)
    meta = {"home_team": "Knicks", "away_team": "Spurs", "tipoff": "21:00 ET"}
    out = ms_mod.build("G1", "nba", rp, game_meta=meta)
    assert out["home_team"] == "Knicks"
    assert out["away_team"] == "Spurs"
    assert out["tipoff"] == "21:00 ET"
    # Reserved keys not overwritten by meta.
    assert out["game_id"] == "G1"
    assert out["edge_claimed"] is False


def test_build_sport_alias_resolved_from_reprice():
    """reprice_output carries the alias-resolved sport; build() honours it."""
    rp = _reprice_like(available=True)
    rp["sport"] = "nba"  # already normalized by repricer
    out = ms_mod.build("G1", "basketball_nba", rp)
    assert out["sport"] == "nba"


def test_build_edge_claimed_always_false():
    """HONESTY invariant: edge_claimed must be False on every output path."""
    assert ms_mod.EDGE_CLAIMED is False
    assert ms_mod.build("G1", "nba", _reprice_like(True))["edge_claimed"] is False
    assert ms_mod.build("G1", "nba", _reprice_like(False))["edge_claimed"] is False


# ===========================================================================
# FIX 2 -- pregame_carry is UNMISTAKABLY marked (reprice=False / is_carry=True)
# WITHOUT a consumer having to read _honest_note, and a real in-game reprice is
# unmistakably the opposite. status stays "live" so the webapp /live classifier
# (keys on status=="live") still treats a carried-prior live game as LIVE.
# ===========================================================================

def test_real_reprice_is_marked_reprice_true_not_carry():
    """A normal in-game reprice (basis != pregame_carry) -> reprice=True/is_carry=False."""
    out = ms_mod.build("G1", "nba", _reprice_like(available=True, basis="blend"))
    assert out["reprice"] is True
    assert out["is_carry"] is False
    assert out["status"] == "live"


def test_pregame_carry_is_unmistakably_marked():
    """A pregame_carry reprice -> reprice=False/is_carry=True, derived from basis
    ALONE (no flag needed on the input) so the marker is unmissable, while status
    stays 'live' (the live page still shows it as LIVE)."""
    carry = {
        "available": True, "sport": "nba",
        "probs": {"p_home": 0.55, "p_away": 0.45, "p_live": 0.55},
        "markets": [], "variance": None, "remaining_frac": None,
        "basis": "pregame_carry", "edge_claimed": False,
        "_honest_note": "UNCHANGED pregame prior, no in-game conditioning",
    }
    out = ms_mod.build("G_CARRY", "mlb", carry)
    # Unmistakable WITHOUT reading the note:
    assert out["reprice"] is False
    assert out["is_carry"] is True
    assert out["basis"] == "pregame_carry"
    # status unchanged so status-based consumers (webapp /live) don't break:
    assert out["status"] == "live"
    assert out["available"] is True
    assert out["edge_claimed"] is False
    # honest note preserved:
    assert "pregame prior" in out["_honest_note"].lower()


def test_explicit_carry_flag_on_input_is_honored():
    """If the repricer ever sets reprice/is_carry directly, build() passes them
    through (basis is the fallback authority, not the only one)."""
    rp = _reprice_like(available=True, basis="blend", reprice=False, is_carry=True)
    out = ms_mod.build("G1", "nba", rp)
    assert out["reprice"] is False and out["is_carry"] is True


def test_unavailable_sentinel_is_neither_reprice_nor_carry():
    out = ms_mod.build("G1", "nba", _reprice_like(available=False))
    assert out["reprice"] is False
    assert out["is_carry"] is False


def test_carry_markers_always_present():
    """reprice + is_carry are GUARANTEED keys on every build() output path."""
    for rp in (_reprice_like(True), _reprice_like(False)):
        out = ms_mod.build("G1", "nba", rp)
        assert "reprice" in out and "is_carry" in out


def test_build_never_raises_on_garbage():
    """Pure fn: garbage input -> unavailable sentinel, never an exception."""
    assert ms_mod.build("G1", "nba", {})["available"] is False
    assert ms_mod.build("G1", "nba", None)["available"] is False  # type: ignore[arg-type]
    assert ms_mod.build("G1", "nba", "not a dict")["available"] is False  # type: ignore[arg-type]


# ===========================================================================
# snapshot.write_live + read_live round-trip tests
# ===========================================================================

def test_write_read_roundtrip(tmp_path):
    """write_live then read_live returns the market_set we wrote."""
    rp = _reprice_like(available=True)
    mset = ms_mod.build("G1", "nba", rp)
    path = snap_mod.write_live("G1", mset, out_dir=tmp_path)
    assert path.exists(), f"snapshot not written: {path}"

    envelope = snap_mod.read_live("G1", sport="nba", out_dir=tmp_path)
    assert envelope is not None
    assert envelope["status"] == "ok"
    ms_back = envelope["market_set"]
    assert ms_back["game_id"] == "G1"
    assert ms_back["sport"] == "nba"
    assert ms_back["probs"]["p_home"] == pytest.approx(mset["probs"]["p_home"])


def test_write_is_atomic_no_tmp_left(tmp_path):
    """After a write, no .tmp file is left on disk (atomic replace succeeded)."""
    mset = ms_mod.build("G1", "nba", _reprice_like())
    snap_mod.write_live("G1", mset, out_dir=tmp_path)
    tmps = list(tmp_path.rglob("*.tmp"))
    assert tmps == [], f"stale .tmp files: {tmps}"


def test_write_updates_latest_index(tmp_path):
    """write_live also updates _latest.json index for the sport."""
    mset = ms_mod.build("G7", "nba", _reprice_like())
    snap_mod.write_live("G7", mset, out_dir=tmp_path)
    latest_path = tmp_path / "nba" / "_latest.json"
    assert latest_path.exists()
    with latest_path.open("r", encoding="utf-8") as fh:
        idx = json.load(fh)
    assert "G7" in idx["games"]


def test_write_multiple_games_index_has_all(tmp_path):
    """Multiple write_live calls accumulate in the index."""
    for gid in ("G1", "G2", "G3"):
        mset = ms_mod.build(gid, "nba", _reprice_like())
        snap_mod.write_live(gid, mset, out_dir=tmp_path)
    ids = snap_mod.list_live_game_ids("nba", out_dir=tmp_path)
    assert set(ids) == {"G1", "G2", "G3"}


def test_read_live_missing_file_returns_none(tmp_path):
    """read_live on a game that was never written -> None, no exception."""
    result = snap_mod.read_live("NO_SUCH_GAME", sport="nba", out_dir=tmp_path)
    assert result is None


def test_read_live_corrupt_file_returns_none(tmp_path):
    """A corrupt (non-JSON) snapshot file -> None, never raises."""
    sport_dir = tmp_path / "nba"
    sport_dir.mkdir(parents=True, exist_ok=True)
    bad = sport_dir / "BAD_GAME.json"
    bad.write_text("{{{ not json !!!", encoding="utf-8")
    result = snap_mod.read_live("BAD_GAME", sport="nba", out_dir=tmp_path)
    assert result is None


def test_read_live_part_assembles_games_block(tmp_path):
    """read_live_part returns a "live" block with all written games."""
    for gid in ("G4", "G5"):
        mset = ms_mod.build(gid, "nba", _reprice_like())
        snap_mod.write_live(gid, mset, out_dir=tmp_path)
    part = snap_mod.read_live_part("nba", out_dir=tmp_path)
    assert part is not None
    assert part["sport"] == "nba"
    assert part["status"] == "ok"
    assert part["served_from"] == "ingame_snapshot"
    assert isinstance(part["games"], list) and len(part["games"]) == 2
    assert "freshness" in part
    assert part["edge_claimed"] is False


def test_read_live_part_no_files_returns_none(tmp_path):
    """read_live_part with no written games -> None (triggers live_board fallback)."""
    result = snap_mod.read_live_part("nba", out_dir=tmp_path)
    assert result is None


def test_read_live_part_empty_index_returns_none(tmp_path):
    """An index with an empty games dict -> None (fallback, not an empty list)."""
    sport_dir = tmp_path / "nba"
    sport_dir.mkdir(parents=True, exist_ok=True)
    latest = sport_dir / "_latest.json"
    latest.write_text(
        json.dumps({"sport": "nba", "updated_at": "2026-06-18T00:00:00", "games": {}}),
        encoding="utf-8")
    result = snap_mod.read_live_part("nba", out_dir=tmp_path)
    assert result is None


def test_read_live_part_corrupt_index_returns_none(tmp_path):
    """Corrupt _latest.json -> None, never raises."""
    sport_dir = tmp_path / "nba"
    sport_dir.mkdir(parents=True, exist_ok=True)
    (sport_dir / "_latest.json").write_text("NOT_JSON", encoding="utf-8")
    result = snap_mod.read_live_part("nba", out_dir=tmp_path)
    assert result is None


def test_snapshot_path_is_under_sport_subdir(tmp_path):
    """Written file is at data/frontend/ingame/<sport>/<game_id>.json shape."""
    mset = ms_mod.build("G99", "nba", _reprice_like())
    path = snap_mod.write_live("G99", mset, out_dir=tmp_path)
    assert path.parent.name == "nba"
    assert path.name == "G99.json"


def test_overwrite_is_idempotent(tmp_path):
    """A second write to the same game_id overwrites cleanly; read returns latest."""
    mset1 = ms_mod.build("G1", "nba", _reprice_like(available=True,
                                                      variance=0.20,
                                                      remaining_frac=0.80))
    snap_mod.write_live("G1", mset1, out_dir=tmp_path)
    mset2 = ms_mod.build("G1", "nba", _reprice_like(available=True,
                                                      variance=0.05,
                                                      remaining_frac=0.10))
    snap_mod.write_live("G1", mset2, out_dir=tmp_path)
    envelope = snap_mod.read_live("G1", sport="nba", out_dir=tmp_path)
    assert envelope is not None
    ms_back = envelope["market_set"]
    # Latest write wins.
    assert ms_back["variance"] == pytest.approx(0.05)
    assert ms_back["remaining_frac"] == pytest.approx(0.10)


def test_variance_in_snapshot_reflects_freshness_lever():
    """FRESHNESS invariant: earlier state (Q1) has higher variance than late (Q4).

    This test does NOT call the real repricer (no network needed); it simulates
    what the repricer would emit by constructing two market_sets directly from
    hand-built reprice-like dicts with the correct variance values.
    """
    rp_early = _reprice_like(available=True, variance=0.22, remaining_frac=0.88)
    rp_late = _reprice_like(available=True, variance=0.03, remaining_frac=0.08)
    ms_early = ms_mod.build("G1", "nba", rp_early)
    ms_late = ms_mod.build("G1", "nba", rp_late)
    assert ms_early["variance"] > ms_late["variance"]
    assert ms_early["remaining_frac"] > ms_late["remaining_frac"]


def test_list_live_game_ids_empty_when_no_writes(tmp_path):
    ids = snap_mod.list_live_game_ids("nba", out_dir=tmp_path)
    assert ids == []
