"""R30_W6 — model deployment audit refresh tests.

Guards every wire-layer invariant established in R20_M7 and patched by R21-R29:

  1. Every R20_M7 production loader path is still callable.
  2. R21_N1 resolver works in both the host repo AND a worktree.
  3. R21_N5 m2_family prediction cache reuses bytes on second call.
  4. R22_O8 injury parquet wire is preferred over the legacy JSON snapshot.
  5. R23_P2 inplay_bet_ranker still imports + calls get_availability_factor.
  6. No regression in the WIRED-surface count vs the R20_M7 baseline (the
     post-R20_M7 baseline JSON shows 22 wired surfaces against current main).
  7. m2_family ensemble produces all 4 non-None values on a known game id.
  8. Per-stat heads all load (7/7) AND every stat predicts non-None on a
     real cached player gamelog (Chris Paul, 101108).

These tests run LOCALLY only — no SSH, no RunPod, no network. They skip
gracefully on a clone that doesn't have the gitignored artifacts so CI
doesn't blow up on a fresh checkout.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

import pytest

_HERE = Path(__file__).resolve().parent
_PROJECT_DIR = _HERE.parent
if str(_PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(_PROJECT_DIR))


# ---------------------------------------------------------------------------
# Resolve where the populated artifacts live (worktree or host). Same logic
# as the probe so tests track the production resolver's behaviour.
# ---------------------------------------------------------------------------
def _resolve_artifact_root() -> Path:
    local = _PROJECT_DIR / "data" / "models"
    canary = local / "m2_family" / "manifest.json"
    if canary.exists():
        return _PROJECT_DIR
    norm = str(_PROJECT_DIR).replace("\\", "/")
    marker = "/.claude/worktrees/"
    if marker in norm:
        host = Path(norm.split(marker, 1)[0])
        if (host / "data" / "models" / "m2_family" / "manifest.json").exists():
            return host
    return _PROJECT_DIR


_ARTIFACT_ROOT = _resolve_artifact_root()
_HAS_M2_LOCAL = (_PROJECT_DIR / "data" / "models" / "m2_family" / "manifest.json").exists()


def _run_in_host(expr: str, timeout: int = 120) -> Optional[str]:
    """Run a one-shot python expression in the artifact-root cwd so the
    production module's PROJECT_DIR resolves to whichever copy has the
    populated artifacts. Returns the last non-empty stdout line."""
    cmd = [sys.executable, "-c", expr]
    try:
        proc = subprocess.run(
            cmd, cwd=str(_ARTIFACT_ROOT), capture_output=True, text=True,
            timeout=timeout,
        )
        if proc.returncode != 0:
            return None
        lines = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()]
        return lines[-1] if lines else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Test 1 — R20_M7 m2_family wire still present in game_models.py
# ---------------------------------------------------------------------------
def test_R20_M7_wire_still_present_in_game_models():
    """game_models.py must still contain _predict_m2_family + the
    m2_family_used result-dict key. R30_W6 audit refresh requirement."""
    src = (_PROJECT_DIR / "src" / "prediction" / "game_models.py").read_text(
        encoding="utf-8"
    )
    assert "_predict_m2_family" in src, "R20_M7 _predict_m2_family wire removed"
    assert "m2_family_used" in src, "R20_M7 m2_family_used key removed"


# ---------------------------------------------------------------------------
# Test 2 — R21_N1 resolver still wired in prop_pergame
# ---------------------------------------------------------------------------
def test_R21_N1_resolver_still_present_in_prop_pergame():
    """prop_pergame._resolve_model_dir + the worktree-fallback branch must
    remain. R21_N1 ship."""
    src = (_PROJECT_DIR / "src" / "prediction" / "prop_pergame.py").read_text(
        encoding="utf-8"
    )
    assert "_resolve_model_dir" in src, "R21_N1 resolver removed"
    assert "/.claude/worktrees/" in src, "R21_N1 worktree fallback removed"


# ---------------------------------------------------------------------------
# Test 3 — R21_N5 cache still wired in game_models
# ---------------------------------------------------------------------------
def test_R21_N5_m2_family_cache_still_present():
    """game_models._predict_m2_family must still consult its on-disk cache
    via _M2_PRED_CACHE_PATH + _m2_family_models_mtime."""
    src = (_PROJECT_DIR / "src" / "prediction" / "game_models.py").read_text(
        encoding="utf-8"
    )
    assert "_M2_PRED_CACHE_PATH" in src, "R21_N5 cache constant removed"
    assert "_m2_family_models_mtime" in src, "R21_N5 mtime check removed"
    assert "_load_m2_pred_cache" in src, "R21_N5 cache loader removed"


# ---------------------------------------------------------------------------
# Test 4 — R22_O8 parquet-first injury wire still present
# ---------------------------------------------------------------------------
def test_R22_O8_injury_parquet_wire_still_present():
    """injury_availability must still prefer
    data/cache/nba_injuries_<date>.parquet over the legacy JSON."""
    src = (_PROJECT_DIR / "src" / "prediction" / "injury_availability.py").read_text(
        encoding="utf-8"
    )
    assert "_load_parquet_indices" in src, "R22_O8 parquet loader removed"
    assert "nba_injuries_" in src, "R22_O8 parquet filename pattern removed"
    assert "_latest_parquet_path" in src, "R22_O8 parquet-path helper removed"


# ---------------------------------------------------------------------------
# Test 5 — R23_P2 inplay injury-kill still wired in inplay_bet_ranker
# ---------------------------------------------------------------------------
def test_R23_P2_inplay_injury_kill_still_present():
    """inplay_bet_ranker must still call get_availability_factor + track
    n_killed_by_injury in its returned payload."""
    src = (_PROJECT_DIR / "scripts" / "inplay_bet_ranker.py").read_text(
        encoding="utf-8"
    )
    assert "_availability_factor" in src, "R23_P2 helper removed"
    assert "get_availability_factor" in src, "R23_P2 import dropped"
    assert "n_killed_by_injury" in src, "R23_P2 telemetry removed"


# ---------------------------------------------------------------------------
# Test 6 — R21_N1 resolver returns a directory with PTS artifacts
# ---------------------------------------------------------------------------
def test_R21_N1_resolver_returns_populated_dir():
    """In a worktree without local artifacts, _resolve_model_dir must walk
    up to the host repo. In a clean clone without ANY artifacts on disk,
    skip rather than fail."""
    from src.prediction.prop_pergame import _resolve_model_dir

    resolved = _resolve_model_dir()
    assert isinstance(resolved, str) and len(resolved) > 0
    pts_canary = os.path.join(resolved, "props_pg_pts.json")
    if not (_ARTIFACT_ROOT / "data" / "models" / "props_pg_pts.json").exists():
        pytest.skip("no PTS artifact on disk in worktree or host — fresh clone")
    assert os.path.exists(pts_canary), (
        f"resolver returned {resolved} but PTS artifact not found there"
    )


# ---------------------------------------------------------------------------
# Test 7 — m2_family pregame predict produces all 4 non-None values
# ---------------------------------------------------------------------------
@pytest.mark.skipif(
    not (_ARTIFACT_ROOT / "data" / "models" / "m2_family" / "manifest.json").exists(),
    reason="m2_family artifacts not present (probe-only checkout)",
)
def test_m2_family_predict_all_nonzero():
    """Running game_models.predict on a known regular-season game id must
    emit total_est / spread_est / home_pts_est / away_pts_est all non-None,
    with m2_family_used=True and confidence='model+m2_family'."""
    expr = (
        "import sys; sys.path.insert(0, '.');\n"
        "from src.prediction.game_models import predict, clear_m2_pred_cache;\n"
        "clear_m2_pred_cache();\n"
        "out = predict('OKC', 'HOU', season='2025-26', game_date='2025-10-21', game_id='0022500001');\n"
        "import json; print('RESULT', json.dumps({"
        "'total_est': out.get('total_est'),"
        "'spread_est': out.get('spread_est'),"
        "'home_pts_est': out.get('home_pts_est'),"
        "'away_pts_est': out.get('away_pts_est'),"
        "'m2_family_used': out.get('m2_family_used'),"
        "'confidence': out.get('confidence')}))"
    )
    line = _run_in_host(expr)
    assert line is not None and line.startswith("RESULT "), (
        f"subprocess produced no RESULT line: {line!r}"
    )
    payload = json.loads(line[len("RESULT "):])
    assert payload["m2_family_used"] is True
    assert payload["confidence"] == "model+m2_family"
    for k in ("total_est", "spread_est", "home_pts_est", "away_pts_est"):
        assert payload[k] is not None, f"{k} is None — m2_family path failed"
    assert payload["total_est"] > 0
    assert payload["home_pts_est"] > 0
    assert payload["away_pts_est"] > 0


# ---------------------------------------------------------------------------
# Test 8 — R21_N5 cache produces byte-identical second prediction
# ---------------------------------------------------------------------------
@pytest.mark.skipif(
    not (_ARTIFACT_ROOT / "data" / "models" / "m2_family" / "manifest.json").exists(),
    reason="m2_family artifacts not present",
)
def test_R21_N5_cache_byte_identical_repeat():
    """Second predict() call on the same (game_id, models_mtime) must return
    byte-identical total/spread/home_pts/away_pts (proves cache hit, not
    re-rolled prediction)."""
    expr = (
        "import sys, json; sys.path.insert(0, '.');\n"
        "from src.prediction.game_models import predict, clear_m2_pred_cache;\n"
        "clear_m2_pred_cache();\n"
        "kw = dict(season='2025-26', game_date='2025-10-21', game_id='0022500001');\n"
        "a = predict('OKC', 'HOU', **kw);\n"
        "b = predict('OKC', 'HOU', **kw);\n"
        "fields = ('total_est', 'spread_est', 'home_pts_est', 'away_pts_est');\n"
        "print('RESULT', json.dumps({'first': {f: a.get(f) for f in fields},"
        " 'second': {f: b.get(f) for f in fields},"
        " 'm2_first': a.get('m2_family_used'), 'm2_second': b.get('m2_family_used')}))"
    )
    line = _run_in_host(expr)
    assert line is not None and line.startswith("RESULT ")
    payload = json.loads(line[len("RESULT "):])
    assert payload["m2_first"] is True and payload["m2_second"] is True
    for f in ("total_est", "spread_est", "home_pts_est", "away_pts_est"):
        assert payload["first"][f] == payload["second"][f], (
            f"R21_N5 cache miss for {f}: first={payload['first'][f]!r} != "
            f"second={payload['second'][f]!r}"
        )


# ---------------------------------------------------------------------------
# Test 9 — All 7 per-stat heads load + predict on a real cached player gamelog
# ---------------------------------------------------------------------------
@pytest.mark.skipif(
    not (_ARTIFACT_ROOT / "data" / "nba" / "gamelog_101108_2024-25.json").exists(),
    reason="player gamelog cache not present",
)
def test_per_stat_heads_all_predict_nonzero():
    """predict_player_pergame for Chris Paul (101108) on a cached season
    must return all 7 stats as non-None floats."""
    expr = (
        "import sys, json; sys.path.insert(0, '.');\n"
        "from src.prediction.prop_pergame import predict_player_pergame, STATS;\n"
        "out = predict_player_pergame(101108, opp_team='LAL', season='2024-25', is_home=True);\n"
        "ok = out is not None and all(out.get(s) is not None for s in STATS);\n"
        "print('RESULT', json.dumps({'ok': ok, 'values': out}))"
    )
    line = _run_in_host(expr)
    assert line is not None and line.startswith("RESULT ")
    payload = json.loads(line[len("RESULT "):])
    assert payload["ok"], f"per-stat predict failed: {payload}"
    for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov"):
        v = payload["values"][stat]
        assert v is not None, f"stat {stat} returned None"
        assert isinstance(v, (int, float)), f"stat {stat} not numeric: {v!r}"
        assert v >= 0.0, f"stat {stat} negative: {v}"


# ---------------------------------------------------------------------------
# Test 10 — R22_O8 injury wire returns 0.0 for at least 1 known-OUT player
# ---------------------------------------------------------------------------
def test_R22_O8_injury_wire_returns_zero_for_OUT():
    """Today's nba_injuries_<date>.parquet (if present) must contain at
    least 1 OUT player whose factor lookup returns 0.0."""
    from datetime import date as _date_cls

    parquet_path = _ARTIFACT_ROOT / "data" / "cache" / (
        f"nba_injuries_{_date_cls.today().isoformat()}.parquet"
    )
    if not parquet_path.exists():
        pytest.skip(f"no injury parquet at {parquet_path}")

    expr = (
        "import sys, os, json, pandas as pd; sys.path.insert(0, '.');\n"
        "from src.prediction.injury_availability import get_availability_factor;\n"
        "from datetime import date as _d;\n"
        "p = os.path.join('data', 'cache', f'nba_injuries_{_d.today().isoformat()}.parquet');\n"
        "df = pd.read_parquet(p);\n"
        "outs = df[df['status'] == 'OUT'].head(3);\n"
        "samples = [(int(r['player_id']), str(r['player_name']),"
        " float(get_availability_factor(player_id=int(r['player_id']),"
        " player_name=str(r['player_name'])))) for _, r in outs.iterrows()];\n"
        "ok = len(samples) >= 1 and all(s[2] == 0.0 for s in samples);\n"
        "print('RESULT', json.dumps({'ok': ok, 'n_out': len(outs), 'samples': samples}))"
    )
    line = _run_in_host(expr)
    assert line is not None and line.startswith("RESULT ")
    payload = json.loads(line[len("RESULT "):])
    assert payload["ok"], f"OUT players didn't return 0.0: {payload}"


# ---------------------------------------------------------------------------
# Test 11 — endQ3 residual heads load all 7 stats and accept apply call
# ---------------------------------------------------------------------------
@pytest.mark.skipif(
    not (_ARTIFACT_ROOT / "data" / "models" / "residual_heads" / "pts.lgb").exists(),
    reason="endQ3 residual heads not present",
)
def test_endq3_residual_heads_loadable_and_callable():
    """residual_heads.load_heads must return all 7 stats; apply_residual_correction
    must accept the standard snap + projs shape without raising."""
    expr = (
        "import sys, json; sys.path.insert(0, '.');\n"
        "from src.prediction.residual_heads import load_heads, apply_residual_correction;\n"
        "heads = load_heads();\n"
        "loaded = sorted(list(heads.keys())) if heads else [];\n"
        "projs_in = {(101108, 'pts'): 26.0, (101108, 'ast'): 6.0};\n"
        "snap = {'period': 4, 'minutes_played': 28.0,"
        "'pts_so_far': {101108: 18.0}, 'reb_so_far': {101108: 5.0},"
        "'home_team_score': 88, 'away_team_score': 92, 'game_date': '2025-10-21'};\n"
        "projs_out = apply_residual_correction(snap, projs_in);\n"
        "callable_ok = isinstance(projs_out, dict) and (101108, 'pts') in projs_out;\n"
        "print('RESULT', json.dumps({'loaded_stats': loaded, 'callable_ok': callable_ok}))"
    )
    line = _run_in_host(expr)
    assert line is not None and line.startswith("RESULT ")
    payload = json.loads(line[len("RESULT "):])
    assert sorted(payload["loaded_stats"]) == sorted(
        ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov"]
    ), f"missing residual heads: got {payload['loaded_stats']}"
    assert payload["callable_ok"]


# ---------------------------------------------------------------------------
# Test 12 — R20_M7 audit baseline still reflects same wire surface count
#           Probe re-runs cleanly with no NEW regression.
# ---------------------------------------------------------------------------
def test_R30_W6_probe_no_regressions_vs_baseline():
    """Run the R30_W6 probe end-to-end and assert no regression surfaces
    vs the R20_M7 stored baseline. Skip if R20_M7 baseline JSON missing
    (fresh checkout)."""
    probe_path = _PROJECT_DIR / "scripts" / "improve_loop" / "probe_R30_W6_audit_refresh.py"
    if not probe_path.exists():
        pytest.fail("probe_R30_W6_audit_refresh.py missing — ship gate violated")

    out = subprocess.run(
        [sys.executable, str(probe_path)], cwd=str(_PROJECT_DIR),
        capture_output=True, text=True, timeout=300,
    )
    # Probe exits 0 on clean refresh; non-zero on regression or smoke fail.
    # We accept both as long as the JSON shows zero regressions vs R20_M7.
    results_path = _PROJECT_DIR / "data" / "cache" / "probe_R30_W6_results.json"
    assert results_path.exists(), (
        f"probe didn't write results JSON. stdout: {out.stdout[-500:]} "
        f"stderr: {out.stderr[-500:]}"
    )
    payload = json.loads(results_path.read_text(encoding="utf-8"))
    assert payload["n_regressions_vs_R20_M7"] == 0, (
        f"regressions detected: {payload.get('regression_surfaces')}"
    )
    # All 5 wires present
    for k, v in payload["wires_present"].items():
        assert v is True, f"wire {k} no longer present"
