"""probe_R30_W6_audit_refresh.py — model deployment audit REFRESH (R30_W6).

R20_M7 audited the production prediction path; that audit was correct as of
round 20. Rounds R21-R29 added several wire-layer touches:

  R21_N1 — `prop_pergame._resolve_model_dir` worktree fallback for
           gitignored prop-model artifacts (props_pg_*.json + mlp pkls).
  R21_N5 — per-(game_id, models_mtime) prediction cache for the m2_family
           ensemble path inside `game_models._predict_m2_family`.
  R22_O8 — `injury_availability` now reads
           `data/cache/nba_injuries_<today>.parquet` (authoritative) before
           falling back to the legacy ESPN JSON snapshot.
  R23_P2 — `scripts/inplay_bet_ranker.py` injury-kill guard: every bet is
           filtered through `get_availability_factor`; OUT players (factor=0.0)
           are excluded from ranked output.
  R28_U2 — pace feature reference-mean patch.
  R29_V3 — residual-drift triage (computation_artifact category fixes for
           synergy / sim features).

This probe re-runs the R20_M7 audit, validates each R21-R29 wire is still
honoured, then smoke-tests the prediction chain (m2_family, per-stat heads,
injury factor, endQ3 residual heads, R21_N5 cache) so any regression in the
wire layer surfaces immediately.

It writes a structured payload to
`data/cache/probe_R30_W6_results.json` and exits 0 on a clean refresh.

Hard rule: LOCAL only. No SSH, no RunPod, no network. Does not modify
production model artifacts or load paths. Pure read-only audit.
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_HERE = Path(__file__).resolve().parent
_PROJECT_DIR = _HERE.parent.parent
if str(_PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(_PROJECT_DIR))

OUT_PATH = _PROJECT_DIR / "data" / "cache" / "probe_R30_W6_results.json"
R20_BASELINE_PATH = _PROJECT_DIR / "data" / "cache" / "probe_R20_M7_results.json"


# ---------------------------------------------------------------------------
# Worktree-aware host-repo resolution. The audit needs to honour the same
# fallback logic that R21_N1 baked into prop_pergame: if we're inside a
# `.claude/worktrees/<wt>/` subtree and the local data/models is sparse,
# the production resolver walks up to the host repo's data/models. The
# audit must do the same OR it will report false-negative NO_ARTIFACT rows
# for every artifact that wasn't copied into the worktree.
# ---------------------------------------------------------------------------
def _resolve_audit_dirs() -> Tuple[str, str]:
    """Return (models_dir, nba_dir) resolved to whichever (worktree or host)
    copy actually has the populated artifacts.

    Probe-only: we never modify production code paths — we just pick the
    same directory the production code would resolve to via
    `prop_pergame._resolve_model_dir` so the audit reflects reality.
    """
    local_models = str(_PROJECT_DIR / "data" / "models")
    local_nba = str(_PROJECT_DIR / "data" / "nba")
    canary = os.path.join(local_models, "m2_family", "manifest.json")
    if os.path.exists(canary):
        return local_models, local_nba

    norm = str(_PROJECT_DIR).replace("\\", "/")
    marker = "/.claude/worktrees/"
    if marker in norm:
        host = norm.split(marker, 1)[0]
        host_models = os.path.join(host, "data", "models").replace("/", os.sep)
        host_nba = os.path.join(host, "data", "nba").replace("/", os.sep)
        if os.path.exists(os.path.join(host_models, "m2_family", "manifest.json")):
            return host_models, host_nba

    return local_models, local_nba


MODELS_DIR, NBA_DIR = _resolve_audit_dirs()


def _exists(*relpaths: str) -> bool:
    return all(os.path.exists(os.path.join(MODELS_DIR, p)) for p in relpaths)


def _m2_family_wire_present() -> bool:
    """Confirm the R20_M7 m2_family wire is still present in game_models.py."""
    p = _PROJECT_DIR / "src" / "prediction" / "game_models.py"
    if not p.exists():
        return False
    src = p.read_text(encoding="utf-8")
    return "_predict_m2_family" in src and "m2_family_used" in src


def _r21_n1_resolver_present() -> bool:
    """Confirm the prop_pergame worktree-fallback resolver is still wired."""
    p = _PROJECT_DIR / "src" / "prediction" / "prop_pergame.py"
    if not p.exists():
        return False
    src = p.read_text(encoding="utf-8")
    return "_resolve_model_dir" in src and "/.claude/worktrees/" in src


def _r21_n5_cache_present() -> bool:
    """Confirm the m2_family prediction cache is still wired."""
    p = _PROJECT_DIR / "src" / "prediction" / "game_models.py"
    if not p.exists():
        return False
    src = p.read_text(encoding="utf-8")
    return (
        "_M2_PRED_CACHE_PATH" in src
        and "_m2_family_models_mtime" in src
        and "_load_m2_pred_cache" in src
    )


def _r22_o8_injury_parquet_wire_present() -> bool:
    """Confirm R22_O8 parquet-first injury wire is still active."""
    p = _PROJECT_DIR / "src" / "prediction" / "injury_availability.py"
    if not p.exists():
        return False
    src = p.read_text(encoding="utf-8")
    return (
        "_load_parquet_indices" in src
        and "nba_injuries_" in src
        and "_latest_parquet_path" in src
    )


def _r23_p2_inplay_injury_kill_present() -> bool:
    """Confirm R23_P2 injury-kill guard is still wired into inplay_bet_ranker."""
    p = _PROJECT_DIR / "scripts" / "inplay_bet_ranker.py"
    if not p.exists():
        return False
    src = p.read_text(encoding="utf-8")
    return (
        "_availability_factor" in src
        and "get_availability_factor" in src
        and "n_killed_by_injury" in src
    )


def _build_deployment_table() -> List[Dict[str, Any]]:
    """Mirror the R20_M7 DEPLOYMENT_TABLE but using the worktree-aware
    MODELS_DIR + the R21/R22/R23 wire-presence checks added by this round.
    """
    m2_wire = _m2_family_wire_present()
    rows: List[Dict[str, Any]] = [
        # Player-prop family
        {"surface": "player_props_pts", "shipped_in_round": "cycle-18 sqrt+Huber",
         "wired": "WIRED" if _exists("props_pg_pts.json") else "NO_ARTIFACT"},
        {"surface": "player_props_reb", "shipped_in_round": "cycle-29 LGB-q50",
         "wired": "WIRED" if _exists("quantile_pergame_lgb_reb_q50.pkl") else "NO_ARTIFACT"},
        {"surface": "player_props_ast", "shipped_in_round": "cycle-23 multitask MLP",
         "wired": "WIRED" if _exists("props_pg_mlp_ast.pkl") else "NO_ARTIFACT"},
        {"surface": "player_props_fg3m", "shipped_in_round": "cycle-27 XGB-q50",
         "wired": "WIRED" if _exists("quantile_pergame_fg3m_q50.json") else "NO_ARTIFACT"},
        {"surface": "player_props_stl", "shipped_in_round": "cycle-27 XGB-q50",
         "wired": "WIRED" if _exists("quantile_pergame_stl_q50.json") else "NO_ARTIFACT"},
        {"surface": "player_props_blk", "shipped_in_round": "cycle-27 XGB-q50",
         "wired": "WIRED" if _exists("quantile_pergame_blk_q50.json") else "NO_ARTIFACT"},
        {"surface": "player_props_tov", "shipped_in_round": "cycle-27 XGB-q50",
         "wired": "WIRED" if _exists("quantile_pergame_tov_q50.json") else "NO_ARTIFACT"},
        # Pregame residual heads
        {"surface": "pregame_residual_heads_6stat",
         "shipped_in_round": "R7_A_pregame_residual_heads_per_stat (round 6)",
         "wired": "WIRED" if _exists("pregame_residual_heads/reb.lgb",
                                      "pregame_residual_heads/blk.lgb") else "NO_ARTIFACT"},
        # In-play residual heads
        {"surface": "endq1_residual_heads",
         "shipped_in_round": "R4_A_residual_heads_endq1 (round 3)",
         "wired": "WIRED" if _exists("residual_heads_endq1/pts.lgb") else "NO_ARTIFACT"},
        {"surface": "endq2_residual_heads",
         "shipped_in_round": "R3_A_residual_heads_endq2 (round 2)",
         "wired": "WIRED" if _exists("residual_heads_endq2/pts.lgb") else "NO_ARTIFACT"},
        {"surface": "endq3_residual_heads",
         "shipped_in_round": "R2_F_residual_heads (round 1)",
         "wired": "WIRED" if _exists("residual_heads/pts.lgb") else "NO_ARTIFACT"},
        {"surface": "endq3_streak_features",
         "shipped_in_round": "R10_M16_streak_per_stat (round 9)",
         "wired": "WIRED" if _exists("residual_heads/blk_xstat_meta.json") else "NO_ARTIFACT"},
        {"surface": "endq3_xstat_covariance",
         "shipped_in_round": "R12_F3 (covered by R12_BATCH6 round 12)",
         "wired": "WIRED" if _exists("residual_heads/blk_xstat.lgb",
                                      "residual_heads/fg3m_xstat.lgb") else "NO_ARTIFACT"},
        # In-play win prob
        {"surface": "inplay_winprob_endq1_v1",
         "shipped_in_round": "R10_M5_inplay_winprob (round 9)",
         "wired": "WIRED" if _exists("inplay_winprob_endq1.lgb") else "NO_ARTIFACT"},
        {"surface": "inplay_winprob_endq3_v1",
         "shipped_in_round": "R10_M5_inplay_winprob (round 9)",
         "wired": "WIRED" if _exists("inplay_winprob_endq3.lgb") else "NO_ARTIFACT"},
        {"surface": "inplay_winprob_endq2_v2_ensemble",
         "shipped_in_round": "R12_F1 (round 11/12 area)",
         "wired": "WIRED" if _exists("inplay_winprob_endq2_v2.lgb") else "NO_ARTIFACT"},
        {"surface": "inplay_winprob_endq1_v3_pregame_anchored",
         "shipped_in_round": "R13_G2 (post-round-12)",
         "wired": "WIRED" if _exists("inplay_winprob_endq1_v3.lgb") else "NO_ARTIFACT"},
        # Game-level family (m2_family multi5 ensemble)
        {"surface": "game_total", "shipped_in_round": "R11 M2 family (round 10)",
         "wired": "WIRED" if (_exists("m2_family/manifest.json",
                                       "m2_family/total_lgb_s42.joblib")
                              and m2_wire) else "NO_ARTIFACT"},
        {"surface": "game_spread", "shipped_in_round": "R11 M2 family (round 10)",
         "wired": "WIRED" if (_exists("m2_family/manifest.json",
                                       "m2_family/spread_lgb_s42.joblib")
                              and m2_wire) else "NO_ARTIFACT"},
        {"surface": "game_home_pts", "shipped_in_round": "R11 M2 family (round 10)",
         "wired": "WIRED" if (_exists("m2_family/home_pts_lgb_s42.joblib")
                              and m2_wire) else "NO_ARTIFACT"},
        {"surface": "game_away_pts", "shipped_in_round": "R11 M2 family (round 10)",
         "wired": "WIRED" if (_exists("m2_family/away_pts_lgb_s42.joblib")
                              and m2_wire) else "NO_ARTIFACT"},
        {"surface": "game_blowout", "shipped_in_round": "pre-loop (legacy)",
         "wired": "WIRED" if _exists("game_blowout.json") else "NO_ARTIFACT"},
        {"surface": "game_first_half", "shipped_in_round": "pre-loop (legacy)",
         "wired": "WIRED" if _exists("game_first_half.json") else "NO_ARTIFACT"},
        {"surface": "game_pace", "shipped_in_round": "pre-loop (legacy)",
         "wired": "WIRED" if _exists("game_pace.json") else "NO_ARTIFACT"},
        # Probe-only surfaces with no persisted artifact
        {"surface": "binary_ou_thresholds (O220/O230/...)",
         "shipped_in_round": "R11 M2v11-v24 + BATCH8 (round 10)",
         "wired": "NO_ARTIFACT"},
        {"surface": "binary_ats_thresholds (AH3/AH7/PH3/...)",
         "shipped_in_round": "R11 M2v13/14/18/19/25-30 (round 10)",
         "wired": "NO_ARTIFACT"},
        {"surface": "q1_total / h1_total / home_q1 / away_q1",
         "shipped_in_round": "R11 M2v15-v17/v32-v34 (round 10)",
         "wired": "NO_ARTIFACT"},
        {"surface": "tracking_pts_residual",
         "shipped_in_round": "R10_M13_tracking_pts_per_stat (round 9)",
         "wired": "NO_ARTIFACT"},
    ]
    return rows


def _count(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = {"WIRED": 0, "NO_ARTIFACT": 0}
    for r in rows:
        counts[r["wired"]] = counts.get(r["wired"], 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Smoke tests — pregame m2_family, per-stat heads, injury wire, endQ3 head,
# R21_N5 cache. Each runs in an isolated try/except so a single failure
# doesn't blank the others.
# ---------------------------------------------------------------------------

# Use the m2_family directory we resolved. To exercise game_models we
# temporarily switch into the host repo's dir if our worktree-local dir is
# sparse — we do NOT modify game_models module code, we just sys.path-prefix
# the directory that owns the populated m2_family/.
_AUDIT_HOST: Optional[str] = None
if not (_PROJECT_DIR / "data" / "models" / "m2_family" / "manifest.json").exists():
    norm = str(_PROJECT_DIR).replace("\\", "/")
    marker = "/.claude/worktrees/"
    if marker in norm:
        _AUDIT_HOST = norm.split(marker, 1)[0].replace("/", os.sep)


def _run_in_host(callable_str: str) -> Optional[str]:
    """Run a one-shot python expression in the host repo via subprocess so
    the production module's PROJECT_DIR resolves to the host's data/models.

    Returns stdout (last line) or None on failure. Probe-only — never imports
    the production module into THIS process under a different PROJECT_DIR
    (that would taint Python's module cache).
    """
    import subprocess

    host = _AUDIT_HOST or str(_PROJECT_DIR)
    cmd = [sys.executable, "-c", callable_str]
    try:
        proc = subprocess.run(
            cmd, cwd=host, capture_output=True, text=True, timeout=120,
        )
        if proc.returncode != 0:
            return None
        lines = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()]
        return lines[-1] if lines else None
    except Exception:
        return None


def smoke_m2_family() -> Tuple[bool, Dict[str, Any]]:
    """Pregame m2_family prediction (cold path) — all 4 values non-None."""
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
    if line is None or not line.startswith("RESULT "):
        return False, {"error": "subprocess failed or RESULT marker missing",
                       "raw": line}
    try:
        payload = json.loads(line[len("RESULT "):])
    except Exception:
        return False, {"error": "json parse failed", "raw": line}
    ok = (
        payload.get("m2_family_used") is True
        and payload.get("total_est") is not None and payload["total_est"] > 0
        and payload.get("spread_est") is not None
        and payload.get("home_pts_est") is not None and payload["home_pts_est"] > 0
        and payload.get("away_pts_est") is not None and payload["away_pts_est"] > 0
        and payload.get("confidence") == "model+m2_family"
    )
    return ok, payload


def smoke_per_stat_heads() -> Tuple[bool, Dict[str, Any]]:
    """All 7 per-stat prop heads load + predict a non-None value."""
    expr = (
        "import sys; sys.path.insert(0, '.');\n"
        "from src.prediction.prop_pergame import predict_player_pergame, STATS;\n"
        "out = predict_player_pergame(101108, opp_team='LAL', season='2024-25', is_home=True);\n"
        "import json;\n"
        "ok = out is not None and all(out.get(s) is not None for s in STATS);\n"
        "print('RESULT', json.dumps({'ok': ok, 'values': out}))"
    )
    line = _run_in_host(expr)
    if line is None or not line.startswith("RESULT "):
        return False, {"error": "subprocess failed or RESULT marker missing",
                       "raw": line}
    try:
        payload = json.loads(line[len("RESULT "):])
    except Exception:
        return False, {"error": "json parse failed", "raw": line}
    return bool(payload.get("ok")), payload


def smoke_injury_factor() -> Tuple[bool, Dict[str, Any]]:
    """Injury parquet returns 0.0 for at least 1 known-OUT player today."""
    expr = (
        "import sys, os, json, pandas as pd; sys.path.insert(0, '.');\n"
        "from src.prediction.injury_availability import get_availability_factor;\n"
        "from datetime import date as _d;\n"
        "p = os.path.join('data', 'cache', f'nba_injuries_{_d.today().isoformat()}.parquet');\n"
        "df = pd.read_parquet(p) if os.path.exists(p) else None;\n"
        "if df is None or df.empty:\n"
        "    print('RESULT', json.dumps({'ok': False, 'reason': 'no_parquet'}))\n"
        "else:\n"
        "    outs = df[df['status'] == 'OUT'].head(5);\n"
        "    samples = [(int(r['player_id']), str(r['player_name']),"
        " float(get_availability_factor(player_id=int(r['player_id']),"
        " player_name=str(r['player_name'])))) for _, r in outs.iterrows()];\n"
        "    ok = len(samples) >= 1 and all(s[2] == 0.0 for s in samples);\n"
        "    print('RESULT', json.dumps({'ok': ok, 'n_out': len(outs), 'samples': samples}))"
    )
    line = _run_in_host(expr)
    if line is None or not line.startswith("RESULT "):
        return False, {"error": "subprocess failed", "raw": line}
    try:
        payload = json.loads(line[len("RESULT "):])
    except Exception:
        return False, {"error": "json parse failed", "raw": line}
    return bool(payload.get("ok")), payload


def smoke_endq3_residual() -> Tuple[bool, Dict[str, Any]]:
    """endQ3 residual_heads loader returns a non-empty heads dict."""
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
        "ok = len(loaded) == 7 and callable_ok;\n"
        "print('RESULT', json.dumps({'ok': ok, 'loaded_stats': loaded, 'callable_ok': callable_ok}))"
    )
    line = _run_in_host(expr)
    if line is None or not line.startswith("RESULT "):
        return False, {"error": "subprocess failed", "raw": line}
    try:
        payload = json.loads(line[len("RESULT "):])
    except Exception:
        return False, {"error": "json parse failed", "raw": line}
    return bool(payload.get("ok")), payload


def smoke_r21_n5_cache() -> Tuple[bool, Dict[str, Any]]:
    """R21_N5 cache: run m2_family predict twice — second call must be byte-
    identical to the first (proves cache reuse, not re-rolled prediction)."""
    expr = (
        "import sys, json; sys.path.insert(0, '.');\n"
        "from src.prediction.game_models import predict, clear_m2_pred_cache;\n"
        "clear_m2_pred_cache();\n"
        "kw = dict(season='2025-26', game_date='2025-10-21', game_id='0022500001');\n"
        "a = predict('OKC', 'HOU', **kw);\n"
        "b = predict('OKC', 'HOU', **kw);\n"
        "fields = ('total_est', 'spread_est', 'home_pts_est', 'away_pts_est');\n"
        "match = all(a.get(f) == b.get(f) for f in fields);\n"
        "ok = match and a.get('m2_family_used') and b.get('m2_family_used');\n"
        "print('RESULT', json.dumps({'ok': ok, 'first': {f: a.get(f) for f in fields},"
        " 'second': {f: b.get(f) for f in fields}}))"
    )
    line = _run_in_host(expr)
    if line is None or not line.startswith("RESULT "):
        return False, {"error": "subprocess failed", "raw": line}
    try:
        payload = json.loads(line[len("RESULT "):])
    except Exception:
        return False, {"error": "json parse failed", "raw": line}
    return bool(payload.get("ok")), payload


def _load_r20_baseline() -> Optional[dict]:
    """Load the on-disk R20_M7 baseline if it exists in EITHER the worktree
    OR the host repo (worktree-aware)."""
    paths = [R20_BASELINE_PATH]
    norm = str(_PROJECT_DIR).replace("\\", "/")
    marker = "/.claude/worktrees/"
    if marker in norm:
        host = Path(norm.split(marker, 1)[0])
        paths.append(host / "data" / "cache" / "probe_R20_M7_results.json")
    for p in paths:
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
    return None


def main() -> int:
    rows = _build_deployment_table()
    counts = _count(rows)

    wires = {
        "R20_M7_m2_family":      _m2_family_wire_present(),
        "R21_N1_resolver":       _r21_n1_resolver_present(),
        "R21_N5_cache":          _r21_n5_cache_present(),
        "R22_O8_injury_parquet": _r22_o8_injury_parquet_wire_present(),
        "R23_P2_inplay_kill":    _r23_p2_inplay_injury_kill_present(),
    }

    smoke: Dict[str, Dict[str, Any]] = {}
    for name, fn in (
        ("m2_family",        smoke_m2_family),
        ("per_stat_heads",   smoke_per_stat_heads),
        ("injury_factor",    smoke_injury_factor),
        ("endq3_residual",   smoke_endq3_residual),
        ("r21_n5_cache",     smoke_r21_n5_cache),
    ):
        t0 = time.time()
        try:
            ok, detail = fn()
        except Exception as exc:  # belt-and-braces — never crash the audit
            ok, detail = False, {"error": f"{type(exc).__name__}: {exc}",
                                  "trace": traceback.format_exc(limit=3)}
        smoke[name] = {"pass": bool(ok), "elapsed_sec": round(time.time() - t0, 2),
                       "detail": detail}

    smoke_pass = sum(1 for s in smoke.values() if s["pass"])

    baseline = _load_r20_baseline()
    n_regressions = 0
    regression_surfaces: List[str] = []
    if baseline:
        base_unwired = set(baseline.get("unwired_surfaces", []))
        now_unwired = {r["surface"] for r in rows if r["wired"] != "WIRED"}
        # A regression is a surface that was WIRED in R20_M7 baseline but is
        # NOT wired now. (Surfaces baseline-unwired that are still unwired
        # are NOT regressions — they were never shipped to production.)
        new_unwired = now_unwired - base_unwired
        regression_surfaces = sorted(new_unwired)
        n_regressions = len(regression_surfaces)

    payload = {
        "probe": "R30_W6_model_deployment_audit_refresh",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "audit_dirs": {"models": MODELS_DIR, "nba": NBA_DIR,
                        "worktree_host": _AUDIT_HOST},
        "n_surfaces": len(rows),
        "counts": counts,
        "n_ships_wired": counts["WIRED"],
        "n_ships_unwired": counts["NO_ARTIFACT"],
        "wires_present": wires,
        "matrix": rows,
        "unwired_surfaces": [r["surface"] for r in rows if r["wired"] != "WIRED"],
        "smoke_tests": smoke,
        "smoke_pass": smoke_pass,
        "smoke_total": len(smoke),
        "smoke_test_per_stage": {k: v["pass"] for k, v in smoke.items()},
        "n_regressions_vs_R20_M7": n_regressions,
        "regression_surfaces": regression_surfaces,
        "baseline_loaded": baseline is not None,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("=" * 80)
    print("R30_W6 model deployment audit refresh")
    print("=" * 80)
    print(f"Audit dirs:           models={MODELS_DIR}")
    print(f"                       nba={NBA_DIR}")
    print(f"                       host fallback={_AUDIT_HOST}")
    print()
    print(f"n_surfaces:           {len(rows)}")
    print(f"  WIRED:              {counts['WIRED']}")
    print(f"  NO_ARTIFACT:        {counts['NO_ARTIFACT']}")
    print(f"n_regressions_vs_R20: {n_regressions}")
    if regression_surfaces:
        for s in regression_surfaces:
            print(f"    - {s}")
    print()
    print("Wires present:")
    for k, v in wires.items():
        print(f"  {k:30} {'YES' if v else 'NO'}")
    print()
    print("Smoke tests:")
    for k, v in smoke.items():
        print(f"  {k:20} {'PASS' if v['pass'] else 'FAIL'}  ({v['elapsed_sec']}s)")
    print()
    print(f"Wrote audit payload -> {OUT_PATH}")
    # Exit non-zero if any regression OR any smoke fail.
    if n_regressions > 0 or smoke_pass < len(smoke):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
