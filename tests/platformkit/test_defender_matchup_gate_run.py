"""Per-file test for scripts.platformkit.defender_matchup_gate_run.

Asserts the HONESTY rails of the gate-run script on a tiny synthetic 2-corpus
fixture (no disk dependency): (1) the planted-null pure-noise column REJECTS
through the IDENTICAL faithful path (proving the gate can FAIL a signal); (2) a
column that genuinely predicts its label is NOT auto-rejected (the gate can also
pass); (3) the in-game gate trips base_degenerate (NOT_TESTABLE for a no-state
layer); (4) <2 corpora -> INSUFFICIENT_DATA, never a fabricated win; (5) no $/edge
field exists. Per-file only -- never the full suite.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from scripts.platformkit import defender_matchup_gate_run as G


def _synth(n_per_season: int = 400, signal: bool = True, seed: int = 0) -> pd.DataFrame:
    """Two-season synthetic defender layer. If signal=True the as-of feature is
    (anti-)correlated with the realized FG% (so the prior should carry information);
    if False the as-of feature is pure noise independent of the label."""
    rng = np.random.default_rng(seed)
    rows = []
    for si, (yr, mo) in enumerate(((2024, 11), (2025, 11))):
        for i in range(n_per_season):
            realized = float(rng.uniform(0.0, 1.0))
            if signal:
                asof = float(np.clip(realized + rng.normal(0, 0.1), 0, 1))
            else:
                asof = float(rng.uniform(0.2, 0.7))
            rows.append({
                "game_id": "g%d_%d" % (si, i // 4),   # ~4 rows per game -> clustering
                "game_date": pd.Timestamp(year=yr, month=mo, day=1 + (i % 27)),
                "def_player_id": 1000 + (i % 50),
                "def_team_tricode": "AAA",
                "def_priorN_fg_pct_allowed_asof": asof,
                "def_n_prior": 10,
                "realized_fg_pct_allowed": realized,
            })
    return pd.DataFrame(rows)


def test_planted_null_rejects(tmp_path):
    """A pure-noise as-of column MUST reject -> the gate can FAIL a signal."""
    df = _synth(signal=False, seed=1)
    p = tmp_path / "layer.parquet"
    df.to_parquet(p, index=False)
    v = G.run(layer_path=p)
    assert v.planted_null["rejects"] is True
    assert v.planted_null["verdict"] == "REJECT"
    # with a no-signal real column the faithful verdict is also REJECT (honest)
    assert v.verdict in ("REJECT", "PARTIAL")


def test_gate_can_pass_a_real_signal(tmp_path):
    """A column genuinely tied to the label is NOT auto-rejected (gate can pass too).

    The planted null must STILL reject in the same run (proving the gate discriminates).
    """
    df = _synth(signal=True, seed=2)
    p = tmp_path / "layer.parquet"
    df.to_parquet(p, index=False)
    v = G.run(layer_path=p)
    assert v.planted_null["rejects"] is True            # control still fails
    # a real informative prior should beat the base-rate in at least one direction
    beats = (v.faithful["a_to_b"]["prior_beats_base"]
             or v.faithful["b_to_a"]["prior_beats_base"])
    assert beats, "an informative prior should beat base-rate in >=1 direction"


def test_ingame_gate_is_degenerate_base(tmp_path):
    """A per-defender-game (no in-game state) layer trips the degenerate-base guard."""
    df = _synth(signal=True, seed=3)
    p = tmp_path / "layer.parquet"
    df.to_parquet(p, index=False)
    v = G.run(layer_path=p)
    ig = v.gate_ingame
    # the in-game gate cannot be REPLICATED on a no-state layer; it reports degenerate
    assert ig["verdict"] in ("INVALID_BASE", "PARTIAL", "REJECT")
    assert ig.get("a_base_degenerate") is True or ig.get("b_base_degenerate") is True


def test_insufficient_data_single_corpus(tmp_path):
    """Only one season on disk -> INSUFFICIENT_DATA, never a fabricated SHIP."""
    df = _synth(signal=True, seed=4)
    df = df[df["game_date"].dt.year == 2024]            # keep one season only
    p = tmp_path / "layer.parquet"
    df.to_parquet(p, index=False)
    v = G.run(layer_path=p)
    assert v.verdict == "INSUFFICIENT_DATA"
    assert v.n_corpora == 1


def test_no_dollar_or_edge_field(tmp_path):
    """No $/ROI/edge field anywhere in the verdict; proposal_only stays True."""
    df = _synth(signal=False, seed=5)
    p = tmp_path / "layer.parquet"
    df.to_parquet(p, index=False)
    v = G.run(layer_path=p)
    d = v.to_dict()
    # No MONEY field/key anywhere in the verdict (a "$"/"edge" mention is allowed ONLY
    # inside the honesty disclaimers that DENY a $ edge -- never as a numeric field).
    bad_keys = ("roi", "profit", "dollar", "bankroll", "units", "stake", "payout")
    for k in d:
        assert not any(b in k.lower() for b in bad_keys), k
    # the only "$"/"edge" strings live in caveats/vs_close as explicit DENIALS
    disclaimer = " ".join(d.get("caveats", []) + [d.get("vs_close", "")]).lower()
    for token in ("$", "market edge"):
        # every occurrence must be inside the disclaimer text, none in a data field
        in_fields = repr({kk: vv for kk, vv in d.items()
                          if kk not in ("caveats", "vs_close", "deciding_stat")}).lower()
        assert token not in in_fields, token
    assert "no $" in disclaimer or "not a market edge" in disclaimer
    assert d["proposal_only"] is True
    assert "CALIBRATION" in d["vs_close"]
