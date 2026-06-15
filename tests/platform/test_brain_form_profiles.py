"""Tests for scripts.platformkit.brain_form_profiles — as-of form signal distributions.

Hermetic: builds tiny synthetic as-of DataFrames via the ``injected`` seam (no disk I/O)
and asserts the rendered _Form_Profiles.md:
  (a) percentile bands are monotonic (p10 <= p25 <= p50 <= p75 <= p90);
  (b) carries the honest no-edge banner (markets efficient / calibration is not edge);
  (c) is person-free (no two-word Title-Case proper names, no player/team wikilinks);
  (d) sports with a missing parquet are skipped honestly;
  (e) a sport with an empty frame is skipped honestly;
  (f) is idempotent (re-run -> byte-identical output).
"""
from __future__ import annotations

import pandas as pd
import pytest

from scripts.platformkit.brain_form_profiles import (
    build_form_profiles,
    _pool_metric,
    _percentile_bands,
)


# ---------------------------------------------------------------------------
# Synthetic frames
# ---------------------------------------------------------------------------

def _nba_frame(n: int = 40) -> pd.DataFrame:
    """Minimal NBA as-of frame with the four required metric pairs."""
    import random
    rng = random.Random(42)
    rows = []
    for _ in range(n):
        rows.append({
            "game_id":           f"g{_}",
            "home_pace_asof":    rng.uniform(92, 108),
            "away_pace_asof":    rng.uniform(92, 108),
            "home_ast_rate_asof": rng.uniform(0.18, 0.32),
            "away_ast_rate_asof": rng.uniform(0.18, 0.32),
            "home_oreb_pg_asof": rng.uniform(8, 14),
            "away_oreb_pg_asof": rng.uniform(8, 14),
            "home_tov_pg_asof":  rng.uniform(10, 18),
            "away_tov_pg_asof":  rng.uniform(10, 18),
        })
    return pd.DataFrame(rows)


def _tennis_frame(n: int = 30) -> pd.DataFrame:
    """Minimal Tennis as-of frame with the five required metric pairs."""
    import random
    rng = random.Random(7)
    rows = []
    for _ in range(n):
        rows.append({
            "event_id":         f"t{_}",
            "p1_ace_rate_asof": rng.uniform(0.03, 0.18),
            "p2_ace_rate_asof": rng.uniform(0.03, 0.18),
            "p1_1st_in_asof":   rng.uniform(0.55, 0.72),
            "p2_1st_in_asof":   rng.uniform(0.55, 0.72),
            "p1_1st_win_asof":  rng.uniform(0.65, 0.82),
            "p2_1st_win_asof":  rng.uniform(0.65, 0.82),
            "p1_2nd_win_asof":  rng.uniform(0.45, 0.62),
            "p2_2nd_win_asof":  rng.uniform(0.45, 0.62),
            "p1_bp_saved_asof": rng.uniform(0.50, 0.75),
            "p2_bp_saved_asof": rng.uniform(0.50, 0.75),
        })
    return pd.DataFrame(rows)


def _empty_nba_frame() -> pd.DataFrame:
    """NBA frame with all-NaN metric columns -> should skip."""
    df = _nba_frame(5)
    for c in ["home_pace_asof", "away_pace_asof", "home_ast_rate_asof",
              "away_ast_rate_asof", "home_oreb_pg_asof", "away_oreb_pg_asof",
              "home_tov_pg_asof", "away_tov_pg_asof"]:
        df[c] = float("nan")
    return df


# ---------------------------------------------------------------------------
# Unit tests for helpers
# ---------------------------------------------------------------------------

def test_pool_metric_concatenates_and_drops_nan():
    df = pd.DataFrame({"a": [1.0, 2.0, float("nan")], "b": [4.0, 5.0, 6.0]})
    series = _pool_metric(df, ["a", "b"])
    assert len(series) == 5        # 3 from 'a' minus 1 NaN + 3 from 'b'
    assert float("nan") not in series.values


def test_pool_metric_missing_col_skipped():
    df = pd.DataFrame({"x": [1.0, 2.0]})
    series = _pool_metric(df, ["x", "nonexistent"])
    assert list(series) == [1.0, 2.0]


def test_percentile_bands_monotonic():
    import numpy as np
    rng = np.random.default_rng(0)
    s = pd.Series(rng.uniform(0, 1, 200))
    b = _percentile_bands(s)
    assert b is not None
    assert b["p10"] <= b["p25"] <= b["p50"] <= b["p75"] <= b["p90"]


def test_percentile_bands_none_on_too_few_values():
    assert _percentile_bands(pd.Series([], dtype=float)) is None
    assert _percentile_bands(pd.Series([1.0])) is None


# ---------------------------------------------------------------------------
# End-to-end via injected seam
# ---------------------------------------------------------------------------

def test_builds_nba_and_tennis_from_injected(tmp_path):
    out = tmp_path / "out"
    rep = build_form_profiles(
        organized_root=out,
        injected={"NBA": _nba_frame(), "Tennis": _tennis_frame()},
        write=True,
    )
    assert rep["n_sports"] == 2
    assert "skipped" not in rep["by_sport"]["NBA"]
    assert "skipped" not in rep["by_sport"]["Tennis"]
    assert (out / "NBA" / "_Form_Profiles.md").is_file()
    assert (out / "Tennis" / "_Form_Profiles.md").is_file()


def test_bands_monotonic_in_output(tmp_path):
    out = tmp_path / "out"
    rep = build_form_profiles(
        organized_root=out,
        injected={"NBA": _nba_frame(80)},
        write=True,
    )
    bands = rep["by_sport"]["NBA"]["bands"]
    for metric, b in bands.items():
        assert b["p10"] <= b["p25"] <= b["p50"] <= b["p75"] <= b["p90"], (
            f"{metric} bands not monotonic: {b}"
        )


def test_n_in_bands_positive(tmp_path):
    out = tmp_path / "out"
    rep = build_form_profiles(
        organized_root=out,
        injected={"Tennis": _tennis_frame(30)},
        write=True,
    )
    bands = rep["by_sport"]["Tennis"]["bands"]
    for metric, b in bands.items():
        assert b["n"] > 0, f"{metric} has n=0"


def test_banner_in_md(tmp_path):
    out = tmp_path / "out"
    build_form_profiles(
        organized_root=out,
        injected={"NBA": _nba_frame()},
        write=True,
    )
    text = (out / "NBA" / "_Form_Profiles.md").read_text(encoding="utf-8")
    assert "no edge claimed" in text.lower()
    assert "markets efficient" in text.lower()
    assert "calibration is not edge" in text.lower()


def test_wikilinks_present(tmp_path):
    out = tmp_path / "out"
    build_form_profiles(
        organized_root=out,
        injected={"NBA": _nba_frame()},
        write=True,
    )
    text = (out / "NBA" / "_Form_Profiles.md").read_text(encoding="utf-8")
    assert "[[_WhatWins" in text
    assert "[[_Index" in text


def test_person_free_no_title_case_names(tmp_path):
    """No two-word Title-Case sequences (proper names) outside headings/frontmatter."""
    import re
    out = tmp_path / "out"
    build_form_profiles(
        organized_root=out,
        injected={"NBA": _nba_frame(), "Tennis": _tennis_frame()},
        write=True,
    )
    for sport in ("NBA", "Tennis"):
        text = (out / sport / "_Form_Profiles.md").read_text(encoding="utf-8")
        # strip headings (#), frontmatter (---) and wikilink lines
        body_lines = [
            ln for ln in text.splitlines()
            if not ln.startswith("#") and not ln.startswith("---")
            and "[[" not in ln
        ]
        body = " ".join(body_lines)
        # two consecutive capitalized words not all-caps (e.g. "John Smith")
        matches = re.findall(r"\b([A-Z][a-z]+\s+[A-Z][a-z]+)\b", body)
        # allow sport names like "Key Stats" etc — filter single-word caps combos
        suspicious = [m for m in matches if m not in {
            "High band", "Low band", "See also", "Key Stats", "Form Profiles",
            "High Band", "Low Band",
        }]
        assert not suspicious, (
            f"[{sport}] possible proper name(s) in body: {suspicious}"
        )


def test_person_free_no_player_team_wikilinks(tmp_path):
    out = tmp_path / "out"
    build_form_profiles(
        organized_root=out,
        injected={"NBA": _nba_frame()},
        write=True,
    )
    text = (out / "NBA" / "_Form_Profiles.md").read_text(encoding="utf-8")
    assert "[[Players/" not in text
    assert "[[Teams/" not in text
    assert "/Players" not in text


def test_missing_parquet_skipped_honestly(tmp_path):
    out = tmp_path / "out"
    rep = build_form_profiles(
        organized_root=out,
        data_root=tmp_path / "empty",
        write=True,
    )
    assert rep["n_sports"] == 0
    for info in rep["by_sport"].values():
        assert "skipped" in info


def test_empty_nan_frame_skipped_honestly(tmp_path):
    out = tmp_path / "out"
    rep = build_form_profiles(
        organized_root=out,
        injected={"NBA": _empty_nba_frame()},
        write=True,
    )
    assert rep["by_sport"]["NBA"].get("skipped") is not None


def test_idempotent(tmp_path):
    out = tmp_path / "out"
    kw = dict(organized_root=out, injected={"NBA": _nba_frame(60)}, write=True)
    build_form_profiles(**kw)
    first = (out / "NBA" / "_Form_Profiles.md").read_text(encoding="utf-8")
    build_form_profiles(**kw)
    second = (out / "NBA" / "_Form_Profiles.md").read_text(encoding="utf-8")
    assert first == second


def test_note_contains_no_edge(tmp_path):
    rep = build_form_profiles(
        organized_root=tmp_path / "out",
        injected={"Tennis": _tennis_frame()},
        write=False,
    )
    assert "no edge claimed" in rep["_note"].lower()


def test_small_n_caveat(tmp_path):
    out = tmp_path / "out"
    # 3 rows -> pooled ~6 values -> below _SMALL_N threshold
    rep = build_form_profiles(
        organized_root=out,
        injected={"NBA": _nba_frame(3)},
        write=True,
    )
    assert rep["by_sport"]["NBA"].get("small_n") is True
    text = (out / "NBA" / "_Form_Profiles.md").read_text(encoding="utf-8")
    assert "indicative only" in text.lower()
