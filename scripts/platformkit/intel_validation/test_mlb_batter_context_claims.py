"""Per-file tests for mlb_batter_context_claims -- SYNTHETIC pitch frames
only (this worktree has no data/ dir). Run with:
  cd /c/Users/neelj/nba-ai-system && python -m pytest \
    scripts/platformkit/intel_validation/test_mlb_batter_context_claims.py -q
"""
from __future__ import annotations

import pandas as pd

from scripts.platformkit.intel_validation import mlb_batter_context_claims as m
from scripts.platformkit.intel_validation.claims_validator import validate_claim


def _pitch(batter, events, release_speed, pitch_type, stand, p_throws, xwoba, season=2022):
    return {"batter": batter, "events": events, "release_speed": release_speed,
            "pitch_type": pitch_type, "stand": stand, "p_throws": p_throws,
            "estimated_woba_using_speedangle": xwoba, "season": season}


def _derived(rows) -> pd.DataFrame:
    """Route raw pitch dicts through the REAL load_batter_rows derivation
    (via a temp parquet) so tests exercise the same bucket logic the
    producer ships, never a re-implemented copy."""
    import tempfile
    from pathlib import Path
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "statcast_fuller__2022.parquet"
        pd.DataFrame(rows).to_parquet(path)
        return m.load_batter_rows({2022: path})


def _synthetic_raw(n_hi=50, n_lo=50, batter=1):
    """One batter: n_hi PA-ending fastballs at 96 mph (xwoba=0.5), n_lo at
    90 mph (xwoba=0.2) -- same-hand (R/R) throughout, so velo/pitch_type
    bucket math is isolated from the platoon dimension."""
    rows = [_pitch(batter, "single", 96.0, "FF", "R", "R", 0.5) for _ in range(n_hi)]
    rows += [_pitch(batter, "field_out", 90.0, "FF", "R", "R", 0.2) for _ in range(n_lo)]
    return _derived(rows)


# --------------------------------------------------------------------------- #
# bucket derivation (load_batter_rows)
# --------------------------------------------------------------------------- #
def test_load_batter_rows_derives_velo_pitch_platoon_buckets(tmp_path):
    df = pd.DataFrame([
        _pitch(1, "single", 96.0, "FF", "R", "R", 0.5),   # hi velo, fastball, same-hand
        _pitch(1, "field_out", 90.0, "FF", "R", "L", 0.2),  # lo velo, fastball, opp-hand
        _pitch(1, "strikeout", 88.0, "SL", "R", "R", 0.1),  # breaking, gap-band velo (n/a), same-hand
        _pitch(1, "walk", 96.0, "FF", "R", "R", None),      # events notna but xwoba null -> DROPPED
        _pitch(1, None, 96.0, "FF", "R", "R", 0.9),         # events null -> not PA-ending -> DROPPED
    ])
    path = tmp_path / "statcast_fuller__2022.parquet"
    df.to_parquet(path)
    raw = m.load_batter_rows({2022: path})

    assert len(raw) == 3  # the walk (xwoba null) and the non-PA-ending row both dropped
    velo_counts = raw["velo_bucket"].value_counts(dropna=True).to_dict()
    assert velo_counts == {"hi": 1, "lo": 1}  # the SL row has no velo_bucket (not fastball-family)
    pitch_counts = raw["pitch_class"].value_counts(dropna=True).to_dict()
    assert pitch_counts == {"fastball": 2, "breaking": 1}
    platoon_counts = raw["platoon_match"].value_counts().to_dict()
    assert platoon_counts == {"same": 2, "opp": 1}


def test_discover_seasons_globs_never_hardcoded(tmp_path):
    for year in (2022, 2024):
        pd.DataFrame([_pitch(1, "single", 96.0, "FF", "R", "R", 0.5)]).to_parquet(
            tmp_path / f"statcast_fuller__{year}.parquet"
        )
    (tmp_path / "statcast_fuller__sample.parquet").write_bytes(b"")  # non-year file, must be ignored
    found = m.discover_seasons(tmp_path)
    assert sorted(found.keys()) == [2022, 2024]  # picks up whatever years exist, no hardcoded list


# --------------------------------------------------------------------------- #
# bucket math + floor skip + independent validator re-verification
# --------------------------------------------------------------------------- #
def test_snapshot_and_claim_bucket_math_and_independent_verify(tmp_path):
    raw = _synthetic_raw(n_hi=50, n_lo=50)
    snap_path, _ = m.build_snapshot(raw, "velo_bucket", "hi", "lo", m._OUT_DIR / "test_velo_snap.parquet")
    claim = m.build_delta_claim("vs_velocity", "2022", snap_path, {1: "Test Batter"}, [2022])

    assert claim["n_considered"] == 1
    assert claim["n_excluded_below_floor"] == 0
    assert abs(claim["ranking"][0]["value"] - (0.5 - 0.2)) < 1e-9
    assert claim["ranking"][0]["batter_name"] == "Test Batter"

    verdict = validate_claim(claim)
    assert verdict.verdict == "VERIFIED", verdict.reason
    snap_path.unlink()


def test_floor_skips_thin_batter():
    raw = _synthetic_raw(n_hi=39, n_lo=50)  # 39 < MIN_VELO_PA=40
    snap_path, _ = m.build_snapshot(raw, "velo_bucket", "hi", "lo", m._OUT_DIR / "test_thin_snap.parquet")
    claim = m.build_delta_claim("vs_velocity", "2022", snap_path, {}, [2022])

    assert claim["n_considered"] == 1
    assert claim["n_excluded_below_floor"] == 1
    assert claim["ranking"] == []  # honest-empty, never fabricated
    snap_path.unlink()


def test_platoon_sign_convention_documented():
    # batter does BETTER same-hand (0.6) than opposite-hand (0.3) -- the unusual case
    rows = [_pitch(1, "single", 90.0, "FF", "R", "R", 0.6) for _ in range(80)]
    rows += [_pitch(1, "field_out", 90.0, "FF", "R", "L", 0.3) for _ in range(80)]
    raw = _derived(rows)
    snap_path, _ = m.build_snapshot(raw, "platoon_match", "same", "opp", m._OUT_DIR / "test_platoon_snap.parquet")
    claim = m.build_delta_claim("platoon", "2022", snap_path, {}, [2022])

    assert claim["ranking"][0]["value"] > 0  # positive == better same-hand, per docstring/caveat
    assert "reverse of the typical platoon effect" in " ".join(claim["caveats"])
    snap_path.unlink()


# --------------------------------------------------------------------------- #
# PA definition consistency + no edge language
# --------------------------------------------------------------------------- #
def test_claim_declares_pa_definition_and_no_edge_language():
    raw = _synthetic_raw(n_hi=50, n_lo=50)
    snap_path, _ = m.build_snapshot(raw, "velo_bucket", "hi", "lo", m._OUT_DIR / "test_pa_snap.parquet")
    claim = m.build_delta_claim("vs_velocity", "2022", snap_path, {}, [2022])
    text = " ".join(claim["caveats"]).lower() + claim["question"].lower()

    assert "estimated_woba_using_speedangle" in " ".join(claim["caveats"])
    assert "batted-ball" in " ".join(claim["caveats"])
    banned = ("18.38", "0.119", "+54%", "78.11", "8.94", "54.57", "roi", "bankroll", "pnl")
    for token in banned:
        assert token not in text, f"banned token {token!r} found in claim text"
    assert "no forecasting/market/$ edge claimed" in text
    snap_path.unlink()


def test_build_all_claims_never_empty_with_data(tmp_path, monkeypatch):
    pd.DataFrame([
        _pitch(1, "single", 96.0, "FF", "R", "R", 0.5),
        _pitch(1, "field_out", 90.0, "FF", "R", "L", 0.2),
    ]).to_parquet(tmp_path / "statcast_fuller__2022.parquet")
    claims = m.build_all_claims(tmp_path)
    assert len(claims) == 6  # 3 metrics x (1 year + 1 pooled)
    assert all(c["ranking"] is not None for c in claims)  # rankings key always present (may be [])
    # invariant (2026-07-19 review fix): every emitted claim declares
    # edge_claimed False, matching every sibling claim producer.
    assert all(c["edge_claimed"] is False for c in claims)
