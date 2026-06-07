"""Tests for the gated, default-OFF vac_load PTS+REB feature.

Mirrors the proven vac_ast feature gate. Verifies:
  (a) flag OFF  -> feature_columns is byte-identical to a clean baseline (no
      vac_load keys present anywhere) for pts/reb/ast — proves a true no-op.
  (b) flag ON   -> feature_columns("pts") gains exactly [vac_min,vac_pts,n_out]
      at the END (129 -> 132); feature_columns("reb") gains them (132 -> 135);
      feature_columns("ast") is UNCHANGED (vac_load is pts/reb only).
  (c) build_vac_load_lookup() returns a dict keyed by (pid, 'YYYY-MM-DD') with
      the right value keys and sane non-negative numbers — smoke only; skipped
      when the box-log sources are missing (fresh checkout).

The feature is appended LAST so existing frozen artifacts load without an
n_features_in_ mismatch. Leak-free (as-of L10 strictly-prior games).
"""
import importlib
import os

import pytest

VAC_LOAD_KEYS = ("vac_min", "vac_pts", "n_out")
VAC_AST_KEYS = ("vac_ast", "vac_ast_share")


def _reload_with_flag(value):
    """Reload prop_pergame with CV_VAC_LOAD_FEATURE set to `value` (or unset
    when value is None) and CV_AST_VAC_FEATURE forced OFF, returning the module."""
    os.environ.pop("CV_AST_VAC_FEATURE", None)
    if value is None:
        os.environ.pop("CV_VAC_LOAD_FEATURE", None)
    else:
        os.environ["CV_VAC_LOAD_FEATURE"] = value
    import src.prediction.prop_pergame as m
    importlib.reload(m)
    return m


@pytest.fixture(autouse=True)
def _restore_env():
    """Snapshot/restore the two flags so test order can't leak module state."""
    saved = {k: os.environ.get(k) for k in ("CV_VAC_LOAD_FEATURE", "CV_AST_VAC_FEATURE")}
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    # Leave the module reloaded in its default-OFF state for any later module.
    _reload_with_flag(None)


# ── (a) default-OFF byte-identical ────────────────────────────────────────────

def test_off_is_byte_identical_to_baseline():
    """With the flag unset/0 the column lists carry NO vac_load keys and match
    the flag-explicitly-0 baseline exactly, for pts/reb/ast."""
    m_unset = _reload_with_flag(None)
    base = {s: list(m_unset.feature_columns(s)) for s in ("pts", "reb", "ast")}

    m_zero = _reload_with_flag("0")
    for s in ("pts", "reb", "ast"):
        cols = list(m_zero.feature_columns(s))
        assert cols == base[s], f"{s}: flag=0 differs from unset baseline"
        for k in VAC_LOAD_KEYS:
            assert k not in cols, f"{s}: {k} leaked into OFF feature list"


def test_off_known_baseline_counts():
    """The OFF baseline counts are the documented values (pts 129, reb 132,
    ast 129) — guards against an accidental always-on append."""
    m = _reload_with_flag(None)
    assert len(m.feature_columns("pts")) == 129
    assert len(m.feature_columns("reb")) == 132
    assert len(m.feature_columns("ast")) == 129


# ── (b) flag ON appends exactly the right keys at the end ──────────────────────

def test_on_pts_appends_vac_load_last():
    m = _reload_with_flag("1")
    cols = list(m.feature_columns("pts"))
    assert len(cols) == 132, f"pts expected 132 with flag on, got {len(cols)}"
    assert tuple(cols[-3:]) == VAC_LOAD_KEYS
    # exactly the 3 new keys, appended (rest unchanged vs OFF)
    off = list(_reload_with_flag(None).feature_columns("pts"))
    assert cols[: len(off)] == off
    assert cols[len(off):] == list(VAC_LOAD_KEYS)


def test_on_reb_appends_vac_load_last():
    m = _reload_with_flag("1")
    cols = list(m.feature_columns("reb"))
    assert len(cols) == 135, f"reb expected 135 with flag on, got {len(cols)}"
    assert tuple(cols[-3:]) == VAC_LOAD_KEYS
    off = list(_reload_with_flag(None).feature_columns("reb"))
    assert cols[: len(off)] == off
    assert cols[len(off):] == list(VAC_LOAD_KEYS)
    # reb ordering is base + reb_context + vac_load: reb_context keys precede.
    for rk in ("team_oreb_pct_l5", "opp_dreb_pct_l5", "reb_chance_l5"):
        assert cols.index(rk) < cols.index("vac_min")


def test_on_ast_unchanged():
    """vac_load is pts/reb-only — AST must NOT gain the keys when the flag is on
    (and CV_AST_VAC_FEATURE stays OFF)."""
    on = list(_reload_with_flag("1").feature_columns("ast"))
    off = list(_reload_with_flag(None).feature_columns("ast"))
    assert on == off
    for k in VAC_LOAD_KEYS:
        assert k not in on
    assert len(on) == 129


# ── (c) builder smoke ──────────────────────────────────────────────────────────

def test_build_vac_load_lookup_shape():
    """Builder returns a dict keyed by (int pid, 'YYYY-MM-DD') with the 3 value
    keys and sane non-negative numbers. Skipped if box-log sources are absent."""
    m = _reload_with_flag("1")
    # Reset the per-process memo so we exercise a real build.
    m._VAC_LOAD_CACHE = None
    lk = m.build_vac_load_lookup()
    assert isinstance(lk, dict)
    if not lk:
        pytest.skip("vac_load sources missing on this checkout — empty lookup")
    # Inspect a sample of records.
    for (pid, ds), rec in list(lk.items())[:200]:
        assert isinstance(pid, int)
        assert isinstance(ds, str) and len(ds) == 10 and ds[4] == "-" and ds[7] == "-"
        assert set(rec.keys()) == set(VAC_LOAD_KEYS)
        assert rec["vac_min"] >= 0.0
        assert rec["vac_pts"] >= 0.0
        assert rec["n_out"] >= 0.0
        # n_out is an integer count stored as float
        assert float(rec["n_out"]).is_integer()
        # a vacated regular contributes >= 15 as-of L10 min, so any nonzero
        # n_out implies nonzero vac_min.
        if rec["n_out"] > 0:
            assert rec["vac_min"] > 0.0
