"""Offline tests for the loop-consistent in-game refresh gate (ingame_gate_refresh).

Asserts the C1 fix: the gate operates on the EXACT refresh corpora the runner appends
to (refresh_a/_b) -- NOT a stale alphabetically-first re-glob -- and writes gate_<sport>
.json that the server reads. Builds two tiny frozen-schema parquets in a tmp state_dir
and confirms a fresh verdict reflects them; the NBA route targets finegrain_nba.json.
"""
from __future__ import annotations

import json
import sys
import pathlib

import pandas as pd
import pytest

_REPO = pathlib.Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.ingame import ingame_gate_refresh as GR  # noqa: E402
from scripts.platformkit.ingame.ingame_refresh_corpora import (  # noqa: E402
    corpus_for, corpus_paths,
)


def _states(gid, n=6, p0=0.55, y=1):
    return [{"sport": "mlb", "game_id": gid, "asof_idx": i,
             "state_diff": float(i - n // 2), "frac_elapsed": (i + 1) / (n + 1.0),
             "p0": p0, "outcome": y} for i in range(n)]


def _seed_refresh_corpora(state_dir, n_games=20):
    """Write balanced refresh_a/_b parquets so both A and B exist (cross gate needs 2)."""
    rows = {0: [], 1: []}
    for g in range(n_games):
        gid = "G%03d" % g
        rows[corpus_for(gid)].extend(_states(gid, y=g % 2))
    paths = corpus_paths("mlb", state_dir=state_dir)
    for idx, p in enumerate(paths):
        pd.DataFrame(rows[idx]).to_parquet(p, index=False)
    return paths


def test_gate_refresh_gates_the_full_pool(tmp_path):
    """BUG A fix: the gate judges the FULL server pool (every {sport}_states__*), not a
    stale subset. A seed corpus alongside the refresh corpora IS included -- gate==serve.
    """
    sd = tmp_path / "states"
    sd.mkdir()
    _seed_refresh_corpora(sd)
    # an extra seed corpus is part of the server pool too -> it must be GATED (not ignored)
    extra = [s for g in range(4) for s in _states("X%03d" % g, y=g % 2)]
    pd.DataFrame(extra).to_parquet(sd / "mlb_states__seed_extra.parquet", index=False)
    v = GR.gate_refresh("mlb", state_dir=str(sd))
    total_games = v.coverage.get("a_games", 0) + v.coverage.get("b_games", 0)
    assert total_games >= 22, v.coverage  # 20 refresh + 4 extra, all in the pool


def test_gate_refresh_writes_server_read_file(tmp_path):
    sd = tmp_path / "states"
    sd.mkdir()
    _seed_refresh_corpora(sd)
    GR.gate_refresh("mlb", state_dir=str(sd))
    # the verdict file the server reads for a generic sport is gate_<sport>.json
    out = pathlib.Path(GR._OUT_DIR) / "gate_mlb.json"
    assert out.exists()
    assert "verdict" in json.loads(out.read_text())


def test_nba_route_targets_finegrain_file(monkeypatch, tmp_path):
    """NBA's refresh gate must write finegrain_nba.json (the file ingame_serve reads for
    NBA), gating the SAME pool the server fits -- not gate_nba.json (which serve ignores).
    """
    import scripts.platformkit.ingame.ingame_serve as serve
    # inject a small NBA A/B split so we don't touch real parquets. _load_pool must
    # mirror the split (A+B) so the gate==serve parity guard sees a consistent stub,
    # exactly as the real loop does (both derive from the same _corpora_for set).
    a, b = [], []
    for g in range(16):
        (a if g % 2 == 0 else b).extend(_states("N%03d" % g, y=g % 2))
    monkeypatch.setattr(serve, "pool_split_ab", lambda sport: (a, b))
    monkeypatch.setattr(serve, "_load_pool", lambda sport: a + b)
    out_dir = pathlib.Path(tmp_path / "ingame_out")
    monkeypatch.setattr(GR, "_OUT_DIR", str(out_dir))
    GR.gate_refresh("nba")
    assert (out_dir / "finegrain_nba.json").exists()
    assert not (out_dir / "gate_nba.json").exists()  # serve never reads this for NBA


def test_bug_a_real_pool_gate_no_parity_error_and_matches_fit_pool():
    """BUG A: on the REAL pool the gate must NOT raise the gate/fit parity error, and the
    corpora it judges must be EXACTLY the server's fit pool (so verdict == served model).
    """
    import scripts.platformkit.ingame.ingame_serve as serve
    if not serve._corpora_for("mlb"):
        pytest.skip("no real mlb corpora on disk")
    # gate the full real pool -- must not raise (the old refresh-only gate did)
    v = GR.gate_refresh("mlb")
    assert v.verdict in {"REPLICATED", "PARTIAL", "REJECT", "INVALID_BASE",
                         "INSUFFICIENT_DATA"}
    # the gate split A+B is exactly _corpora_for -> gated games == fit-pool games
    a, b = serve.pool_split_ab("mlb")
    gated_games = len({s["game_id"] for s in a} | {s["game_id"] for s in b})
    fit_games = len({s["game_id"] for s in serve._load_pool("mlb")})
    assert gated_games == fit_games, (gated_games, fit_games)


def test_pool_split_ab_is_disjoint_complete_partition_all_sports():
    """GLOB-POOL INTEGRITY: for EVERY sport on disk, pool_split_ab must be a disjoint,
    complete partition of the served pool (gate==serve).

    Guards the double-count class (soccer combos+singles) and the !=2-corpora split class
    (MLB's 4 season files): A+B states == pool states, A&B share NO game, A|B games ==
    pool games, and neither side is empty (the 4-file split must not degenerate).
    """
    import scripts.platformkit.ingame.ingame_serve as serve
    tested = 0
    for sport in ("nba", "mlb", "soccer", "tennis"):
        pool = serve._load_pool(sport)
        if not pool:
            continue
        tested += 1
        a, b = serve.pool_split_ab(sport)
        assert len(a) + len(b) == len(pool), (sport, "A+B states != pool states")
        ga = {s["game_id"] for s in a}
        gb = {s["game_id"] for s in b}
        gp = {s["game_id"] for s in pool}
        assert not (ga & gb), (sport, "A/B share games (cross-corpus double-count)")
        assert (ga | gb) == gp, (sport, "A|B games != served pool games (gate!=serve)")
        assert ga and gb, (sport, "a split side is EMPTY (degenerate split)")
        # and the live parity guard must AGREE (not raise) on the same real pool
        GR._assert_gate_pool_parity(sport)
    if tested == 0:
        pytest.skip("no real in-game corpora on disk")


def test_parity_guard_raises_on_cross_corpus_overlap(monkeypatch):
    """The parity guard must FIRE (raise) when A/B share a game -- the soccer
    combos+singles double-count class. (The prior guard was a no-op that never fired.)"""
    import scripts.platformkit.ingame.ingame_serve as serve
    monkeypatch.setattr(serve, "_load_pool", lambda sp: [{"game_id": "g1"}, {"game_id": "g2"}])
    monkeypatch.setattr(serve, "pool_split_ab",
                        lambda sp: ([{"game_id": "g1"}], [{"game_id": "g1"}]))
    with pytest.raises(GR.GatePoolParityError):
        GR._assert_gate_pool_parity("mlb")


def test_parity_guard_raises_on_incomplete_split(monkeypatch):
    """The parity guard must FIRE when A|B drops a served game (gate!=serve)."""
    import scripts.platformkit.ingame.ingame_serve as serve
    monkeypatch.setattr(serve, "_load_pool",
                        lambda sp: [{"game_id": "g1"}, {"game_id": "g2"}, {"game_id": "g3"}])
    monkeypatch.setattr(serve, "pool_split_ab",
                        lambda sp: ([{"game_id": "g1"}], [{"game_id": "g2"}]))  # g3 dropped
    with pytest.raises(GR.GatePoolParityError):
        GR._assert_gate_pool_parity("mlb")


def test_gate_on_paths_needs_two_corpora(tmp_path):
    sd = tmp_path / "states"
    sd.mkdir()
    p = sd / "mlb_states__refresh_a.parquet"
    pd.DataFrame(_states("X")).to_parquet(p, index=False)
    v = GR.gate_on_paths("mlb", [str(p)])  # only one path
    assert v.verdict == "INSUFFICIENT_DATA"


# ---------------------------------------------------------------------------
# FIX 1 + FIX 3: write-guard and serve-sufficiency tests (2026-06-19)
# ---------------------------------------------------------------------------

def _seed_rich_verdict(out_dir, sport="mlb"):
    """Write a fake REPLICATED verdict with 1000 games to simulate a production file."""
    import json
    rich = {
        "verdict": "REPLICATED",
        "sport": sport,
        "coverage": {"a_games": 500, "b_games": 500, "a_states": 5000, "b_states": 5000},
    }
    p = pathlib.Path(out_dir) / ("gate_%s.json" % sport)
    p.write_text(json.dumps(rich), encoding="ascii")
    return p


def test_thin_run_does_not_clobber_richer_production_verdict(tmp_path):
    """FIX 1: a thin/INSUFFICIENT gate run must NOT overwrite a richer existing file.

    Simulates the bug: gate_mlb.json held a rich REPLICATED verdict (1000 games);
    a thin run of 5 games would have clobbered it. The write-guard must prevent that.
    """
    out_dir = tmp_path / "ingame_out"
    out_dir.mkdir()
    rich_path = _seed_rich_verdict(str(out_dir), sport="mlb")

    # Patch GR._OUT_DIR so _write resolves to our tmp dir (production path emulation).
    import scripts.platformkit.ingame.ingame_gate_refresh as GR_mod
    original = GR_mod._OUT_DIR
    try:
        GR_mod._OUT_DIR = str(out_dir)
        # Also patch the import inside ingame_gate_generic to point at our out_dir.
        import scripts.platformkit.ingame.ingame_gate_generic as GG_mod
        orig_gg = GG_mod._OUT_DIR
        GG_mod._OUT_DIR = str(out_dir)

        # A thin corpus (3 games per side -- well below _MIN_GAMES_TO_OVERWRITE=50).
        sd = tmp_path / "states"
        sd.mkdir()
        _seed_refresh_corpora(sd, n_games=5)  # only 5 games total
        v = GR.gate_refresh("mlb", state_dir=str(sd))
        # Verdict should be INSUFFICIENT_DATA or thin REJECT -- not enough games.
        total_new = v.coverage.get("a_games", 0) + v.coverage.get("b_games", 0)
        assert total_new < 50, "test corpus should be thin"

        # The RICHER production file (1000 games) must NOT have been overwritten.
        import json
        on_disk = json.loads(rich_path.read_text())
        assert on_disk["verdict"] == "REPLICATED", (
            "write-guard failed: thin run clobbered richer production verdict. "
            "on_disk=%s" % on_disk)
        assert on_disk["coverage"]["a_games"] == 500, "production games were lost"
    finally:
        GR_mod._OUT_DIR = original
        GG_mod._OUT_DIR = orig_gg


def test_thin_run_with_out_dir_writes_to_sandbox_not_production(tmp_path):
    """FIX 1: injecting out_dir routes the verdict to a sandbox, not the real path."""
    out_dir = tmp_path / "sandbox"
    out_dir.mkdir()
    prod_dir = tmp_path / "production"
    prod_dir.mkdir()

    sd = tmp_path / "states"
    sd.mkdir()
    _seed_refresh_corpora(sd, n_games=5)

    import scripts.platformkit.ingame.ingame_gate_refresh as GR_mod
    orig = GR_mod._OUT_DIR
    try:
        # production dir has no pre-existing file
        GR_mod._OUT_DIR = str(prod_dir)
        import scripts.platformkit.ingame.ingame_gate_generic as GG_mod
        orig_gg = GG_mod._OUT_DIR
        GG_mod._OUT_DIR = str(prod_dir)

        GR.gate_refresh("mlb", state_dir=str(sd), out_dir=str(out_dir))

        # verdict written to sandbox, NOT to production
        assert (out_dir / "gate_mlb.json").exists(), "sandbox file not written"
        assert not (prod_dir / "gate_mlb.json").exists(), "production file wrongly written"
    finally:
        GR_mod._OUT_DIR = orig
        GG_mod._OUT_DIR = orig_gg


def test_serve_ingame_proven_requires_sufficient_games(tmp_path):
    """FIX 3: serve_ingame must degrade to BASE when n_games < _MIN_GAMES_PROVEN,
    even if the artifact's embedded verdict says REPLICATED.
    """
    import json
    import scripts.platformkit.ingame.ingame_serve as serve

    model_dir = tmp_path / "models"
    model_dir.mkdir()
    # A thin artifact: says REPLICATED but only 3 games -- should NOT be served as proven.
    thin_art = {
        "version": 1, "sport": "mlb", "verdict": "REPLICATED",
        "prior_status": "proven", "n_states": 9, "n_games": 3,
        "base_slope": [1.0, 0.5],
        "weight_surface": {"edges": [0.0], "default": 0.3, "cells": {}},
        "fit_ok": True,
    }
    art_path = model_dir / "mlb_ingame.json"
    art_path.write_text(json.dumps(thin_art), encoding="ascii")

    orig_dir = serve._MODEL_DIR
    try:
        serve._MODEL_DIR = str(model_dir)
        result = serve.serve_ingame("mlb", state_diff=2.0, frac_elapsed=0.5, p0=0.6)
        # Sufficiency guard: n_games=3 < 50 -> must NOT be proven
        assert result["model"] != "base+prior(proven)", (
            "serve_ingame served thin artifact as proven: %s" % result)
        # Should serve as base only (honest degrade)
        assert result["model"] == "base", (
            "expected 'base' after sufficiency degrade, got: %s" % result["model"])
        assert "SUFFICIENCY GUARD" in " ".join(result.get("provenance", []))
    finally:
        serve._MODEL_DIR = orig_dir


def test_serve_ingame_proven_passes_for_sufficient_games(tmp_path):
    """FIX 3: serve_ingame must serve proven when n_games >= _MIN_GAMES_PROVEN."""
    import json
    import scripts.platformkit.ingame.ingame_serve as serve

    model_dir = tmp_path / "models"
    model_dir.mkdir()
    rich_art = {
        "version": 1, "sport": "mlb", "verdict": "REPLICATED",
        "prior_status": "proven", "n_states": 500000, "n_games": 4865,
        "base_slope": [1.0, 0.5],
        "weight_surface": {"edges": [0.0], "default": 0.3, "cells": {}},
        "fit_ok": True,
    }
    art_path = model_dir / "mlb_ingame.json"
    art_path.write_text(json.dumps(rich_art), encoding="ascii")

    orig_dir = serve._MODEL_DIR
    try:
        serve._MODEL_DIR = str(model_dir)
        result = serve.serve_ingame("mlb", state_diff=2.0, frac_elapsed=0.5, p0=0.6)
        assert result["model"] == "base+prior(proven)", (
            "expected proven for 4865-game artifact, got: %s" % result["model"])
    finally:
        serve._MODEL_DIR = orig_dir


# ---------------------------------------------------------------------------
# gap_ledger_ultra16.md row 1: _write must be crash-safe (tmp+os.replace via
# io_atomic.write_json_atomic), not a bare open()+json.dump.
# ---------------------------------------------------------------------------

def test_write_routes_through_atomic_helper(tmp_path, monkeypatch):
    """_write must call io_atomic.write_json_atomic, not open()+json.dump directly."""
    calls = []
    real = GR.write_json_atomic

    def _spy(path, obj, **kw):
        calls.append((path, obj))
        return real(path, obj, **kw)

    monkeypatch.setattr(GR, "write_json_atomic", _spy)
    from scripts.platformkit.ingame.ingame_gate_generic import GenericVerdict
    v = GenericVerdict("INSUFFICIENT_DATA", "mlb", {}, {}, {"a_games": 0, "b_games": 0}, [])
    out_dir = tmp_path / "out"
    out = GR._write(v, "gate_mlb.json", out_dir=str(out_dir))
    assert len(calls) == 1, "_write did not call the shared atomic helper"
    assert calls[0][0] == out
    assert json.loads(pathlib.Path(out).read_text())["verdict"] == "INSUFFICIENT_DATA"


def test_write_never_leaves_a_torn_file_on_crash(tmp_path, monkeypatch):
    """Simulate a kill mid-write: the target is either the OLD complete file or the NEW
    complete file, never a partial one (the crash-safety this fix exists for)."""
    from scripts.platformkit.ingame.ingame_gate_generic import GenericVerdict
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    target = out_dir / "gate_mlb.json"
    target.write_text('{"verdict": "OLD"}', encoding="ascii")

    def _boom(*a, **kw):
        raise OSError("simulated kill mid-write")

    monkeypatch.setattr(GR, "write_json_atomic", _boom)
    v = GenericVerdict("REPLICATED", "mlb", {}, {}, {"a_games": 999, "b_games": 999}, [])
    with pytest.raises(OSError):
        GR._write(v, "gate_mlb.json", out_dir=str(out_dir))
    # target must be untouched -- old complete content, never partial/empty
    on_disk = json.loads(target.read_text())
    assert on_disk == {"verdict": "OLD"}


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
