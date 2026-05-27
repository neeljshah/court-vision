"""Build per-player-season breakdown feature parquet from misc, scoring, and matchup sources.

Sources (all under data/nba/):
  - player_misc_2024-25.json      → misc scoring-profile features (paint, fast-break, etc.)
  - player_scoring_2024-25.json   → shot-distribution & creation-mode pcts
  - boxscore_matchups_004*.json   → per-game offensive matchup splits (separate grain)

Outputs:
  data/cache/player_breakdown_features.parquet   (player_id, season + all features)
  data/cache/matchup_breakdown_features.parquet  (player_id, game_id + matchup features)

Idempotent — safe to rerun.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ── paths ─────────────────────────────────────────────────────────────────────
REPO = Path(__file__).resolve().parent.parent
DATA_NBA = REPO / "data" / "nba"
CACHE_DIR = REPO / "data" / "cache"
OUT_PLAYER = CACHE_DIR / "player_breakdown_features.parquet"
OUT_MATCHUP = CACHE_DIR / "matchup_breakdown_features.parquet"

MISC_FILE = DATA_NBA / "player_misc_2024-25.json"
SCORING_FILE = DATA_NBA / "player_scoring_2024-25.json"
MATCHUP_GLOB = str(DATA_NBA / "boxscore_matchups_004*.json")

SEASON = "2024-25"

# ── helpers ───────────────────────────────────────────────────────────────────

def _load_json(path: Path) -> dict:
    """Load JSON with UTF-8 encoding; return empty dict on failure."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        print(f"[WARN] could not load {path}: {exc}", file=sys.stderr)
        return {}


def _null_rate(series: pd.Series) -> float:
    return series.isna().mean()


# ── player misc ───────────────────────────────────────────────────────────────
MISC_COLS = {
    "pts_paint": "misc_pts_paint",
    "pts_off_tov": "misc_pts_off_TO",
    "pts_fast_break": "misc_pts_fast_break",
    "pts_2nd_chance": "misc_pts_2nd_chance",
    # opp defensive context
    "opp_pts_off_tov": "misc_opp_pts_off_TO",
    "opp_pts_paint": "misc_opp_pts_paint",
    "opp_pts_fast_break": "misc_opp_pts_fast_break",
}


def parse_misc(raw: dict) -> pd.DataFrame:
    rows = []
    for name, rec in raw.items():
        if not isinstance(rec, dict):
            continue
        pid = rec.get("player_id")
        if pid is None:
            continue
        row: dict = {"player_id": int(pid), "season": SEASON, "player_name": name}
        for src_key, dst_key in MISC_COLS.items():
            row[dst_key] = rec.get(src_key, np.nan)
        rows.append(row)
    return pd.DataFrame(rows)


# ── player scoring ─────────────────────────────────────────────────────────────
SCORING_COLS = {
    "pct_pts_3pt": "scoring_pct_pts_3pt",
    "pct_pts_paint": "scoring_pct_pts_paint",
    "pct_pts_ft": "scoring_pct_pts_ft",
    "pct_pts_mid_range": "scoring_pct_pts_mid_range",
    "pct_pts_fast_break": "scoring_pct_pts_fast_break",
    "pct_ast_2pt": "scoring_pct_ast_2pm",       # % of 2PM that were assisted
    "pct_unast_2pt": "scoring_pct_uast_2pm",     # % unassisted — self-creation proxy
    "pct_ast_3pt": "scoring_pct_ast_3pm",
    "pct_unast_3pt": "scoring_pct_uast_3pm",
    "pct_fga_2pt": "scoring_pct_fga_2pt",
    "pct_fga_3pt": "scoring_pct_fga_3pt",
}


def parse_scoring(raw: dict) -> pd.DataFrame:
    rows = []
    for name, rec in raw.items():
        if not isinstance(rec, dict):
            continue
        pid = rec.get("player_id")
        if pid is None:
            continue
        row: dict = {"player_id": int(pid), "season": SEASON}
        for src_key, dst_key in SCORING_COLS.items():
            row[dst_key] = rec.get(src_key, np.nan)
        rows.append(row)
    return pd.DataFrame(rows)


# ── boxscore matchups ─────────────────────────────────────────────────────────
# Key offensive-player stats from matchup grain.
# We aggregate per (off_player_id, game_id): total partial possessions, pct of
# defender time, FG attempted/made against the matched-up defender, and whether
# the defender switches were a factor.
MATCHUP_AGG_COLS = [
    "partialpossessions",
    "percentageoffensivetotaltime",
    "percentagedefendertotaltime",
    "matchupfieldgoalsattempted",
    "matchupfieldgoalsmade",
    "matchupthreepointersattempted",
    "matchupthreepointersmade",
    "playerpoints",
    "matchupassists",
    "matchupturnovers",
    "switcheson",
]


def parse_matchups(file_paths: list[str]) -> pd.DataFrame:
    frames = []
    for fp in file_paths:
        raw = _load_json(Path(fp))
        if not raw:
            continue
        game_id = str(raw.get("game_id", ""))
        matchups = raw.get("matchups", [])
        if not isinstance(matchups, list) or not matchups:
            continue
        df = pd.DataFrame(matchups)
        if df.empty:
            continue
        df["game_id"] = game_id
        # rename key columns up-front for clarity
        df = df.rename(columns={
            "personidoff": "player_id",
            "personiddef": "def_player_id",
        })
        # coerce numeric
        for col in MATCHUP_AGG_COLS:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        frames.append(df)

    if not frames:
        return pd.DataFrame()

    full = pd.concat(frames, ignore_index=True)

    # --- aggregate to (player_id, game_id) ---
    # primary defender = row with max partialpossessions per off-player per game
    agg_parts = (
        full.groupby(["player_id", "game_id"], as_index=False)
        .agg(
            matchup_total_partial_poss=("partialpossessions", "sum"),
            matchup_fga_vs_primary=("matchupfieldgoalsattempted", "sum"),
            matchup_fgm_vs_primary=("matchupfieldgoalsmade", "sum"),
            matchup_3pa_vs_primary=("matchupthreepointersattempted", "sum"),
            matchup_3pm_vs_primary=("matchupthreepointersmade", "sum"),
            matchup_pts_vs_primary=("playerpoints", "sum"),
            matchup_ast_vs_primary=("matchupassists", "sum"),
            matchup_tov_vs_primary=("matchupturnovers", "sum"),
            matchup_switches_drawn=("switcheson", "sum"),
            matchup_pct_off_time=("percentageoffensivetotaltime", "max"),
            matchup_n_defenders=("def_player_id", "nunique"),
        )
    )

    # derived: fg% vs primary defender
    agg_parts["matchup_fg_pct"] = np.where(
        agg_parts["matchup_fga_vs_primary"] > 0,
        agg_parts["matchup_fgm_vs_primary"] / agg_parts["matchup_fga_vs_primary"],
        np.nan,
    )

    return agg_parts


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # ---------- misc ----------
    misc_raw = _load_json(MISC_FILE)
    df_misc = parse_misc(misc_raw)
    print(f"misc rows: {len(df_misc)}")

    # ---------- scoring ----------
    scoring_raw = _load_json(SCORING_FILE)
    df_scoring = parse_scoring(scoring_raw)
    print(f"scoring rows: {len(df_scoring)}")

    # ---------- join misc + scoring on (player_id, season) ----------
    df_player = df_misc.merge(
        df_scoring, on=["player_id", "season"], how="outer"
    )
    print(f"merged player rows: {len(df_player)}")

    # ---------- write player parquet ----------
    df_player.to_parquet(OUT_PLAYER, index=False)
    print(f"Wrote {OUT_PLAYER}  ({len(df_player)} rows)")

    # ---------- null rates ----------
    feature_cols = [
        c for c in df_player.columns
        if c not in ("player_id", "season", "player_name")
    ]
    print("\n--- null rates (player breakdown) ---")
    for col in feature_cols:
        rate = _null_rate(df_player[col])
        flag = " *** HIGH NULL" if rate > 0.10 else ""
        print(f"  {col:<35s} {rate:.2%}{flag}")

    # ---------- sample row for Jayson Tatum (1628369) ----------
    tatum = df_player[df_player["player_id"] == 1628369]
    print("\n--- Tatum (1628369) sample ---")
    if not tatum.empty:
        for col, val in tatum.iloc[0].items():
            print(f"  {col}: {val}")
    else:
        print("  [not found]")

    # ---------- matchups ----------
    matchup_files = sorted(glob.glob(MATCHUP_GLOB))
    print(f"\nmatchup files found: {len(matchup_files)}")
    df_matchup = parse_matchups(matchup_files)

    if df_matchup.empty:
        print("[WARN] no matchup data — skipping matchup parquet")
    else:
        df_matchup.to_parquet(OUT_MATCHUP, index=False)
        print(f"Wrote {OUT_MATCHUP}  ({len(df_matchup)} rows)")
        print("\n--- null rates (matchup breakdown) ---")
        m_feat_cols = [c for c in df_matchup.columns if c not in ("player_id", "game_id")]
        for col in m_feat_cols:
            rate = _null_rate(df_matchup[col])
            flag = " *** HIGH NULL" if rate > 0.10 else ""
            print(f"  {col:<40s} {rate:.2%}{flag}")

        # sample for Tatum in matchups
        tatum_m = df_matchup[df_matchup["player_id"] == 1628369]
        print(f"\n--- Tatum matchup rows: {len(tatum_m)} ---")
        if not tatum_m.empty:
            print(tatum_m.to_string(index=False))


if __name__ == "__main__":
    main()
