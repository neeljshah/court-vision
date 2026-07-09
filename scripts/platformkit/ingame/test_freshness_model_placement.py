"""Per-file test: ref-side model-prob resolution + paired bootstrap CI."""
import datetime as dt

import numpy as np

from scripts.platformkit.ingame import freshness_model_placement as fmp
from scripts.platformkit.ingame.nba_outcome_resolver import _build_name_index


def test_resolve_model_prob_ref_side():
    names = {"BOS", "PHI"}
    name_index = _build_name_index(names)
    # ticker tail "BOSPHI" -> away=BOS, home=PHI (per KXNBAGAME AWAY+HOME shape)
    lut = {(dt.date(2026, 4, 26), "BOS", "PHI"): 0.65}
    p = fmp._resolve_model_prob("KXNBAGAME-26APR26BOSPHI", lut, name_index)
    # ref = alphabetically-first of {BOS,PHI} = BOS (away) -> 1 - p_home
    assert abs(p - (1.0 - 0.65)) < 1e-9


def test_resolve_model_prob_missing_is_none():
    name_index = _build_name_index({"BOS", "PHI"})
    assert fmp._resolve_model_prob("KXNBAGAME-26APR26BOSPHI", {}, name_index) is None
    assert fmp._resolve_model_prob("KXMLBGAME-26APR261920LAAKC", {}, name_index) is None


def test_paired_bootstrap_ci():
    lo, hi = fmp._paired_bootstrap_ci(np.array([1.0, 2.0]))
    assert np.isnan(lo) and np.isnan(hi)
    lo, hi = fmp._paired_bootstrap_ci(np.array([0.01] * 20))
    assert abs(lo - 0.01) < 1e-9 and abs(hi - 0.01) < 1e-9
