"""scripts.platformkit.combo.corpus_cache -- gate-ready per-sport corpus builder.

GENERALIZES what the wave-1 sport runners hand-rolled inline: one gate-ready
frame per sport, persisted so batch_gate.py / null_floor.py never re-replay a
base construction per candidate. Each sport's base p_base replay is REUSED
EXACTLY from the wave-1/A1 runner (same public fn, same call pattern) --
never re-derived here.

Sports: mlb, nba, soccer, tennis. Output: one row per event with keys
(event_id, corpus_unit, y, p_base) + every currently-legal leak-free
ingredient column at full coverage (NaN where absent -- consumers apply the
score_with_fallback contract, never this module).

STALENESS CONTRACT: a sidecar JSON records each SOURCE file's mtime+sha256 at
build time. `load_gate_corpus` refuses (raises StaleCorpusError) if any
source file's mtime OR sha differs from what the sidecar recorded -- an
honest error, never a silent stale read.

Calibration, not edge. NO $/ROI anywhere. pandas + numpy + stdlib only. ASCII.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from domains.basketball_nba.ratings import walk_forward_elo as nba_walk_forward_elo  # noqa: E402
from domains.mlb.asof_sp_form import build_sp_form_features  # noqa: E402
from domains.mlb.ratings import walk_forward_elo as mlb_walk_forward_elo  # noqa: E402
from domains.soccer.ratings import walk_forward_goals  # noqa: E402
from domains.tennis.elo_walkforward import walk_forward_elo as tennis_walk_forward_elo  # noqa: E402
from scripts.platformkit.combo.stack_fit import logit  # noqa: E402

_CACHE_DIR = _REPO / "data" / "cache" / "combo"
SPORTS: Tuple[str, ...] = ("mlb", "nba", "soccer", "tennis")
# The column a walk-forward over a gate corpus may order by, and the honest
# label for a corpus that carries no such column (gap S44).
DATE_COL = "event_date"
POSITIONAL_ORDER = "POSITIONAL-ORDER"


class StaleCorpusError(RuntimeError):
    """A cached corpus's source files moved since it was built -- refuse the read."""


def _corpus_path(sport: str) -> Path:
    return _CACHE_DIR / f"gate_corpus_{sport}.parquet"


def _sidecar_path(sport: str) -> Path:
    return _CACHE_DIR / f"gate_corpus_{sport}.sources.json"


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def _source_manifest(paths: List[Path]) -> Dict[str, Dict[str, object]]:
    return {str(p): {"mtime": p.stat().st_mtime, "sha256": _file_sha256(p)} for p in paths}


# --------------------------------------------------------------------------- #
# Per-sport gate-ready frame builders (mirror the wave-1 runner exactly)
# --------------------------------------------------------------------------- #

def _build_mlb() -> Tuple[pd.DataFrame, List[Path]]:
    """games.parquet (2010-2021) + games_current.parquet (2022-2026) eras as
    corpus_unit; base = 2-feature [elo_logit, z(sp_first6_diff_ew)] mirroring
    domains.mlb.pregame_stack_gate._fit_base's ingredients exactly."""
    games_a = _REPO / "data/domains/mlb/games.parquet"
    games_b = _REPO / "data/domains/mlb/games_current.parquet"
    park = _REPO / "data/domains/mlb/asof_park.parquet"
    asof = _REPO / "data/domains/mlb/asof_features.parquet"
    sources = [games_a, games_b, park, asof]

    sp = build_sp_form_features()[["event_id", "sp_first6_diff_ew"]]
    park_df = pd.read_parquet(park)[["event_id", "park_factor"]]
    ra_df = pd.read_parquet(asof)[["event_id", "sp_ra_diff_asof"]]

    frames = []
    for path, unit in ((games_a, "era_2010_2021"), (games_b, "era_2022_2026")):
        games = pd.read_parquet(path)
        games = games[games["target_home_win"].notna()].reset_index(drop=True)
        elo = mlb_walk_forward_elo(games)[["event_id", "date", "p_home_elo"]]
        out = games[["event_id", "target_home_win"]].merge(elo, on="event_id", how="left")
        out = out.merge(sp, on="event_id", how="left")
        out = out.merge(park_df, on="event_id", how="left")
        out = out.merge(ra_df, on="event_id", how="left")
        out = out.sort_values("date").reset_index(drop=True)
        out["corpus_unit"] = unit
        out["y"] = out["target_home_win"].astype(float)
        out["p_base"] = np.nan  # base needs a walk-forward LOGISTIC fit -- see note below
        frames.append(out)
    df = pd.concat(frames, ignore_index=True)
    # p_base here is the pre-stack ELO probability (a legal, cheap standalone base
    # ingredient); the 2-feature LOGISTIC p_base used by judge_stack_family is
    # fit per-candidate inside stack_gate_pregame callers (train-only), never cached
    # -- caching a FIT would freeze a standardizer across candidates, which the
    # prereg forbids. This module caches the INGREDIENT columns, not a frozen fit.
    df["p_base"] = df["p_home_elo"].astype(float)
    df[DATE_COL] = df["date"]  # S44: surface the builder's own date, renaming nothing
    return df[["event_id", "corpus_unit", DATE_COL, "y", "p_base", "p_home_elo",
              "sp_first6_diff_ew", "park_factor", "sp_ra_diff_asof"]], sources


# asof_features.parquet ships raw home/away asof pace/oreb/tov columns, not the
# diff -- mirrors asof_reclaim_dims.py's _PAIR_DIFFS mapping exactly (imported
# name, never re-derived independently of that module's convention).
_NBA_PAIR_DIFFS: Dict[str, Tuple[str, str]] = {
    "pace_diff_asof": ("home_pace_asof", "away_pace_asof"),
    "oreb_pg_diff_asof": ("home_oreb_pg_asof", "away_oreb_pg_asof"),
    "tov_pg_diff_asof": ("home_tov_pg_asof", "away_tov_pg_asof"),
}


def _build_nba() -> Tuple[pd.DataFrame, List[Path]]:
    """Season-disjoint 2-corpus pair (PREREG_AMENDMENT_A2_2026-07-05.md Family 2
    re-open): asof_features_ext/asof_box_extra_ext (commit 4cee589d) carry BOTH
    2024-25 (1225 rows) and 2025-26 (589 rows); `season` from games.parquet
    splits them into corpus_unit='2024-25'/'2025-26'. Base = walk-forward Elo on
    games.parquet, joined to the ext ingredient parquets on game_id -- SAME
    construction as the pre-A2 single-corpus build, just on the widened _ext
    sources. Also derives the two A2 product terms (N1 dreb*pace, N2 stl*fg3m)
    as plain columns so batch_gate's declarative feature-name specs can select
    them directly."""
    games_path = _REPO / "data/domains/basketball_nba/games.parquet"
    asof = _REPO / "data/domains/basketball_nba/asof_features_ext.parquet"
    box_extra = _REPO / "data/domains/basketball_nba/asof_box_extra_ext.parquet"
    sources = [games_path, asof, box_extra]

    games = pd.read_parquet(games_path)
    games = games[games["home_win"].notna()].reset_index(drop=True)
    games["season_label"] = games["season"].astype(str)  # keep '2024-25' for corpus_unit later
    # walk_forward_elo requires an INT season (season-boundary regression); games.parquet
    # ships '2022-23' style strings -- start-year convention mirrors adapter.py._season_to_int.
    games["season"] = games["season_label"].str.split("-").str[0].astype(int)
    wf = nba_walk_forward_elo(games)
    elo_col = next((c for c in ("p_home_elo", "win_prob_home", "p_elo") if c in wf.columns), None)
    elo_sel = wf[["game_id", elo_col]].rename(columns={elo_col: "p_elo"}) if elo_col else \
        wf[["game_id"]].assign(p_elo=np.nan)

    af = pd.read_parquet(asof)
    for out_col, (h, a) in _NBA_PAIR_DIFFS.items():
        af[out_col] = af[h].astype(float) - af[a].astype(float) if h in af.columns and a in af.columns else np.nan
    box = pd.read_parquet(box_extra)
    box_keep = [c for c in ("dreb_diff_asof", "fg3m_diff_asof", "stl_diff_asof", "blk_diff_asof")
               if c in box.columns]

    # asof_features_ext (1814 rows, the widened 2-season box-era universe) drives
    # the corpus; games/elo and box_extra_ext are LEFT-merged onto it (both are
    # supersets keyed on game_id).
    out = af[["game_id"] + list(_NBA_PAIR_DIFFS.keys())].merge(
        box[["game_id"] + box_keep], on="game_id", how="left")
    out = out.merge(games[["game_id", "date", "season_label", "home_win"]], on="game_id", how="left")
    out = out.merge(elo_sel, on="game_id", how="left")
    out = out.sort_values("date").reset_index(drop=True)

    out["event_id"] = out["game_id"].astype(str)
    out["corpus_unit"] = out["season_label"]  # '2024-25' / '2025-26' -- season-disjoint
    out["y"] = out["home_win"].astype(float)
    out["p_base"] = out["p_elo"].astype(float)
    # A2 K_new product terms (raw, pre-standardization -- z() happens at fit time).
    out["dreb_x_pace_asof"] = out["dreb_diff_asof"] * out["pace_diff_asof"]
    out["stl_x_fg3m_asof"] = out["stl_diff_asof"] * out["fg3m_diff_asof"]
    out[DATE_COL] = out["date"]  # S44: surface the builder's own date, renaming nothing
    cols = (["event_id", "corpus_unit", DATE_COL, "y", "p_base", "p_elo"] + box_keep
           + list(_NBA_PAIR_DIFFS.keys()) + ["dreb_x_pace_asof", "stl_x_fg3m_asof"])
    return out[cols], sources


# Same-match (post-kickoff) soccer facts: final shots/SOT/corners/fouls/cards,
# half-time and full-time goals, the label itself, post-match residuals, and any
# whole-season team aggregate that CONTAINS the match being scored
# (style_fingerprints). A column named here is a leak, never an as-of ingredient
# for the gate spine (gap S53).
SOCCER_LEAKY_COLUMNS = frozenset({
    "home_shots", "away_shots", "home_sot", "away_sot", "home_corners", "away_corners",
    "home_fouls", "away_fouls", "home_yellow", "away_yellow", "home_red", "away_red",
    "total_shots", "total_sot", "home_sot_ratio", "away_sot_ratio",
    "hthg", "htag", "htr", "fthg", "ftag", "ftr", "total_goals", "target_over25",
    "total_fouls", "total_yellow", "total_red", "total_cards",
    "shot_share", "sot_ratio", "fouls_committed_pm", "fouls_drawn_pm", "corners_pm",
    "cards_pm", "ppg", "finishing_residual_home", "finishing_residual_away", "sot_diff",
})

# The as-of ingredient columns the soccer spine carried before S53 (order kept
# exactly) and the ones S53 joins in addition. Both families are prior-only.
_SOCCER_ASOF_EXISTING: Tuple[str, ...] = (
    "home_sot_for_l10", "away_sot_for_l10", "diff_sot_for_asof", "diff_sot_against_asof",
    "diff_shots_for_asof", "diff_shots_against_asof", "home_sot_ratio_for_asof",
    "away_sot_ratio_for_asof", "home_n_prior", "away_n_prior")
# asof_features.parquet already shipped these eight; the builder selected them out.
_SOCCER_ASOF_ADDED: Tuple[str, ...] = (
    "home_sot_for_asof", "home_sot_against_asof", "home_shots_for_asof",
    "home_shots_against_asof", "away_sot_for_asof", "away_sot_against_asof",
    "away_shots_for_asof", "away_shots_against_asof")


def _asof_only(columns: List[str]) -> List[str]:
    """Refuse a same-match column by name before it can reach the gate spine."""
    leaky = sorted(set(columns) & SOCCER_LEAKY_COLUMNS)
    if leaky:
        raise ValueError("same-match (leaky) column(s) refused for the soccer gate "
                         "spine: " + ", ".join(leaky))
    return list(columns)


def _build_soccer() -> Tuple[pd.DataFrame, List[Path], Dict[str, Dict[str, object]]]:
    """matches.parquet `div` column = disjoint-league corpus_unit; base = Poisson
    walk_forward_goals p_over25, mirrors home_sot_replication_gate exactly.

    S53 additively joins the as-of ingredients that already exist on disk at this
    spine's own `event_id` grain: the eight asof_features columns the selection
    dropped, plus the leak-free as-of xG-PROXY family
    (`domains.soccer.asof_xg_proxy`, prior-only by construction). Nothing
    same-match is joined -- `_asof_only` refuses those by name.
    """
    matches = _REPO / "data/domains/soccer/matches.parquet"
    asof = _REPO / "data/domains/soccer/asof_features.parquet"
    xg = _REPO / "data/domains/soccer/asof_xg_proxy.parquet"
    sources = [matches, asof, xg]

    mdf = pd.read_parquet(matches)
    mdf["event_id"] = mdf["event_id"].astype(str)
    total_goals = (pd.to_numeric(mdf["fthg"], errors="coerce")
                  + pd.to_numeric(mdf["ftag"], errors="coerce"))
    mdf["target_over25"] = (total_goals >= 3).astype(float)
    mdf = mdf[total_goals.notna()].copy()
    wf = walk_forward_goals(mdf)
    wf["event_id"] = wf["event_id"].astype(str)
    wf["p_over25"] = np.clip(wf["p_over25"].astype(float), 1e-6, 1 - 1e-6)

    adf = pd.read_parquet(asof)
    adf["event_id"] = adf["event_id"].astype(str)
    adf = adf.drop_duplicates("event_id", keep="first")
    ing_cols = _asof_only([c for c in _SOCCER_ASOF_EXISTING if c in adf.columns])
    added_cols = _asof_only([c for c in _SOCCER_ASOF_ADDED if c in adf.columns])

    out = wf.merge(adf[["event_id"] + ing_cols + added_cols], on="event_id", how="left")

    # S53: the as-of xG-PROXY family, same event_id spine. home_n_prior /
    # away_n_prior already arrive from asof_features and are NOT re-joined.
    xdf = pd.read_parquet(xg)
    xdf["event_id"] = xdf["event_id"].astype(str)
    xdf = xdf.drop_duplicates("event_id", keep="first")
    xg_cols = _asof_only([c for c in xdf.columns
                          if c != "event_id" and c not in ing_cols + added_cols])
    out = out.merge(xdf[["event_id"] + xg_cols], on="event_id", how="left")

    out["corpus_unit"] = out["div"].astype(str) if "div" in out.columns else "unknown_league"
    out["y"] = out["target_over25"].astype(float)
    out["p_base"] = out["p_over25"].astype(float)
    out[DATE_COL] = out["date"]  # S44: surface the builder's own date, renaming nothing
    provenance = {col: {"source": str(src.relative_to(_REPO)).replace("\\", "/"),
                        "join_key": "event_id", "n_rows": int(len(out)),
                        "n_joined": int(out[col].notna().sum()),
                        "join_rate": round(float(out[col].notna().mean()), 6)}
                  for cols, src in ((added_cols, asof), (xg_cols, xg)) for col in cols}
    return out[["event_id", "corpus_unit", DATE_COL, "y", "p_base", "p_over25"]
              + ing_cols + added_cols + xg_cols], sources, provenance


def _build_tennis() -> Tuple[pd.DataFrame, List[Path]]:
    """matches.parquet (ATP) / wta_matches.parquet (WTA) = tour corpus_unit;
    base = walk-forward Elo, mirrors interaction_gate_math.build_corpus_frame."""
    atp_m = _REPO / "data/domains/tennis/matches.parquet"
    atp_h = _REPO / "data/domains/tennis/asof_hold.parquet"
    wta_m = _REPO / "data/domains/tennis/wta_matches.parquet"
    wta_h = _REPO / "data/domains/tennis/asof_hold_wta.parquet"
    ret = _REPO / "data/domains/tennis/asof_return.parquet"
    sources = [atp_m, atp_h, wta_m, wta_h, ret]

    frames = []
    for m_path, h_path, unit in ((atp_m, atp_h, "ATP"), (wta_m, wta_h, "WTA")):
        mm = pd.read_parquet(m_path)
        mm = mm[mm["winner"].notna()].reset_index(drop=True)
        wf = tennis_walk_forward_elo(mm)
        elo_col = next((c for c in ("win_prob_p1", "p_elo") if c in wf.columns), None)
        out = wf[["event_id", "date", "winner"] + ([elo_col] if elo_col else [])].rename(
            columns={elo_col: "p_elo"} if elo_col else {})
        if "p_elo" not in out.columns:
            out["p_elo"] = np.nan
        out["target_p1_win"] = (out["winner"].astype(float) == 1.0).astype(float)

        hold = pd.read_parquet(h_path)
        hold_cols = [c for c in ("event_id", "surface", "p1_n_prior", "p2_n_prior",
                                 "p1_hold_pct_asof", "p2_hold_pct_asof") if c in hold.columns]
        hold_sel = hold[hold_cols].drop_duplicates("event_id", keep="first")
        out = out.merge(hold_sel, on="event_id", how="left")

        ret_df = pd.read_parquet(ret)
        ret_cols = [c for c in ("event_id", "diff_return_won_asof", "diff_break_pct_asof")
                   if c in ret_df.columns]
        out = out.merge(ret_df[ret_cols].drop_duplicates("event_id", keep="first"),
                        on="event_id", how="left")
        out["corpus_unit"] = unit
        out["y"] = out["target_p1_win"]
        out["p_base"] = out["p_elo"].astype(float)
        frames.append(out)
    df = pd.concat(frames, ignore_index=True)
    df[DATE_COL] = df["date"]  # S44: surface the builder's own date, renaming nothing
    keep = ["event_id", "corpus_unit", DATE_COL, "y", "p_base", "p_elo", "surface",
           "p1_hold_pct_asof", "p2_hold_pct_asof", "diff_return_won_asof", "diff_break_pct_asof"]
    return df[[c for c in keep if c in df.columns]], sources


_BUILDERS = {"mlb": _build_mlb, "nba": _build_nba, "soccer": _build_soccer, "tennis": _build_tennis}


def build_gate_corpus(sport: str) -> pd.DataFrame:
    """Build ONE sport's gate-ready frame, persist to parquet + sources sidecar."""
    if sport not in _BUILDERS:
        raise ValueError(f"unknown sport {sport!r}; must be one of {SPORTS}")
    # A builder may return a third element: per-added-column provenance (S53).
    built = _BUILDERS[sport]()
    df, sources = built[0], built[1]
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    df.to_parquet(_corpus_path(sport), index=False)
    manifest = {"sport": sport, "built_at": time.time(), "n_rows": len(df),
               "sources": _source_manifest(sources),
               "provenance": built[2] if len(built) > 2 else {}}
    _sidecar_path(sport).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return df


def load_gate_corpus(sport: str) -> pd.DataFrame:
    """Load a cached corpus; refuse (StaleCorpusError) if any source file moved."""
    cp, sp = _corpus_path(sport), _sidecar_path(sport)
    if not cp.exists() or not sp.exists():
        raise StaleCorpusError(f"no cached corpus for {sport!r}; run build_gate_corpus first")
    manifest = json.loads(sp.read_text(encoding="utf-8"))
    for src, rec in manifest.get("sources", {}).items():
        p = Path(src)
        if not p.exists():
            raise StaleCorpusError(f"source {src} for {sport!r} corpus no longer exists")
        if p.stat().st_mtime != rec["mtime"] or _file_sha256(p) != rec["sha256"]:
            raise StaleCorpusError(
                f"source {src} for {sport!r} corpus changed since build "
                f"(mtime/sha mismatch) -- rebuild via build_gate_corpus({sport!r})")
    return pd.read_parquet(cp)


def freshness_report(sport: str) -> Dict[str, object]:
    """Read-only freshness + ordering facts for one cached corpus (gap S41).

    Never rebuilds and never raises on a stale cache -- `stale` is a plain bool
    the caller decides on, unlike `load_gate_corpus` which refuses. Row counts:
    `n_rows_at_build` is what the sidecar recorded when the cache was written,
    `n_rows_cached` is what the parquet holds now. `order_basis` is the column a
    walk-forward over this corpus may order by, or the literal
    "POSITIONAL-ORDER" when the corpus carries no date column (gap S44).
    """
    if sport not in _BUILDERS:
        raise ValueError(f"unknown sport {sport!r}; must be one of {SPORTS}")
    cp, sp = _corpus_path(sport), _sidecar_path(sport)
    rep: Dict[str, object] = {
        "sport": sport, "corpus_path": str(cp),
        "cache_exists": cp.exists(), "sidecar_exists": sp.exists(),
        "cache_mtime": cp.stat().st_mtime if cp.exists() else None,
        "built_at": None, "n_rows_at_build": None, "n_rows_cached": None,
        "sources": [], "stale": True, "stale_reason": "no cached corpus or sidecar",
        "order_basis": POSITIONAL_ORDER, "provenance": {},
    }
    if not (cp.exists() and sp.exists()):
        return rep
    manifest = json.loads(sp.read_text(encoding="utf-8"))
    rep["built_at"] = manifest.get("built_at")
    rep["n_rows_at_build"] = manifest.get("n_rows")
    # S53: per-added-column source parquet + join key + join rate, or {} where
    # the builder joins no extra ingredient family.
    rep["provenance"] = manifest.get("provenance", {})
    cached = pd.read_parquet(cp)
    rep["n_rows_cached"] = len(cached)
    rep["order_basis"] = DATE_COL if DATE_COL in cached.columns else POSITIONAL_ORDER
    changed_names: List[str] = []
    for src, rec in manifest.get("sources", {}).items():
        p = Path(src)
        exists = p.exists()
        now = p.stat().st_mtime if exists else None
        changed = (not exists) or now != rec["mtime"] or _file_sha256(p) != rec["sha256"]
        rep["sources"].append({"path": src, "exists": exists, "changed": changed,
                              "mtime_at_build": rec["mtime"], "mtime_now": now})
        if changed:
            changed_names.append(p.name)
    rep["stale"] = bool(changed_names)
    rep["stale_reason"] = ("sources changed since build: " + ", ".join(changed_names)
                          if changed_names else None)
    return rep


__all__ = ["SPORTS", "DATE_COL", "POSITIONAL_ORDER", "SOCCER_LEAKY_COLUMNS",
           "StaleCorpusError", "build_gate_corpus", "load_gate_corpus", "freshness_report"]
