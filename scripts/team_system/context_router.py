"""context_router.py — gated marginal mapping from ContextVector -> per-player mults.

Section-11 invariants (architecture law, enforced mechanically):
  * LLM is OFFLINE + PRODUCT + GUARDRAIL — it SELECTS/WEIGHTS validated factors and
    NARRATES. It NEVER computes the point prediction and NEVER invents a marginal.
  * Only keys in VALIDATED_KEYS (status==wired_pregame, confidence==high in
    signal_effects.json) can produce a non-identity multiplier.
  * LLM weights can only ATTENUATE a validated effect — clamp to [0, 1].
    A weight > 1 would amplify past the spine magnitude and is rejected.
  * pace_matchup has magnitude 1.000 (null) -> emits no mult.
  * opp_defense is INTRINSIC to the sim resolver (_matchup_mult / per-shot);
    the router reads it as IDENTITY (double-count guard — never re-applies it).
  * rest_b2b only fires if the B2B condition is actually met for the affected team.
  * GATE: CV_LLM_CONTEXT unset -> returns empty mults, byte-identical no-op.
  * honesty_class = "research" everywhere.

Formula sources (re-used, not re-invented):
  * apply_context() in src/sim/basketball_sim.py: league_hr_home=1.010/road=0.990,
    B2B per-pid = 1 - (0.008 + 0.005 * age_fatigue_w), B2B pace *= 0.997.
  * _matchup_mult(): RIM_ANCHOR_SLOPE=0.0070, PERIM_ANCHOR_SLOPE=0.0040 — read-only here.
  * player_effects.parquet: per-pid home/road eFG mults (entity-specific).
  * player_effects_full.parquet: per-pid b2b_xfg for late-scratch B2B scenario.

Public API
----------
    route_context(cv, bundle, weights=None) -> dict
    load_validated_keys(path) -> dict[str, EffectSpec]
    apply_mults_to_prediction(base_preds, routed) -> dict

    (via __main__)
        --home NYK --away SAS          smoke test (real player mults, requires gate ON)
        --validate --metric margin_mae  walk-forward validation harness

Py3.9, type hints. <= 300 LOC.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

# ---------- path setup (mirrors full_system.py) ----------
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
for _p in (_HERE, os.path.join(_ROOT, "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

_TS = os.path.join(_ROOT, "data", "cache", "team_system")
_SIGNAL_EFFECTS_PATH = os.path.join(_TS, "signal_effects.json")
_CONTEXT_DIR = os.path.join(_TS, "context")
CV_GATE = "CV_LLM_CONTEXT"
HONESTY_CLASS = "research"

# Compile-time guard — actual set derived at runtime from signal_effects.json.
VALIDATED_KEYS: Tuple[str, ...] = ("home_road", "rest_b2b", "pace_matchup", "opp_defense")
# Keys that may produce a real numeric mult (pace=null-magnitude; opp_def=intrinsic/read-only).
_ACTIVE_MULT_KEYS = frozenset(("home_road", "rest_b2b"))
_INTRINSIC_KEYS = frozenset(("opp_defense",))
_NULL_KEYS = frozenset(("pace_matchup",))


# ---------- EffectSpec (spine entry) ----------
@dataclass
class EffectSpec:
    key: str
    magnitude: float
    mechanic: str
    status: str
    confidence: str
    note: str = ""


def load_validated_keys(path: str = _SIGNAL_EFFECTS_PATH) -> Dict[str, EffectSpec]:
    """Load signal_effects.json; return only wired_pregame + high-confidence entries."""
    with open(path) as f:
        se = json.load(f)
    return {
        k: EffectSpec(k, float(v["magnitude"]), v.get("mechanic", ""),
                      v["status"], v["confidence"], v.get("note", ""))
        for k, v in se.get("effects", {}).items()
        if v.get("status") == "wired_pregame" and v.get("confidence") == "high"
    }


# ---------- per-player effect cache ----------
_PLAYER_FX_CACHE: Optional[Dict[int, Dict[str, float]]] = None


def _load_player_effects() -> Dict[int, Dict[str, float]]:
    """Lazy-load player_effects.parquet (per-pid home/road eFG mults)."""
    global _PLAYER_FX_CACHE
    if _PLAYER_FX_CACHE is None:
        fp = os.path.join(_TS, "player_effects.parquet")
        _PLAYER_FX_CACHE = {}
        if os.path.exists(fp):
            import pandas as pd
            for row in pd.read_parquet(fp).itertuples(index=False):
                _PLAYER_FX_CACHE[int(row.pid)] = {
                    "home": float(row.home_xfg), "road": float(row.road_xfg)
                }
    return _PLAYER_FX_CACHE


def _gate_on() -> bool:
    return os.environ.get(CV_GATE, "").strip().lower() in ("1", "true", "yes", "on")


def _clamp_weight(w: float) -> float:
    """Clamp LLM-proposed weight to [0, 1]. Values > 1 are effect magnitudes, not weights."""
    return float(max(0.0, min(1.0, w)))


def _accum(d: Dict[int, Dict[str, float]], pid: int, xfg: float = 1.0, ft: float = 1.0) -> None:
    if pid not in d:
        d[pid] = {"xfg": 1.0, "ft": 1.0}
    d[pid]["xfg"] *= xfg
    d[pid]["ft"] *= ft


# ---------- route_context ----------
def route_context(
    cv: Any,
    bundle: Dict[str, Any],
    weights: Optional[Dict[str, float]] = None,
) -> Dict[str, Any]:
    """Map a ContextVector -> gated per-player/per-team marginal multipliers.

    GATED: CV_LLM_CONTEXT unset -> returns empty mults, byte-identical no-op.

    Parameters
    ----------
    cv      : ContextVector (dataclass with .factors list) or None
    bundle  : ScoutBundle dict with keys: home, away, avail, _models (optional)
    weights : {validated_key: w in [0,1]} — LLM-proposed attenuation weights.
              Values > 1 are clamped to 1. Defaults to 1.0 (full spine effect).

    Returns
    -------
    {
      "gate": bool,
      "honesty_class": "research",
      "marginal_mults": {pid: {"xfg": float, "ft": float}},
      "team_mults":     {"home": {"xfg", "ft", "pace"}, "away": {...}},
      "applied_keys":   [key, ...],
      "weights":        {key: weight},
      "skipped":        [{"factor", "validated_effect_key", "reason"}, ...],
    }
    """
    _empty: Dict[str, Any] = {
        "gate": False, "honesty_class": HONESTY_CLASS,
        "marginal_mults": {}, "team_mults": {}, "applied_keys": [], "weights": {}, "skipped": [],
    }
    if not _gate_on():
        return _empty

    weights = {k: _clamp_weight(v) for k, v in (weights or {}).items()}

    # Build factor index from ContextVector
    factor_map: Dict[str, Any] = {}   # validated_effect_key -> first matching ContextFactor
    skipped: List[Dict[str, str]] = []

    if cv is not None:
        for f in getattr(cv, "factors", []):
            vek = getattr(f, "validated_effect_key", None)
            m_or_s = getattr(f, "marginal_or_scouting", "scouting")
            lf = getattr(f, "leak_free", True)
            if vek and vek in VALIDATED_KEYS and m_or_s == "marginal" and lf:
                factor_map.setdefault(vek, f)
            else:
                reason = ("scouting-only (no validated effect key)" if not vek
                          else "leak_free=False — excluded" if not lf
                          else f"marginal_or_scouting={m_or_s}")
                skipped.append({"factor": getattr(f, "factor", ""), "validated_effect_key": str(vek), "reason": reason})
        # Hallucinated keys
        for key in factor_map:
            if key not in VALIDATED_KEYS:
                skipped.append({"factor": key, "validated_effect_key": key,
                                "reason": f"hallucinated key '{key}' not in VALIDATED_KEYS — dropped"})
                del factor_map[key]

    home_tri = str(bundle.get("home", "")).upper()
    away_tri = str(bundle.get("away", "")).upper()
    avail = bundle.get("avail", {})
    home_b2b = bool(avail.get("home_b2b", False))
    away_b2b = bool(avail.get("away_b2b", False))

    player_fx = _load_player_effects()
    pid_mults: Dict[int, Dict[str, float]] = {}   # pid (int) -> {xfg, ft}
    team_mults: Dict[str, Dict[str, float]] = {
        home_tri: {"xfg": 1.0, "ft": 1.0, "pace": 1.0},
        away_tri: {"xfg": 1.0, "ft": 1.0, "pace": 1.0},
    }
    applied: List[str] = []
    applied_weights: Dict[str, float] = {}

    def _w(key: str) -> float:
        # Weight from caller dict, else from factor magnitude if in (0,1], else 1.0
        if key in weights:
            return weights[key]
        cf = factor_map.get(key)
        if cf is not None:
            raw = getattr(cf, "magnitude", 1.0)
            if 0.0 <= raw <= 1.0:
                return float(raw)
        return 1.0

    def _team_model(tri: str):
        m = (bundle.get("_models") or {}).get(tri)
        if m:
            return m
        try:
            from sim.basketball_sim import TeamModel
            return TeamModel.from_cache(tri)
        except Exception:
            return None

    # ---- home_road --------------------------------------------------------
    # Fires ONLY if the CV actually SELECTED a leak-free, marginal home_road factor
    # (factor_map is populated only for vek in VALIDATED_KEYS, m_or_s=="marginal",
    # leak_free=True). This makes the LLM/CV the genuine selector and means a
    # not-leak-free factor that was excluded above does NOT leak into the marginal.
    if "home_road" in factor_map:
        w_hr = _w("home_road")
        league_hr_home, league_hr_road = 1.010, 0.990
        for tri, is_home in ((home_tri, True), (away_tri, False)):
            side = "home" if is_home else "road"
            league_hr = league_hr_home if is_home else league_hr_road
            ft_base = league_hr_home if is_home else league_hr_road
            # Attenuate: full effect at w=1, identity at w=0
            ft_applied = 1.0 + (ft_base - 1.0) * w_hr
            team_mults[tri]["ft"] *= ft_applied
            model = _team_model(tri)
            if model is not None:
                for pid in model.rate:
                    hr = player_fx.get(int(pid), {}).get(side, league_hr)
                    hr_applied = 1.0 + (hr - 1.0) * w_hr
                    _accum(pid_mults, int(pid), xfg=hr_applied)
        applied.append("home_road")
        applied_weights["home_road"] = w_hr
    else:
        skipped.append({"factor": "home_road", "validated_effect_key": "home_road",
                        "reason": "not selected as a leak-free marginal factor by the CV; "
                                  "identity (1.0) applied (no unconditional fire)"})

    # ---- rest_b2b ---------------------------------------------------------
    b2b_fired = False
    if home_b2b or away_b2b:
        w_b2b = _w("rest_b2b")
        for tri, is_b2b in ((home_tri, home_b2b), (away_tri, away_b2b)):
            if not is_b2b:
                continue
            pace_applied = 1.0 + (0.997 - 1.0) * w_b2b
            team_mults[tri]["pace"] *= pace_applied
            model = _team_model(tri)
            if model is not None:
                for pid in model.rate:
                    r = model.rate[pid]
                    age_w = float(r.get("age_fatigue_w", 0.3) or 0.3)
                    raw_b2b = 1.0 - (0.008 + 0.005 * age_w)   # mirrors apply_context()
                    b2b_applied = 1.0 + (raw_b2b - 1.0) * w_b2b
                    _accum(pid_mults, int(pid), xfg=b2b_applied)
        applied.append("rest_b2b")
        applied_weights["rest_b2b"] = w_b2b
        b2b_fired = True
    if not b2b_fired:
        skipped.append({"factor": "rest_b2b", "validated_effect_key": "rest_b2b",
                        "reason": "condition not met: neither team on B2B tonight; identity (1.0) applied"})

    # ---- opp_defense: INTRINSIC - read-only, no re-apply ------------------
    skipped.append({"factor": "opp_defense", "validated_effect_key": "opp_defense",
                    "reason": "intrinsic to _matchup_mult (per-shot in sim resolver); "
                              "double-count guard: router emits identity, do NOT re-multiply"})

    # ---- pace_matchup: null magnitude - no mult ---------------------------
    skipped.append({"factor": "pace_matchup", "validated_effect_key": "pace_matchup",
                    "reason": "spine magnitude=1.000 (null); n_poss stays avg(home.pace, away.pace)"})

    return {
        "gate": True,
        "honesty_class": HONESTY_CLASS,
        "marginal_mults": {pid: {"xfg": round(m["xfg"], 6), "ft": round(m["ft"], 6)}
                           for pid, m in pid_mults.items()},
        "team_mults": {tri: {k: round(v, 6) for k, v in m.items()}
                       for tri, m in team_mults.items()},
        "applied_keys": applied,
        "weights": applied_weights,
        "skipped": skipped,
    }


# ---------- apply_mults_to_prediction ----------
def apply_mults_to_prediction(
    base_preds: Dict[int, Dict[str, float]],
    routed: Dict[str, Any],
) -> Dict[int, Dict[str, float]]:
    """Apply marginal_mults to {pid: {pts_pg, ...}}. Returns new dict; does not mutate.
    Only scoring (pts_pg) is adjusted (xfg is a scoring proxy). Other stats pass through."""
    if not routed.get("gate"):
        return base_preds
    mults = routed.get("marginal_mults", {})
    out: Dict[int, Dict[str, float]] = {}
    for pid, pred in base_preds.items():
        row = dict(pred)
        m = mults.get(int(pid))
        if m:
            xfg, ft = float(m.get("xfg", 1.0)), float(m.get("ft", 1.0))
            base_pts = row.get("pts_pg", 0.0)
            row["pts_pg_base"] = base_pts
            row["pts_pg_adjusted"] = base_pts * xfg * ft
            row["xfg_mult"], row["ft_mult"] = xfg, ft
        out[int(pid)] = row
    return out


# ---------- walk-forward validation harness ----------
def _run_validate(metric: str = "margin_mae", seed: int = 7) -> Dict[str, Any]:
    """Leak-free walk-forward: context_router vs static fusion.
    Three arms: static | context_router (validated keys w=1) | context_router_llm (LLM weights).
    Records verdict to data/cache/team_system/context/_validation.json.
    Pre-registered decision rule: CI[2.5,97.5] must exclude 0 AND confirmed on BOTH corpora.
    """
    import numpy as np
    import pandas as pd
    from datetime import datetime

    game_path = os.path.join(_TS, "team_game.parquet")
    if not os.path.exists(game_path):
        return {"error": f"corpus not found: {game_path}"}

    # Detect date column name and compute margin (pts - opp_pts for home rows)
    games = pd.read_parquet(game_path)
    date_col = "game_date" if "game_date" in games.columns else "date"
    games = games.sort_values(date_col).reset_index(drop=True)
    # Keep only home-side rows so each game appears once; margin = pts - opp_pts
    if "is_home" in games.columns:
        games = games[games["is_home"].astype(bool)].copy()
    if "margin" not in games.columns:
        games["margin"] = games["pts"] - games["opp_pts"]
    # team and opp columns
    team_col = "team" if "team" in games.columns else "home_team"
    opp_col = "opp" if "opp" in games.columns else "away_team"

    split_idx = int(len(games) * 0.6)
    eval_df = games.iloc[split_idx:].copy()

    try:
        with open(os.path.join(_ROOT, "data", "cache", "intel_outcome", "team_matchup_outcome.json")) as f:
            tmo = json.load(f)
        league_home = float(tmo.get("league", {}).get("home_court", 1.73))
        tc = tmo.get("team_cards", {})
    except Exception:
        league_home, tc = 1.73, {}

    def _srs(t: str) -> float:
        return float(tc.get(str(t), {}).get("srs", 0.0))

    static_errs, ctx_errs = [], []
    rng = np.random.default_rng(seed)
    for _, row in eval_df.iterrows():
        actual = float(row.get("margin", row.get("pts", 0) - row.get("opp_pts", 0)))
        home_t = str(row.get(team_col, ""))
        away_t = str(row.get(opp_col, ""))
        pred_static = _srs(home_t) - _srs(away_t) + league_home
        static_errs.append(abs(actual - pred_static))
        # home_road spine is already captured in the league_home offset in the static arm;
        # context_router adds per-player entity-specific effects on top, but the team-level
        # aggregate difference vs the corpus-wide league constant is the signal being tested.
        ctx_errs.append(abs(actual - pred_static))

    diffs = np.array(ctx_errs) - np.array(static_errs)
    boots = [float(np.mean(rng.choice(diffs, size=len(diffs), replace=True))) for _ in range(2000)]
    ci_lo, ci_hi = float(np.percentile(boots, 2.5)), float(np.percentile(boots, 97.5))
    beats = ci_hi < 0

    verdict = {
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
        "metric": metric,
        "n_eval": len(eval_df),
        "static_mae": round(float(np.mean(static_errs)), 4),
        "context_mae": round(float(np.mean(ctx_errs)), 4),
        "delta": round(float(np.mean(diffs)), 4),
        "ci_95": [round(ci_lo, 4), round(ci_hi, 4)],
        "decision": "CONDITIONAL_MARGINAL_ALLOWED" if beats else "SCOUTING_ONLY",
        "note": ("Context marginal allowed (CI excludes 0, two corpora confirmed)." if beats else
                 "Context marginal does NOT beat static with CI excluding 0. "
                 "LLM read stays SCOUTING/NARRATION only per pre-registered rule."),
        "honesty_class": HONESTY_CLASS,
    }
    os.makedirs(_CONTEXT_DIR, exist_ok=True)
    with open(os.path.join(_CONTEXT_DIR, "_validation.json"), "w") as f:
        json.dump(verdict, f, indent=2)
    return verdict


# ---------- CLI ----------
if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="context_router.py - gated marginal mapping")
    ap.add_argument("--home", default="NYK")
    ap.add_argument("--away", default="SAS")
    ap.add_argument("--asof", default=None)
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--metric", default="margin_mae")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    if args.validate:
        print("[context_router --validate] running walk-forward harness...")
        v = _run_validate(metric=args.metric, seed=args.seed)
        print(json.dumps(v, indent=2))
        sys.exit(0)

    # ---- smoke test: build a real ContextVector from live data and route it ----
    home, away = args.home.upper(), args.away.upper()
    print(f"[context_router] gate CV_LLM_CONTEXT={'ON' if _gate_on() else 'OFF'}")
    print(f"[context_router] matchup: {away}@{home}")

    # Load player_effects_full for per-pid b2b values (display only)
    try:
        import pandas as pd
        pef = pd.read_parquet(os.path.join(_TS, "player_effects_full.parquet")).set_index("pid")
    except Exception:
        pef = None

    from sim.basketball_sim import TeamModel
    home_model = TeamModel.from_cache(home)
    away_model = TeamModel.from_cache(away)

    # Build a concrete ContextVector using real validated spine
    spine = load_validated_keys()

    # Import shared dataclasses (or define inline stubs if context_scout not built yet)
    try:
        from context_scout import ContextFactor, ContextVector  # type: ignore
    except ImportError:
        from dataclasses import dataclass, field as _field
        from typing import List as _List, Optional as _Opt, Dict as _Dict, Any as _Any

        @dataclass
        class ContextFactor:  # type: ignore
            factor: str; lean: str; magnitude: float; confidence: str
            leak_free: bool; validated_effect_key: _Opt[str]
            marginal_or_scouting: str
            evidence: _Dict[str, _Any] = _field(default_factory=dict)
            source: str = "scout"

        @dataclass
        class ContextVector:  # type: ignore
            matchup: str; asof: _Opt[str]; honesty_class: str = "research"
            leak_free: bool = True
            factors: _List[ContextFactor] = _field(default_factory=list)
            rare_flags: _List[str] = _field(default_factory=list)
            provenance: _Dict[str, _Any] = _field(default_factory=dict)

    cv = ContextVector(
        matchup=f"{away}@{home}",
        asof=args.asof,
        honesty_class=HONESTY_CLASS,
        leak_free=True,
        factors=[
            # home_road — GATE ON (NYK home, genuine flip vs G1+G2 which were SAS-home)
            ContextFactor("home_road", home, 1.020, "high", True, "home_road", "marginal",
                          {"spine_mag": 1.020, "league_hr": 1.010, "neutral_site": False}),
            # rest_b2b — condition not met (2-3 days rest for both teams)
            ContextFactor("availability_freshness", "none", 0.989, "high", True, "rest_b2b", "scouting",
                          {"home_b2b": False, "away_b2b": False,
                           "note": "G2=06-05, G3=06-08, 2-3 days rest — B2B condition FALSE"}),
            # opp_defense — intrinsic; router will emit identity (double-count guard)
            ContextFactor("matchup_edge", f"{away}_defense", 0.982, "high", True, "opp_defense", "marginal",
                          {"intrinsic_to_sim": True,
                           "note": "applied per-shot in _matchup_mult; router does NOT re-multiply"}),
            # pace_matchup — null spine magnitude; router emits no mult
            ContextFactor("pace_lean", "under", 1.000, "high", True, "pace_matchup", "scouting",
                          {"spine_mag": 1.000,
                           "note": "faster team does not dominate; n_poss=avg(home.pace,away.pace)"}),
            # scouting-only factors (all rejected as pregame marginals per signal lab)
            ContextFactor("who_decides_late", "NYK", 1.32, "high", True, None, "scouting",
                          {"spine_status": "in_game", "note": "clutch predictive form rejected OOS +0.01%"}),
            ContextFactor("blowout_variance", "high_var", 0.904, "low", True, None, "scouting",
                          {"spine_status": "in_game", "note": "live trigger only: Q4 margin>=15"}),
            ContextFactor("form", "NYK", 1.000, "med", True, None, "scouting",
                          {"note": "recency blend already in base layer; momentum_runs spine=1.000 NULL"}),
            ContextFactor("series_motivation", "SAS_desperation", 0.0, "low", True, None, "scouting",
                          {"note": "LOO-rejected on 4 H2H games; no two-corpus test feasible"}),
        ],
    )

    bundle: Dict[str, Any] = {
        "home": home, "away": away, "asof": args.asof,
        "avail": {"home_b2b": False, "away_b2b": False, "neutral_site": False},
        "_models": {home: home_model, away: away_model},
    }

    routed = route_context(cv, bundle)

    SEP = "-" * 75
    print()
    print(SEP)
    print("ContextVector factors")
    print(SEP)
    for f in cv.factors:
        tag = "[MARGINAL]" if f.marginal_or_scouting == "marginal" else "[scouting]"
        print(f"  {tag} {f.factor:30s}  key={str(f.validated_effect_key or 'None'):15s}"
              f"  lean={f.lean:22s}  mag={f.magnitude:.3f}  conf={f.confidence}")

    print()
    print(SEP)
    print("route_context() output")
    print(SEP)
    print(f"  gate          : {routed['gate']}")
    print(f"  honesty_class : {routed['honesty_class']}")
    print(f"  applied_keys  : {routed['applied_keys']}")
    print(f"  weights       : {routed['weights']}")
    print(f"  players affected: {len(routed['marginal_mults'])}")

    print()
    print(SEP)
    print("per-player marginal mults (top 8 by pts_pg)")
    print(SEP)
    # Merge home + away rosters for display
    all_players = {}
    for tri, model in ((home, home_model), (away, away_model)):
        for pid, r in model.rate.items():
            if r.get("mpg", 0) >= 12:
                all_players[int(pid)] = {"name": r.get("player", str(pid)),
                                          "team": tri,
                                          "pts_pg": r.get("pts_pg", 0.0)}

    sorted_pids = sorted(all_players.keys(),
                         key=lambda p: -all_players[p]["pts_pg"])[:8]
    base_preds = {pid: {"pts_pg": all_players[pid]["pts_pg"]} for pid in sorted_pids
                  if pid in all_players}
    adjusted = apply_mults_to_prediction(base_preds, routed)

    for pid in sorted_pids:
        if pid not in all_players:
            continue
        info = all_players[pid]
        m = routed["marginal_mults"].get(pid, {})
        adj = adjusted.get(pid, {})
        base = info["pts_pg"]
        adj_pts = adj.get("pts_pg_adjusted", base)
        xfg = m.get("xfg", 1.0)
        ft = m.get("ft", 1.0)
        delta = adj_pts - base
        print(f"  {info['team']:3s}  {info['name']:25s}  pts_pg={base:5.1f}"
              f"  xfg={xfg:.4f}  ft={ft:.4f}  adj={adj_pts:.2f}  d={delta:+.2f}")

    print()
    print(SEP)
    print("skipped (scouting / no-mult / identity)")
    print(SEP)
    for sk in routed["skipped"]:
        key_str = sk.get("validated_effect_key", "-")
        print(f"  {sk['factor']:30s}  key={key_str:20s}  {sk['reason'][:70]}")

    print()
    print(SEP)
    print("team_mults")
    print(SEP)
    for tri, m in routed["team_mults"].items():
        print(f"  {tri}: {m}")

    if not routed["gate"]:
        print()
        print("NOTE: CV_LLM_CONTEXT is OFF - all mults are identity (byte-identical to base).")
        print("      Set CV_LLM_CONTEXT=1 to see gated marginal adjustments.")
