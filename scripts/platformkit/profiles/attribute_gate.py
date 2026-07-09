"""attribute_gate -- do a PROFILE ENGINE's attributes PREDICT game outcomes?

The profile engines (data/cache/profiles/) emit per-entity ATTRIBUTE values
(gravity, rim_pressure_def, platoon_resilience, ...). This is the first
PROFILE-ATTRIBUTE GATE PASS: it turns a PRIOR-SEASON attribute into a team-game
feature-diff and asks whether adding it to a leak-free Elo base improves OOS
Brier -- the SAME walk-forward / Diebold-Mariano machinery
relevance_gate.run_gate already runs (reused verbatim, not reinvented).

LEAK RULE (hard): a season's games are conditioned ONLY on a STRICTLY-PRIOR
season's profile window. A same-season window -- or a last20/clutch/home-away
PARTIAL window -- is refused with verdict SKIPPED_SAME_SEASON_WINDOW; it is not
knowable pregame. Player attrs roll up to team via a minutes/outs-weighted mean
of that team's PRIOR-season players (player_team_agg -- the moat-wave
player->team precedent); team attrs join directly (franchise id -> tricode).

VERDICT BAR (Bonferroni, DECLARED BEFORE RUNNING): with K attributes actually
gate-tested in a pass, MATTERS_PROVISIONAL iff
    delta > 0  AND  dm_p < ALPHA/K  AND  delta_t80 > 0.
Single-fold within one season -> the strongest verdict stays PROVISIONAL until
replicated on an independent season/corpus.

EXPECTATION: every pregame team-level aggregate tested in this repo so far has
been NULL (4 independent confirmations). NULL rows here are CATALOGUED SUCCESSES
that complete the attributes->predictions moat loop; the attributes' live
predictive arena may be IN-GAME conditioning, a different lane. The NBA profile
engine currently emits only the CURRENT season, so NBA attributes SKIP pregame
until a strictly-prior profile build lands -- the autoloop seam then tests them
automatically.

AUTOLOOP SEAM: run_pass() takes NO args -- latest seasons auto-detected from the
profile parquet + games table -- so a future sha-pinned template can invoke it.
(This module does NOT author that template.)

NO dollar/edge language. edge_claimed is hard-wired False.

CLI: python -m scripts.platformkit.profiles.attribute_gate [--sport nba] [--no-write]
"""
from __future__ import annotations

import argparse
import importlib
import re
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from scripts.platformkit.gamebrief.team_ids import TEAM_ID_TO_ABBR
from scripts.platformkit.intel_weighting.batter_pa_agg import aggregate_to_team_batter_pa
from scripts.platformkit.intel_weighting.player_team_agg import aggregate_to_team
from scripts.platformkit.intel_weighting.relevance_gate import (
    GateResult, _base_probs, run_gate,
)
from scripts.platformkit.intel_weighting.sport_config import (
    SEASON_STYLE, load_games, prior_season_str,
)
from scripts.platformkit.intel_weighting.weight_ledger import append_results

REPO_ROOT = Path(__file__).resolve().parents[3]
PROFILES_DIR = REPO_ROOT / "data" / "cache" / "profiles"
METHOD = "profile_attribute_gate_v1"
ALPHA = 0.05
_LEVELS = ("player", "team", "lineup")
_DOMAIN = {"nba": "basketball_nba", "wnba": "basketball_wnba"}
# sports with a wired player->team playing-time aggregation (player_team_agg)
_AGG_SPORTS = {"nba", "mlb"}
# partial-window markers -> not a plain full-season -> refused pregame (leak rule)
_PARTIAL = ("home", "away", "career", "clutch", "last", "recent", "l5", "l10", "l20")

# THE PASS: highest-value attributes per sport (mission-declared).
PASS_ATTRS: Dict[str, List[str]] = {
    "nba": ["gravity", "rim_pressure_def", "usage_absorption", "spacing_contribution",
            "stint_stamina_avg_s", "creation", "lineup_continuity_avg_stint_s"],
    "mlb": ["platoon_resilience", "mix_by_leverage", "framing", "pull_tendency",
            "contact_quality"],
}


def _window_season(window: str, style: str) -> Optional[str]:
    """Profile window label -> season string, PLAIN full-season windows only.
    'season_2025_26'->'2025-26' (split); 'season_2023'->'2023' (plain). A
    last20/clutch/home-away partial window returns None -> refused pregame."""
    w = str(window).lower()
    if any(t in w for t in _PARTIAL):
        return None
    if style == "split":
        m = re.search(r"(\d{4})[_-](\d{2})", w)
        return f"{m.group(1)}-{m.group(2)}" if m else None
    m = re.search(r"(\d{4})", w)
    return m.group(1) if m else None


def _registry_entry(sport: str, attribute: str) -> Optional[dict]:
    """This attribute's domains.<domain>.profiles.attribute_registry metadata
    dict, else None. (ask.load_registry maps sport->domain wrongly for
    nba/wnba; _DOMAIN fixes it.)"""
    try:
        mod = importlib.import_module(
            f"domains.{_DOMAIN.get(sport, sport)}.profiles.attribute_registry")
        for cand in ("ATTRIBUTES", "REGISTRY", "ATTRIBUTE_REGISTRY", "attributes"):
            o = getattr(mod, cand, None)
            if isinstance(o, dict) and isinstance(o.get(attribute), dict):
                return o[attribute]
    except Exception:  # noqa: BLE001 -- missing registry -> clean fallback
        pass
    return None


def _weight_family(sport: str, attribute: str) -> str:
    """Registry weight_ledger_family for this attribute, else 'profile_<attr>'."""
    entry = _registry_entry(sport, attribute)
    fam = entry.get("weight_ledger_family") if entry else None
    return fam or f"profile_{attribute}"


def _entity_role(sport: str, attribute: str) -> Optional[str]:
    """Registry 'entity' (batter/pitcher/catcher/...) for this attribute, else
    None -- routes MLB to the role-appropriate team aggregation: pitcher
    attributes stay outs-weighted (player_team_agg), everything else
    (batter/catcher) is PA-weighted (batter_pa_agg) since they carry no
    is_pitcher-filtered playing time."""
    entry = _registry_entry(sport, attribute)
    return entry.get("entity") if entry else None


def _locate(sport: str, attribute: str) -> Tuple[Optional[str], Optional[pd.DataFrame]]:
    """(entity_level, attribute rows) from the first profile parquet carrying it."""
    for level in _LEVELS:
        path = PROFILES_DIR / f"{sport}_{level}_profiles.parquet"
        if not path.exists():
            continue
        df = pd.read_parquet(path, columns=["entity_id", "window", "attribute", "raw_value"])
        sub = df[df["attribute"].astype(str) == attribute]
        if not sub.empty:
            return level, sub
    return None, None


def _season_values(sub: pd.DataFrame, style: str) -> Dict[str, Dict[str, float]]:
    """{season -> {entity_id: raw_value}} over PLAIN full-season windows only."""
    out: Dict[str, Dict[str, float]] = {}
    for w, grp in sub.groupby("window"):
        season = _window_season(str(w), style)
        if season is None:
            continue
        out[season] = {str(e): float(v)
                       for e, v in zip(grp["entity_id"], grp["raw_value"]) if pd.notna(v)}
    return out


def _team_feat(values: Dict[str, float]) -> Dict[str, float]:
    """team-level entity_id -> games team key (NBA franchise id -> tricode)."""
    feat: Dict[str, float] = {}
    for eid, val in values.items():
        key = TEAM_ID_TO_ABBR[int(eid)] if eid.isdigit() and int(eid) in TEAM_ID_TO_ABBR else eid
        feat[key] = val
    return feat


def _skip(family: str, sport: str, attribute: str, n: int, verdict: str, reason: str,
          mapping: str = "-", caveats: Optional[List[str]] = None) -> GateResult:
    return GateResult(family, sport, attribute, mapping, n, 0.0, 0.0, 0.0, 0.0, 1.0,
                      verdict, (caveats or []) + [reason])


def gate_attribute(sport: str, attribute: str, games_df: pd.DataFrame,
                   base_logit_getter: Callable[[], np.ndarray]) -> Tuple[GateResult, bool]:
    """Gate ONE profile attribute. Returns (GateResult, tested?) where tested is
    True only if it reached run_gate (=> counts toward the Bonferroni K)."""
    style = SEASON_STYLE.get(sport, "split")
    family = _weight_family(sport, attribute)
    n_all = len(games_df)
    level, sub = _locate(sport, attribute)
    if sub is None:
        return _skip(family, sport, attribute, n_all, "UNTESTABLE_NO_BASE",
                     "attribute absent from every profile parquet"), False

    season_vals = _season_values(sub, style)
    if not season_vals:
        return _skip(family, sport, attribute, n_all, "SKIPPED_SAME_SEASON_WINDOW",
                     "only partial windows (last20/clutch/home-away); no plain full-season"), False

    games_seasons = set(games_df["season"].astype(str))
    eval_season = next((S for S in sorted(games_seasons, reverse=True)
                        if prior_season_str(S, sport) in season_vals), None)
    if eval_season is None:
        avail = ",".join(sorted(season_vals))
        return _skip(family, sport, attribute, n_all, "SKIPPED_SAME_SEASON_WINDOW",
                     f"profile seasons [{avail}] not strictly prior to any games season "
                     "(same-season only -> not knowable pregame)"), False

    prior = prior_season_str(eval_season, sport)
    caveats = [f"eval={eval_season} conditioned on strictly-prior profile season={prior}"]
    prior_vals = season_vals[prior]

    if level == "team":
        feat, mapping = _team_feat(prior_vals), "team_franchise_direct"
    else:
        if sport not in _AGG_SPORTS:
            return _skip(family, sport, attribute, n_all, "UNTESTABLE_NO_TEAM_AGG",
                         f"no player->team playing-time aggregation wired for {sport}"), False
        role = _entity_role(sport, attribute)
        if sport == "mlb" and role != "pitcher":
            pa_role = "catcher" if role == "catcher" else "batter"
            feat, dropped = aggregate_to_team_batter_pa(prior_vals, prior, role=pa_role)
            mapping = f"{pa_role}_pa_prior_season"
        else:
            feat, dropped = aggregate_to_team(prior_vals, prior, sport=sport)
            mapping = "player_minwt_prior_season"
        if dropped:
            caveats.append(f"{len(dropped)} team(s) dropped below the coverage floor")
        if not feat:
            return _skip(family, sport, attribute, n_all, "UNTESTABLE_NO_TEAM_AGG",
                         "player->team agg left zero teams above the coverage floor "
                         "(e.g. a batter attribute vs the wired pitcher-outs weight)",
                         mapping, caveats), False

    eval_mask = (games_df["season"].astype(str) == eval_season).to_numpy()
    g = run_gate(sport, family, attribute, feat, games_df, base_logit_getter(), eval_mask, mapping)
    g.caveats = caveats + g.caveats
    return g, g.verdict in ("MATTERS_PROVISIONAL", "NULL")


def _verdict(delta: float, dm_p: float, delta_t80: float, K: int) -> str:
    """Bonferroni bar over K tested attributes (declared in the docstring)."""
    if delta > 0 and dm_p < ALPHA / max(K, 1) and delta_t80 > 0:
        return "MATTERS_PROVISIONAL"
    return "NULL"


def _base_logit_lazy(sport: str, games_df: pd.DataFrame) -> Callable[[], np.ndarray]:
    """Defer the (costly) Elo walk-forward until an attribute is actually
    testable -- an all-SKIP sport never pays for it."""
    cache: Dict[str, np.ndarray] = {}

    def getter() -> np.ndarray:
        if "l" not in cache:
            pb = np.clip(_base_probs(sport, games_df), 1e-9, 1 - 1e-9)
            cache["l"] = np.log(pb / (1 - pb))
        return cache["l"]

    return getter


def run_pass(sports: Optional[List[str]] = None, write: bool = True) -> List[GateResult]:
    """AUTOLOOP SEAM: no-args -> gate every PASS_ATTRS attribute for nba+mlb,
    latest eligible seasons auto-detected, upsert the weight ledger."""
    sports = sports or ["nba", "mlb"]
    results: List[GateResult] = []
    for sport in sports:
        games_df = load_games(sport)
        getter = _base_logit_lazy(sport, games_df)
        raw = [gate_attribute(sport, a, games_df, getter) for a in PASS_ATTRS.get(sport, [])]
        K = sum(1 for _, tested in raw if tested)
        for g, tested in raw:
            if tested:
                g.verdict = _verdict(g.delta, g.dm_p, g.delta_trunc80, K)
                g.caveats.append(f"Bonferroni K={K}: dm_p bar = {ALPHA}/{K} = {ALPHA / max(K, 1):.4g}")
            results.append(g)
    if write:
        append_results(results, method=METHOD)
    return results


def _board(results: List[GateResult]) -> None:
    print(f"\nPROFILE-ATTRIBUTE GATE ({METHOD}) -- calibration only, NO edge/$; "
          "honest NULL/SKIP is a catalogued success")
    hdr = (f"{'sport':<6}{'attribute':<28}{'n':>6}{'delta':>11}{'dm_p':>9}"
           f"{'d_t80':>11}  verdict")
    print(hdr)
    print("-" * len(hdr))
    for g in sorted(results, key=lambda r: (r.sport, r.metric)):
        print(f"{g.sport:<6}{g.metric[:27]:<28}{g.n_games:>6}{g.delta:>+11.5f}"
              f"{g.dm_p:>9.4f}{g.delta_trunc80:>+11.5f}  {g.verdict}")
    from collections import Counter
    c = Counter(g.verdict for g in results)
    print("-" * len(hdr))
    print("  ".join(f"{k}={v}" for k, v in sorted(c.items())))


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="profile-attribute relevance gate (calibration only)")
    ap.add_argument("--sport", choices=sorted(PASS_ATTRS))
    ap.add_argument("--no-write", action="store_true", help="scoreboard only, skip ledger")
    args = ap.parse_args(argv)
    results = run_pass([args.sport] if args.sport else None, write=not args.no_write)
    _board(results)
    print(f"\nledger: {'untouched (--no-write)' if args.no_write else METHOD + ' rows upserted'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
