"""Tests for scripts.platformkit.brain_tennis_depth — hermetic via injected seam.

Asserts: thresholds monotonic; each style has band+share; banner+wikilinks present;
person-free; skip-on-missing; idempotent.
"""
from __future__ import annotations

import re

import pandas as pd

from scripts.platformkit.brain_tennis_depth import (
    build_tennis_depth,
    _compute_thresholds,
    _pool_metric,
    _style_share,
    _STYLE_SPECS,
    _METRICS,
)


# ---------------------------------------------------------------------------
# Synthetic data helpers
# ---------------------------------------------------------------------------

def _make_df(n: int = 60, seed: int = 42) -> pd.DataFrame:
    import random
    rng = random.Random(seed)
    rows = [{"event_id": f"t{i}",
             "p1_ace_rate_asof": rng.uniform(0.02, 0.22), "p2_ace_rate_asof": rng.uniform(0.02, 0.22),
             "p1_1st_in_asof":   rng.uniform(0.54, 0.76), "p2_1st_in_asof":   rng.uniform(0.54, 0.76),
             "p1_1st_win_asof":  rng.uniform(0.62, 0.84), "p2_1st_win_asof":  rng.uniform(0.62, 0.84),
             "p1_2nd_win_asof":  rng.uniform(0.43, 0.64), "p2_2nd_win_asof":  rng.uniform(0.43, 0.64),
             "p1_bp_saved_asof": rng.uniform(0.48, 0.76), "p2_bp_saved_asof": rng.uniform(0.48, 0.76),
             } for i in range(n)]
    return pd.DataFrame(rows)


def _make_empty_df() -> pd.DataFrame:
    df = _make_df(5)
    df[[c for c in df.columns if c != "event_id"]] = float("nan")
    return df


# ---------------------------------------------------------------------------
# Unit tests for helpers
# ---------------------------------------------------------------------------

def test_pool_metric_concatenates_and_drops_nan():
    df = pd.DataFrame({
        "p1_ace_rate_asof": [0.05, 0.10, float("nan")],
        "p2_ace_rate_asof": [0.08, 0.12, 0.15],
    })
    series = _pool_metric(df, ["p1_ace_rate_asof", "p2_ace_rate_asof"])
    assert len(series) == 5, f"expected 5 values, got {len(series)}"
    assert series.isna().sum() == 0


def test_pool_metric_missing_col_skipped():
    df = pd.DataFrame({"p1_ace_rate_asof": [0.05, 0.10]})
    series = _pool_metric(df, ["p1_ace_rate_asof", "nonexistent_col"])
    assert list(series) == [0.05, 0.10]


def test_compute_thresholds_monotonic():
    df = _make_df(80)
    thr = _compute_thresholds(df)
    assert thr, "should compute at least one metric"
    for metric, b in thr.items():
        assert b["p33"] <= b["p50"] <= b["p67"], (
            f"{metric}: thresholds not monotonic: {b}"
        )


def test_compute_thresholds_all_five_metrics():
    df = _make_df(60)
    thr = _compute_thresholds(df)
    expected = {m for m, _ in _METRICS}
    assert set(thr.keys()) == expected


def test_compute_thresholds_n_positive():
    df = _make_df(40)
    thr = _compute_thresholds(df)
    for metric, b in thr.items():
        assert b["n"] > 0, f"{metric} has n=0"


def test_style_share_between_0_and_1():
    df = _make_df(80)
    thr = _compute_thresholds(df)
    for spec in _STYLE_SPECS:
        share = _style_share(df, spec, thr)
        if share is not None:
            assert 0.0 <= share <= 1.0, f"{spec['name']} share={share} out of [0,1]"


# ---------------------------------------------------------------------------
# End-to-end via injected seam
# ---------------------------------------------------------------------------

def test_builds_successfully_from_injected(tmp_path):
    rep = build_tennis_depth(
        organized_root=tmp_path / "out",
        injected=_make_df(80),
        write=True,
    )
    assert "skipped" not in rep
    assert rep["n_rows"] > 0
    assert len(rep["styles"]) == 4
    md_path = tmp_path / "out" / "Tennis" / "_Serve_Return_Archetypes.md"
    assert md_path.is_file()


def test_thresholds_monotonic_in_result(tmp_path):
    rep = build_tennis_depth(
        organized_root=tmp_path / "out",
        injected=_make_df(80),
        write=False,
    )
    for metric, b in rep["thresholds"].items():
        assert b["p33"] <= b["p50"] <= b["p67"], (
            f"{metric} thresholds not monotonic: {b}"
        )


def test_each_style_has_share(tmp_path):
    rep = build_tennis_depth(
        organized_root=tmp_path / "out",
        injected=_make_df(80),
        write=False,
    )
    for st in rep["styles"]:
        assert st["share"] is not None, f"{st['name']} has no share"
        assert 0.0 <= st["share"] <= 1.0


def test_banner_in_note(tmp_path):
    rep = build_tennis_depth(
        organized_root=tmp_path / "out",
        injected=_make_df(60),
        write=True,
    )
    md = (tmp_path / "out" / "Tennis" / "_Serve_Return_Archetypes.md").read_text(
        encoding="utf-8"
    )
    assert "no edge claimed" in md.lower()
    assert "markets efficient" in md.lower()
    assert "calibration is not edge" in md.lower()


def test_archetype_wikilinks_present(tmp_path):
    rep = build_tennis_depth(
        organized_root=tmp_path / "out",
        injected=_make_df(60),
        write=True,
    )
    md = (tmp_path / "out" / "Tennis" / "_Serve_Return_Archetypes.md").read_text(
        encoding="utf-8"
    )
    # All four style wikilinks should appear
    assert "[[Archetypes/Fast_Court_Big_Server]]" in md
    assert "[[Archetypes/All_Court_Baseliner]]" in md
    assert "[[Archetypes/Clay_Court_Specialist]]" in md
    assert "[[Archetypes/Hard_Court_Specialist]]" in md


def test_band_threshold_values_in_note(tmp_path):
    """The rendered note must contain actual numeric threshold values."""
    rep = build_tennis_depth(
        organized_root=tmp_path / "out",
        injected=_make_df(80),
        write=True,
    )
    md = (tmp_path / "out" / "Tennis" / "_Serve_Return_Archetypes.md").read_text(
        encoding="utf-8"
    )
    # Threshold table row for ace_rate must contain a decimal number
    assert re.search(r"ace_rate.*\d+\.\d{3,}", md), (
        "ace_rate threshold not found in note"
    )


def test_style_share_in_note(tmp_path):
    """Each style section must show a percentage share."""
    build_tennis_depth(
        organized_root=tmp_path / "out",
        injected=_make_df(80),
        write=True,
    )
    md = (tmp_path / "out" / "Tennis" / "_Serve_Return_Archetypes.md").read_text(
        encoding="utf-8"
    )
    # At least one share percentage must appear
    assert re.search(r"\d+\.\d+%", md), "No share percentage found in note"


def test_person_free_no_player_name_patterns(tmp_path):
    """No two-word Title-Case proper-name sequences in prose body.

    Style concept names (Big Server, All Court, etc.) are allowed — these are
    descriptive concepts, not people. The check is applied to body text with
    headings, frontmatter, and wikilink lines stripped.
    """
    build_tennis_depth(
        organized_root=tmp_path / "out",
        injected=_make_df(60),
        write=True,
    )
    md = (tmp_path / "out" / "Tennis" / "_Serve_Return_Archetypes.md").read_text(
        encoding="utf-8"
    )
    body_lines = [
        ln for ln in md.splitlines()
        if not ln.startswith("#")
        and not ln.startswith("---")
        and not ln.startswith("tags:")
        and "[[" not in ln
    ]
    body = " ".join(body_lines)
    matches = re.findall(r"\b([A-Z][a-z]+\s+[A-Z][a-z]+)\b", body)
    # Permitted style-concept phrases (descriptive, not player names)
    allowed = {
        "Big Server", "All Court", "Hard Court", "Clay Court",
        "Fast Court", "Grand Slam", "See Also", "Corpus Share",
        "Reading This", "Stat Signature", "Defining Bands",
        "Corpus Percentile", "Serve Return", "First Strike",
    }
    suspicious = [m for m in matches if m not in allowed]
    assert not suspicious, f"Possible player names in body: {suspicious}"


def test_no_players_or_teams_wikilinks(tmp_path):
    build_tennis_depth(
        organized_root=tmp_path / "out",
        injected=_make_df(60),
        write=True,
    )
    md = (tmp_path / "out" / "Tennis" / "_Serve_Return_Archetypes.md").read_text(
        encoding="utf-8"
    )
    assert "[[Players/" not in md
    assert "[[Teams/" not in md


def test_skip_on_missing_parquet(tmp_path):
    rep = build_tennis_depth(
        organized_root=tmp_path / "out",
        data_root=tmp_path / "empty_data",
        write=True,
    )
    assert "skipped" in rep
    assert "missing parquet" in rep["skipped"].lower()


def test_skip_on_all_nan_frame(tmp_path):
    rep = build_tennis_depth(
        organized_root=tmp_path / "out",
        injected=_make_empty_df(),
        write=True,
    )
    assert "skipped" in rep


def test_note_contains_no_edge_in_meta(tmp_path):
    rep = build_tennis_depth(
        organized_root=tmp_path / "out",
        injected=_make_df(60),
        write=False,
    )
    assert "no edge claimed" in rep["_note"].lower()


def test_idempotent(tmp_path):
    out = tmp_path / "out"
    kw = dict(organized_root=out, injected=_make_df(80), write=True)
    build_tennis_depth(**kw)
    first = (out / "Tennis" / "_Serve_Return_Archetypes.md").read_text(
        encoding="utf-8"
    )
    build_tennis_depth(**kw)
    second = (out / "Tennis" / "_Serve_Return_Archetypes.md").read_text(
        encoding="utf-8"
    )
    assert first == second, "Note content changed on second run (not idempotent)"


def test_small_n_caveat(tmp_path):
    """Very small frame -> small_n=True and caveat in note."""
    rep = build_tennis_depth(
        organized_root=tmp_path / "out",
        injected=_make_df(3),
        write=True,
    )
    # 3 rows * 2 sides = 6 pooled rows, well below _SMALL_N=50
    assert rep.get("small_n") is True
    md = (tmp_path / "out" / "Tennis" / "_Serve_Return_Archetypes.md").read_text(
        encoding="utf-8"
    )
    assert "indicative only" in md.lower()
