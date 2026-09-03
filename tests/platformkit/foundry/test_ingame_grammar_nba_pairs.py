"""S144: the systematic pair grammar is closed, blind, causal, and separately frozen."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.family_bars import git_blob_id, load_families
from scripts.platformkit.foundry import ingame_grammar_nba as N
from scripts.platformkit.foundry import ingame_grammar_nba_pairs as P
from scripts.platformkit.foundry.grammar import semantic_hash
from scripts.platformkit.foundry.ingame_guards import assert_label_blind, assert_tick_asof

S86_CSV = Path("data/cache/eval_gate/s86_nba_every_tick_2026-09-03.csv")


def synthetic(n_games: int = 6, n_ticks: int = 40) -> pd.DataFrame:
    rng = np.random.default_rng(20260903)
    frames = []
    for game in range(n_games):
        home = np.cumsum(rng.integers(0, 4, n_ticks)).astype(float)
        away = np.cumsum(rng.integers(0, 4, n_ticks)).astype(float)
        elapsed = np.linspace(0.5, 47.5, n_ticks)
        frames.append(pd.DataFrame({
            "game": "g%d" % game, "ts": 1_700_000_000 + game * 100_000 + np.arange(n_ticks) * 60.0,
            "period": np.clip((elapsed // 12 + 1).astype(int), 1, 4),
            "score_home": home, "score_away": away, "margin": home - away,
            "elapsed": elapsed, "rem": 48.0 - elapsed}))
    return pd.concat(frames, ignore_index=True).sort_values(["ts", "game"], kind="stable").reset_index(drop=True)


def real_slice(n_games: int = 24) -> pd.DataFrame:
    frame = pd.read_csv(S86_CSV, usecols=["game_id", "ts", "period", "score_home", "score_away", "margin", "elapsed", "rem"])
    keep = sorted(frame["game_id"].unique())[:n_games]
    return frame[frame["game_id"].isin(keep)].rename(columns={"game_id": "game"}).assign(
        game=lambda x: x["game"].astype(str)).sort_values(["ts", "game"], kind="stable").reset_index(drop=True)


def test_the_pair_grid_is_exhaustive_deduped_and_disjoint_from_s102():
    hypotheses = P.enumerate_hypotheses()
    assert len(P.BASE) == 14 and len(P.EXCLUDED_BASES) == 2
    assert len(P.pair_members()) == 91 * 2 == 182
    assert len(hypotheses) == 91 * 2 * 6 == 1092
    hashes = {semantic_hash(h) for h in hypotheses}
    assert len(hashes) == len(hypotheses)
    assert hashes.isdisjoint({semantic_hash(h) for h in N.enumerate_hypotheses()})
    assert not set(P.EXCLUDED_BASES) & set(P.BASE)
    assert all(not any(base in h.feature for base in P.EXCLUDED_BASES) for h in hypotheses)
    assert set(P.build_grid(synthetic()).columns) == {h.feature + "|raw" for h in hypotheses}


def test_pair_builders_are_tick_time_causal_at_eight_probes_and_label_blind():
    src = real_slice()
    probes = assert_tick_asof(src, P.build_grid, probes=8, labels=np.arange(len(src)) % 2)
    assert len(probes) == 8 and probes[-1] > len(src) // 2
    assert assert_label_blind(src, P.build_grid, labels=np.arange(len(src)) % 2) == ["outcome"]


def test_the_pair_family_is_frozen_once_with_the_new_pin_and_closed_count():
    spec = load_families()
    family = spec.get(P.FAMILY)
    text = Path("docs/evidence/harness/FWER_FAMILIES_SPEC_2026-09-03.md").read_text("ascii")
    assert text.count("S144 -- one NBA in-game pair TICK-GRID family added") == 1
    assert spec.spec_version == "s144-families-v4" and len(spec.families) == 41
    assert family.kind == "tickgrid" and family.features == 182 and family.hypotheses == 1092
    assert tuple(family.members) == P.pair_members()
    assert family.hypotheses == len(P.enumerate_hypotheses())
    assert spec.prereg_sha256 == git_blob_id(Path(spec.spec_path))
