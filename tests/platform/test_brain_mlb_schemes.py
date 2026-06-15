"""tests.platform.test_brain_mlb_schemes — hermetic tests for brain_mlb_schemes.

Uses the ``injected`` seam with small synthetic DataFrames so no real parquets are
required.  Asserts: bands are monotonic, each scheme has its threshold + share, the
rendered note contains the honest banner + cross-links, the note is person-free (no
two-word Title-Case proper-noun names that look like people), and the build skips
honestly when parquets are missing.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.platformkit.brain_mlb_schemes import build_mlb_schemes  # noqa: E402


# ---------------------------------------------------------------------------
# Synthetic fixtures
# ---------------------------------------------------------------------------

try:
    import pandas as pd
    _HAS_PANDAS = True
except ImportError:
    _HAS_PANDAS = False

pytestmark = pytest.mark.skipif(not _HAS_PANDAS, reason="pandas not available")


def _make_features(n: int = 120) -> "pd.DataFrame":
    """Synthetic asof_features-shaped frame with sp_ra and sp_starts_prior columns."""
    import numpy as np

    rng = pd.Series(range(n))
    sp_ra_vals = [3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0, 7.0] * (n // 8 + 1)
    starts_vals = [5, 10, 20, 40, 80, 120, 160, 200] * (n // 8 + 1)
    return pd.DataFrame({
        "event_id": rng,
        "home_sp_ra_asof": sp_ra_vals[:n],
        "away_sp_ra_asof": [v + 0.2 for v in sp_ra_vals[:n]],
        "sp_ra_diff_asof": [0.2] * n,
        "home_sp_starts_prior": starts_vals[:n],
        "away_sp_starts_prior": [v + 5 for v in starts_vals[:n]],
    })


def _make_park(n: int = 120) -> "pd.DataFrame":
    """Synthetic asof_park-shaped frame with park_factor column."""
    park_vals = [0.85, 0.90, 0.95, 0.99, 1.01, 1.07, 1.12, 1.20] * (n // 8 + 1)
    return pd.DataFrame({
        "event_id": list(range(n)),
        "park_total_mean": [8.5] * n,
        "park_factor": park_vals[:n],
        "park_n_prior": [300] * n,
    })


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_build_returns_result_dict() -> None:
    """build_mlb_schemes returns a dict with expected top-level keys."""
    rep = build_mlb_schemes(
        write=False,
        injected={"features": _make_features(), "park": _make_park()},
    )
    assert "skipped" not in rep, f"Unexpected skip: {rep}"
    assert "n_games" in rep
    assert "schemes" in rep
    assert "ra_bands" in rep
    assert "park_bands" in rep
    assert "pitching_schemes_md" in rep


def test_bands_are_monotonic() -> None:
    """All percentile bands are non-decreasing (p10 <= p25 <= p50 <= p75 <= p90)."""
    rep = build_mlb_schemes(
        write=False,
        injected={"features": _make_features(), "park": _make_park()},
    )
    for key in ("ra_bands", "starts_bands", "park_bands"):
        b = rep[key]
        vals = [b[k] for k in ("p10", "p25", "p50", "p75", "p90")]
        assert vals == sorted(vals), f"{key} not monotonic: {vals}"


def test_all_schemes_have_band_and_share() -> None:
    """Each scheme entry carries a non-empty 'band' string and a numeric 'share'."""
    rep = build_mlb_schemes(
        write=False,
        injected={"features": _make_features(), "park": _make_park()},
    )
    schemes = rep["schemes"]
    assert len(schemes) >= 5, "Expected at least 5 schemes"
    for s in schemes:
        assert s["band"], f"Scheme '{s['name']}' has empty band"
        assert isinstance(s["share"], (int, float)), f"Scheme '{s['name']}' share not numeric"
        assert 0 <= s["share"] <= 100, f"Share out of range: {s}"


def test_bands_appear_in_rendered_note() -> None:
    """Scheme threshold numbers from the real bands appear in the rendered Markdown."""
    rep = build_mlb_schemes(
        write=False,
        injected={"features": _make_features(), "park": _make_park()},
    )
    md = rep["pitching_schemes_md"]
    # p25 of sp_ra must appear in the note (it anchors the elite-starter scheme)
    ra_p25 = str(rep["ra_bands"]["p25"])
    assert ra_p25 in md, f"ra_bands p25={ra_p25} not found in rendered note"
    # p25 of park_factor must appear (suppression park scheme)
    pk_p25 = str(rep["park_bands"]["p25"])
    assert pk_p25 in md, f"park_bands p25={pk_p25} not found in rendered note"


def test_rendered_note_has_honest_banner() -> None:
    """Rendered note contains the honest calibration/efficiency banner."""
    rep = build_mlb_schemes(
        write=False,
        injected={"features": _make_features(), "park": _make_park()},
    )
    md = rep["pitching_schemes_md"]
    assert "markets efficient" in md
    assert "calibration is not edge" in md
    assert "no edge claimed" in md


def test_rendered_note_has_cross_links() -> None:
    """Rendered note contains wikilinks to _WhatWins and at least one archetype."""
    rep = build_mlb_schemes(
        write=False,
        injected={"features": _make_features(), "park": _make_park()},
    )
    md = rep["pitching_schemes_md"]
    assert "[[_WhatWins" in md, "_WhatWins cross-link missing"
    assert "[[Archetypes/" in md, "Archetypes cross-link missing"


def test_person_free_no_proper_noun_people() -> None:
    """Rendered note must not contain two-word Title-Case person names.

    Scheme/concept names are Title-Case and acceptable.  We guard against
    sequences like 'John Smith' (two capitalised words separated by a space
    that are NOT known concept keywords).
    """
    rep = build_mlb_schemes(
        write=False,
        injected={"features": _make_features(), "park": _make_park()},
    )
    md = rep["pitching_schemes_md"]
    # Allowlist: concept-level Title-Case tokens that are fine
    _CONCEPT_WORDS = frozenset({
        "MLB", "Pitching", "Schemes", "Run", "Environment", "Taxonomy",
        "Rotation", "Anchored", "Prevention", "Bullpen", "Dependent",
        "Starter", "Volatile", "Thin", "Sample", "Short", "Leash", "Profile",
        "Park", "Suppressed", "Power", "High", "Balanced", "Staff", "Neutral",
        "Signal", "Distributions", "Corpus", "Bands", "Scheme", "Reading",
        "Honestly", "Descriptive", "Calibration", "Key", "Stats", "Form",
        "Index", "Archetypes", "Pitcher", "Contender", "Grinder", "Offense",
        "What", "Wins", "Why", "See", "Also", "Cross", "Links", "Not",
        "Big", "Inning", "Swing", "Scoring", "Vault", "Organized",
    })
    # Pattern: two capitalised words (first letter upper, rest any, no digits)
    pattern = re.compile(r'\b([A-Z][a-z]+)\s+([A-Z][a-z]+)\b')
    for m in pattern.finditer(md):
        w1, w2 = m.group(1), m.group(2)
        if w1 not in _CONCEPT_WORDS and w2 not in _CONCEPT_WORDS:
            # heuristic: if NEITHER word is in our concept set, flag it
            pytest.fail(
                f"Possible person name found in note: '{w1} {w2}' — ensure note is person-free"
            )


def test_skip_on_missing_injected_key() -> None:
    """Skips honestly when injected dict is missing required keys."""
    rep = build_mlb_schemes(write=False, injected={"features": _make_features()})
    assert "skipped" in rep


def test_skip_on_empty_injected() -> None:
    """Skips honestly when injected dict is completely empty."""
    rep = build_mlb_schemes(write=False, injected={})
    assert "skipped" in rep


def test_write_creates_file(tmp_path: Path) -> None:
    """With write=True, the note is written to <organized_root>/MLB/_Pitching_Schemes.md."""
    rep = build_mlb_schemes(
        organized_root=tmp_path,
        write=True,
        injected={"features": _make_features(), "park": _make_park()},
    )
    assert "skipped" not in rep
    out = tmp_path / "MLB" / "_Pitching_Schemes.md"
    assert out.exists(), f"Expected {out} to be created"
    content = out.read_text(encoding="utf-8")
    assert "Pitching Schemes" in content
    assert "markets efficient" in content


def test_skip_on_real_missing_parquet(tmp_path: Path) -> None:
    """When parquets don't exist on disk, returns a skip result (no crash)."""
    rep = build_mlb_schemes(data_root=tmp_path, write=False)
    assert "skipped" in rep, "Expected skip on missing parquet files"


def test_n_schemes() -> None:
    """We produce exactly 6 schemes (the full taxonomy)."""
    rep = build_mlb_schemes(
        write=False,
        injected={"features": _make_features(), "park": _make_park()},
    )
    assert rep["n_schemes"] == 6
