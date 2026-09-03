"""Per-file tests for factory_source_manifest (S78).

  cd /c/Users/neelj/nba-ai-system && python -m pytest \
      tests/platformkit/ops/test_factory_source_manifest.py -q

Two things are checked and nothing else: the manifest really is BUILT FROM the registries
(not a hardcoded list), and the pod comparison classifies MISSING / DIFFERS / OK correctly
on a synthetic listing.
"""
from __future__ import annotations

import pytest

from scripts.platformkit.foundry import asof_supply, catalogue
from scripts.platformkit.ops import factory_source_manifest as fsm


def test_manifest_comes_from_the_registries():
    need = fsm.required()
    # asof_supply: every declared bridge table (comma lists split, globs expanded).
    for spec in asof_supply.REGISTRY.values():
        for part in spec.source.split(","):
            part = part.strip()
            if any(ch in part for ch in "*?["):
                continue
            assert part in need, part
    # catalogue: every NAMED parquet.
    for name in catalogue.NAMED:
        assert name in need, name
    # the corpora, their sidecars, and a sidecar-recorded source.
    for sport in ("nba", "mlb", "soccer", "tennis"):
        assert "data/cache/combo/gate_corpus_%s.parquet" % sport in need
        assert "data/cache/combo/gate_corpus_%s.sources.json" % sport in need
    assert "data/cache/combo/gate_corpus_nba_close.parquet" in need
    # close_join spines + the hardcoded screen_predictor._teams games tables.
    for path in ("data/domains/tennis/wta_matches.parquet", "data/domains/soccer/odds.parquet",
                 "data/domains/basketball_nba/games.parquet",
                 "data/domains/mlb/games_current.parquet"):
        assert path in need, path
    # origins are recorded, so a MISSING row can always name who asked for it.
    assert all(need[p] for p in need)


def test_pod_path_subset_drops_the_ingame_only_stores():
    full, gated = fsm.required(), fsm.required(ingame=False)
    assert set(gated) < set(full)
    # an in-game-only store is enumerated but not gated ...
    assert "data/cache/eval_gate/s86_nba_every_tick_2026-09-03.csv" in full
    assert not fsm.on_pod_path(["ingame:nba", "families:live_tick:nba_ticks"])
    # ... while anything a pregame screen reads stays gated.
    assert "data/cache/combo/gate_corpus_tennis.parquet" in gated
    assert fsm.on_pod_path(["catalogue", "asof_supply:tennis_meta"])


def test_classify_missing_differs_ok():
    local = [("a.parquet", 10, "sha_a"), ("b.parquet", 20, "sha_b"), ("c.parquet", 30, "sha_c")]
    pod = {"a.parquet": "sha_a", "b.parquet": "DIFFERENT"}
    assert fsm.classify(local, pod) == {"a.parquet": "OK", "b.parquet": "DIFFERS",
                                        "c.parquet": "MISSING"}


def test_ship_command_names_only_the_missing_set_and_never_runs():
    command = fsm.ship_command(["x.parquet", "y.parquet"])
    assert "x.parquet" in command and "y.parquet" in command
    assert "tar -czf -" in command and fsm.POD_REPO in command
    assert "--force" not in command
    assert fsm.ship_command([]) == "(nothing missing -- no ship needed)"


def test_pod_digests_refuses_an_empty_transport(monkeypatch):
    """An ssh that returns nothing must RAISE, not report every source MISSING (fail-open)."""
    class _Proc:
        returncode, stdout, stderr = 255, b"", b"ssh: connect refused"

    monkeypatch.setattr(fsm.subprocess, "run", lambda *a, **k: _Proc())
    with pytest.raises(RuntimeError, match="no sha256sum output"):
        fsm.pod_digests(["a.parquet"])
