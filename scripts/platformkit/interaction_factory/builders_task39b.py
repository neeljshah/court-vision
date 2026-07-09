"""scripts.platformkit.interaction_factory.builders_task39b -- the 3 factory
builders task 39b registers (nba_boxdetail_asof, mlb_battrack_asof,
mlb_pa_archetype_asof) plus the tennis/soccer match-level builders, split out
of runner.py to keep that module under its LOC budget. Same contract as any
other runner builder: `builder(attrs, tpl) -> {"frame", "cluster", "corpus",
"kind", ...} | None` -- registered into runner._BUILDERS by runner.py itself.

`build_mlb_pa_archetype_frame` reuses runner.build_mlb_pa_frame verbatim (no
reimplementation); imported LAZILY inside the function body to avoid a
circular import (runner.py imports this module's builders into _BUILDERS).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

REPO = Path(__file__).resolve().parents[3]

# --------------------------------------------------------------------------
# NBA BOX-DETAIL builder (task-39b). boxdetail_asof.parquet (domains.
# basketball_nba.boxdetail_asof, commit bcaa6d7a) is ALREADY a leak-free
# strictly-prior team diff -- this builder only attaches walk-forward Elo +
# home_win, reusing asof_ast_rate_eval.build_candidate_frame verbatim (the
# same Elo+games.parquet merge every other as-of reclaim in this domain uses).
#
# KNOWN LIMITATION (boxdetail_gate.py already found this): box-detail's
# on-disk history starts 2026-01-20, entirely AFTER games.parquet's 70%
# walk-forward train cutoff. That gate's own `_train_window_has_coverage`
# helper is REUSED here (not reimplemented) as a pre-fit guard: if the family
# has no train-window coverage, every candidate in the batch is marked
# NOT_TESTABLE with an explicit reason instead of running a fit whose
# standardization would silently degenerate on an all-NaN train column.
_NBA_BOXDETAIL_SOURCE = REPO / "data" / "domains" / "basketball_nba" / "boxdetail_asof.parquet"
_NBA_BOXDETAIL_CORPUS = "boxdetail_asof"


def _nba_boxdetail_diff_col(attr: str) -> str:
    """Registry attr name ('fast_break_pts_asof') -> boxdetail_asof.parquet's
    diff column ('fast_break_pts_diff_asof') -- same _asof-suffix-strip the
    registry's own ingredient mapping uses (attribute_registry.py _BOXDETAIL_SPECS)."""
    base = attr[: -len("_asof")] if attr.endswith("_asof") else attr
    return base + "_diff_asof"


def build_nba_boxdetail_frame(attrs: List[str], asof: pd.DataFrame,
                               games: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """Per-game frame for the box-detail self-cross template: y=home_win,
    asof__<attr> = boxdetail_asof.parquet's own diff column (already leak-free,
    see boxdetail_asof.py), p_base = walk-forward Elo. Merges, invents nothing."""
    from domains.basketball_nba import asof_ast_rate_eval as _eval
    diff_cols = sorted({_nba_boxdetail_diff_col(a) for a in attrs})
    out = _eval.build_candidate_frame(games=games, asof=asof, feat_col=diff_cols[0])
    out = out[["game_id", "home_win", "p_base", diff_cols[0]]].copy()
    for dc in diff_cols[1:]:
        extra = asof[["game_id", dc]].copy()
        extra["game_id"] = extra["game_id"].astype(str)
        out = out.merge(extra, on="game_id", how="left")
    out = out.rename(columns={_nba_boxdetail_diff_col(a): "asof__" + a for a in attrs})
    out["y"] = out["home_win"]
    return out


def _nba_boxdetail_builder(attrs: List[str], tpl: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not _NBA_BOXDETAIL_SOURCE.exists():
        return None
    from domains.basketball_nba import boxdetail_gate as _bdgate  # noqa: SLF001 -- reuse the sibling gate's own guard, not a reimplementation
    asof = pd.read_parquet(_NBA_BOXDETAIL_SOURCE)
    probe_col = _nba_boxdetail_diff_col(attrs[0])  # all 5 stats share one all-or-nothing coverage window (boxdetail_asof.py docstring) -- one probe suffices for the whole family
    if not _bdgate._train_window_has_coverage(probe_col):
        return {"frame": pd.DataFrame(), "cluster": "game_id", "corpus": _NBA_BOXDETAIL_CORPUS, "kind": "logit",
                "insufficient_train_history": True,
                "train_note": "box-detail's on-disk history (2026-01-20+) falls entirely after "
                              "the sibling gate's 70pct walk-forward train cutoff -- reusing "
                              "boxdetail_gate._train_window_has_coverage rather than a fake fit."}
    frame = build_nba_boxdetail_frame(attrs, asof)
    return {"frame": frame, "cluster": "game_id", "corpus": _NBA_BOXDETAIL_CORPUS,
            "kind": "logit", "covariate": "p_base"}


# --------------------------------------------------------------------------
# MLB BAT-TRACKING self-cross builder (task-39b). Season-Y bat-tracking attrs
# (data/cache/profiles/mlb_player_profiles.parquet, long format: entity_id,
# window='season_YYYY', attribute, raw_value) -> season-(Y+1) contact_quality
# outcome. Leak-free BY CONSTRUCTION: features and outcome are disjoint,
# non-overlapping season windows, features strictly precede the outcome
# season -- not a within-season correlation.
_MLB_PROFILES_SOURCE = REPO / "data" / "cache" / "profiles" / "mlb_player_profiles.parquet"
_MLB_BATTRACK_OUTCOME_ATTR = "contact_quality"
_MLB_BATTRACK_CORPUS = "mlb_player_profiles_battrack"


def _profile_season(window: object) -> Optional[int]:
    """'season_2024' -> 2024; anything else -> None (never guessed)."""
    s = str(window)
    if not s.startswith("season_"):
        return None
    try:
        return int(s[len("season_"):])
    except ValueError:
        return None


def build_mlb_battrack_frame(profiles: pd.DataFrame, attrs: List[str]) -> pd.DataFrame:
    """Pivot the long-format profile store to season-Y bat-tracking attrs join
    season-(Y+1) contact_quality. Returns 0 rows (never fabricated) if a
    batter's season-Y bat-tracking season and season-(Y+1) contact_quality
    season don't both exist on disk -- bat-tracking covers 2024-2026,
    contact_quality only covers 2023-2024, so today's on-disk corpora have
    ZERO (Y, Y+1) overlap; an honest data-coverage gap, not a code bug --
    candidates fall out NOT_TESTABLE via the standard MIN_N path, same as any
    other under-covered pair."""
    keep_attrs = [a for a in attrs if a != _MLB_BATTRACK_OUTCOME_ATTR]
    df = profiles[profiles["attribute"].isin(keep_attrs + [_MLB_BATTRACK_OUTCOME_ATTR])].copy()
    df["season"] = df["window"].map(_profile_season)
    df = df[df["season"].notna()]
    piv = df.pivot_table(index=["entity_id", "season"], columns="attribute",
                          values="raw_value", aggfunc="first").reset_index()
    if _MLB_BATTRACK_OUTCOME_ATTR not in piv.columns:
        return pd.DataFrame(columns=["entity_id", "y"] + ["asof__" + a for a in keep_attrs])
    have = [a for a in keep_attrs if a in piv.columns]
    feat = piv[["entity_id", "season"] + have].rename(columns={a: "asof__" + a for a in have})
    outc = piv[["entity_id", "season", _MLB_BATTRACK_OUTCOME_ATTR]].rename(
        columns={_MLB_BATTRACK_OUTCOME_ATTR: "y"}).dropna(subset=["y"])
    outc = outc.copy()
    outc["season"] = outc["season"] - 1  # contact_quality's own season S belongs to feature season Y=S-1
    return feat.merge(outc, on=["entity_id", "season"], how="inner")


def _mlb_battrack_builder(attrs: List[str], tpl: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not _MLB_PROFILES_SOURCE.exists():
        return None
    profiles = pd.read_parquet(_MLB_PROFILES_SOURCE, columns=["entity_id", "window", "attribute", "raw_value"])
    frame = build_mlb_battrack_frame(profiles, attrs)
    return {"frame": frame, "cluster": "entity_id", "corpus": _MLB_BATTRACK_CORPUS, "kind": "ols"}


# --------------------------------------------------------------------------
# MLB PA x TEAM-ARCHETYPE builder (task-39b). Reuses runner.build_mlb_pa_frame
# verbatim (no reimplementation, lazy import to avoid a circular import) and
# adds each PA's batting team (canonical dialect) so entity-class candidates
# can scope the frame to one archetype's member teams (see
# runner._fit_candidate's entity_class handling). Team-archetype membership
# itself is reused from domains.mlb.atlas_playstyles' own classifier over
# games.parquet -- no new archetype logic.
_MLB_ARCHETYPE_ALIAS_EXTRA = {"CUB": "CHC", "LOS": "LAD", "SFG": "SF"}  # games.parquet carries both dialects for these 3 franchises; GC_TO_PG_TEAM below doesn't


def _mlb_canon_team(code: object) -> str:
    from domains.mlb.game_pk_bridge import GC_TO_PG_TEAM
    s = str(code).strip().upper()
    s = GC_TO_PG_TEAM.get(s, s)
    return _MLB_ARCHETYPE_ALIAS_EXTRA.get(s, s)


def mlb_team_archetype_members() -> Dict[str, set]:
    """slug -> canonical (Statcast-dialect) team-code set, reusing
    atlas_playstyles' own classifier over games.parquet (its team-code dialect
    differs from Statcast's; canonicalized here so the join works)."""
    from domains.mlb.atlas_playstyles import _classify, _compute_team_stats, _load_games  # noqa: SLF001 -- reuse, not reinvent
    games = _load_games(REPO / "data" / "domains" / "mlb")
    assignment = _classify(_compute_team_stats(games))
    return {slug: {_mlb_canon_team(t) for t in teams} for slug, teams in assignment.items()}


def build_mlb_pa_archetype_frame(pitch_df: pd.DataFrame, attrs: List[str]) -> pd.DataFrame:
    """runner.build_mlb_pa_frame's own leak-free PA frame, plus each PA's
    batting team (canonical dialect) for entity-class scoping."""
    from scripts.platformkit.interaction_factory.runner import build_mlb_pa_frame  # lazy: avoid circular import
    frame = build_mlb_pa_frame(pitch_df, attrs)
    tm = pitch_df[["game_pk", "at_bat_number", "home_team", "away_team", "inning_topbot"]].drop_duplicates(
        ["game_pk", "at_bat_number"])
    is_top = tm["inning_topbot"].astype(str).str.strip().str.lower().eq("top")
    tm = tm.assign(team=tm["away_team"].where(is_top, tm["home_team"]).map(_mlb_canon_team))
    return frame.merge(tm[["game_pk", "at_bat_number", "team"]], on=["game_pk", "at_bat_number"], how="left")


def _mlb_pa_archetype_builder(attrs: List[str], tpl: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    from scripts.platformkit.interaction_factory import runner as _runner  # lazy: avoid circular import; reuse its source-of-truth path/corpus, not a duplicate
    if not _runner._MLB_PA_SOURCE.exists():
        return None
    cols = ["game_pk", "game_date", "at_bat_number", "pitch_number", "pitcher", "batter",
            "events", "description", "launch_speed", "home_team", "away_team", "inning_topbot"]
    pitch_df = pd.read_parquet(_runner._MLB_PA_SOURCE, columns=cols)
    frame = build_mlb_pa_archetype_frame(pitch_df, attrs)
    return {"frame": frame, "cluster": "pitcher", "corpus": _runner._MLB_PA_CORPUS, "kind": "logit",
            "archetype_members": mlb_team_archetype_members(), "entity_col": "team"}


# --------------------------------------------------------------------------
# TENNIS / SOCCER match-level self-cross builders (task-39b). Both pools
# (generator.STATIC_POOLS) are pre-built diff_*_asof columns ALREADY on disk
# (leak-free by their own module's construction) -- these builders only merge
# them onto each sport's real match outcome, keyed on the shared event_id.
_TENNIS_MATCHES = REPO / "data" / "domains" / "tennis" / "matches.parquet"
_TENNIS_RETURN = REPO / "data" / "domains" / "tennis" / "asof_return.parquet"
_TENNIS_FEATURES = REPO / "data" / "domains" / "tennis" / "asof_features.parquet"
_TENNIS_CORPUS = "tennis_asof_return_features"


def build_tennis_match_frame(matches: pd.DataFrame, ret: pd.DataFrame, feats: pd.DataFrame,
                              attrs: List[str]) -> pd.DataFrame:
    m = matches[["event_id", "tourney_id", "winner"]].copy()
    m["y"] = (m["winner"] == 1).astype(float)
    r_cols = ["event_id"] + [c for c in attrs if c in ret.columns]
    f_cols = ["event_id"] + [c for c in attrs if c in feats.columns and c not in ret.columns]
    out = m.merge(ret[r_cols], on="event_id", how="left")
    if len(f_cols) > 1:
        out = out.merge(feats[f_cols], on="event_id", how="left")
    return out.rename(columns={a: "asof__" + a for a in attrs if a in out.columns})


def _tennis_match_builder(attrs: List[str], tpl: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not (_TENNIS_MATCHES.exists() and _TENNIS_RETURN.exists() and _TENNIS_FEATURES.exists()):
        return None
    matches = pd.read_parquet(_TENNIS_MATCHES, columns=["event_id", "tourney_id", "winner"])
    ret = pd.read_parquet(_TENNIS_RETURN)
    feats = pd.read_parquet(_TENNIS_FEATURES)
    frame = build_tennis_match_frame(matches, ret, feats, attrs)
    return {"frame": frame, "cluster": "tourney_id", "corpus": _TENNIS_CORPUS, "kind": "logit"}


_SOCCER_MATCHES = REPO / "data" / "domains" / "soccer" / "matches.parquet"
_SOCCER_FEATURES = REPO / "data" / "domains" / "soccer" / "asof_features.parquet"
_SOCCER_CORPUS = "soccer_asof_features"


def build_soccer_match_frame(matches: pd.DataFrame, feats: pd.DataFrame, attrs: List[str]) -> pd.DataFrame:
    m = matches[["event_id", "div", "fthg", "ftag"]].copy()
    m["y"] = (m["fthg"] > m["ftag"]).astype(float)
    f_cols = ["event_id"] + [c for c in attrs if c in feats.columns]
    out = m.merge(feats[f_cols], on="event_id", how="left")
    return out.rename(columns={a: "asof__" + a for a in attrs if a in out.columns})


def _soccer_match_builder(attrs: List[str], tpl: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not (_SOCCER_MATCHES.exists() and _SOCCER_FEATURES.exists()):
        return None
    matches = pd.read_parquet(_SOCCER_MATCHES, columns=["event_id", "div", "fthg", "ftag"])
    feats = pd.read_parquet(_SOCCER_FEATURES)
    frame = build_soccer_match_frame(matches, feats, attrs)
    return {"frame": frame, "cluster": "div", "corpus": _SOCCER_CORPUS, "kind": "logit"}


__all__ = [
    "build_nba_boxdetail_frame", "build_mlb_battrack_frame", "build_mlb_pa_archetype_frame",
    "mlb_team_archetype_members", "build_tennis_match_frame", "build_soccer_match_frame",
    "_nba_boxdetail_builder", "_mlb_battrack_builder", "_mlb_pa_archetype_builder",
    "_tennis_match_builder", "_soccer_match_builder",
]
