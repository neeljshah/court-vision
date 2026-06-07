#!/usr/bin/env python3
"""build_player_cv_profiles.py — Aggregate features.csv files into
per-player-game CV profiles ready for prop_pergame consumption.

Reads `features.csv` from every completed game dir in
`nba-data-backup/tracking/` and produces:

  - `data/player_cv_per_game.parquet`  (one row per player×game)
  - `data/player_cv_per_player.parquet` (one row per player, season-aggregated)

These tables produce the same `cvb_*` signals as
`src/features/cv_feature_bridge.py` but at scale across the whole season,
so `scripts/prop_pergame_walk_forward.py` can consume them.

Schema (per-game parquet):
    game_id, player_id, player_name, team, n_frames, minutes_proxy,
    cvb_avg_defender_dist, cvb_avg_spacing, cvb_avg_velocity,
    cvb_fatigue_score, cvb_paint_time_pct, cvb_off_ball_dist,
    cvb_passes_per100, cvb_dribbles_per100, cvb_paint_pressure_opp,
    cvb_team_centroid_x, cvb_team_centroid_y,
    cvb_contested_shot_pct, cvb_off_ball_dist_std,
    cvb_velocity_q4_dropoff   (velocity decline Q1→Q4, fatigue proxy)

Sentinel handling matches `compute_spatial_features()`:
    defender_distance == 99.0  → NaN
    handler_isolation == 99.0  → NaN
    nearest_opponent  ≤ 0      → NaN

Usage:
    python scripts/build_player_cv_profiles.py
    python scripts/build_player_cv_profiles.py --season 2024-25
    python scripts/build_player_cv_profiles.py --games 0022500279,0022500280
    python scripts/build_player_cv_profiles.py --out data/cv_profiles.parquet
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Iterable, Optional

import numpy as np
import pandas as pd

BACKUP    = Path(r"C:\Users\neelj\nba-data-backup\tracking")
DEFAULT_OUT_PG     = Path("data/player_cv_per_game.parquet")
DEFAULT_OUT_PP     = Path("data/player_cv_per_player.parquet")
UNRESOLVED_PATH    = Path("data/cache/cv_unresolved_player_names.json")

SENTINEL_FT = 98.5     # any spatial value ≥ this is sentinel (99 / pixel 200)
MIN_FRAMES  = 60       # skip players with < 2 sec of tracking (noise)


# ---------------------------------------------------------------------------
# NBA personId resolver — maps tracker player_name -> static-dict personId.
#
# The tracker's `player_id` column is a synthetic per-game track ID (1-10),
# NOT the NBA personId. Downstream joins to props/box-score data require the
# real personId. This resolver uses `nba_api.stats.static.players` (in-memory
# dict, no API call) with diacritic stripping + suffix normalization.
# ---------------------------------------------------------------------------
_SUFFIX_RE = re.compile(r"\b(Jr\.?|Sr\.?|II|III|IV|V)\b\.?", flags=re.IGNORECASE)


def _norm_name(s: str) -> str:
    """Diacritic-strip + suffix-strip + casefold for fuzzy roster lookup."""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = _SUFFIX_RE.sub("", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s.casefold()


def _build_resolver() -> tuple[dict, callable]:
    """Return (cache_dict, resolve_fn) — cached name->personId lookup."""
    from nba_api.stats.static import players as _nba_players  # static, no API

    roster = _nba_players.get_players()
    # normalized full-name -> list of player dicts (handles homonyms via active)
    by_norm: dict[str, list[dict]] = {}
    for p in roster:
        by_norm.setdefault(_norm_name(p["full_name"]), []).append(p)

    cache: dict[str, Optional[int]] = {}

    def resolve(name: Optional[str]) -> Optional[int]:
        if name is None or (isinstance(name, float) and not np.isfinite(name)):
            return None
        s = str(name)
        if not s or "#?" in s:  # tracker placeholder like 'MIA#?'
            return None
        if s in cache:
            return cache[s]
        # 1) try nba_api's own regex matcher first (handles diacritics)
        try:
            res = _nba_players.find_players_by_full_name(s)
        except Exception:
            res = []
        # 2) fallback: normalized roster lookup
        if not res:
            res = by_norm.get(_norm_name(s), [])
        pid: Optional[int] = None
        if res:
            # prefer active player when multiple match
            active = [p for p in res if p.get("is_active")]
            chosen = active[0] if active else res[0]
            pid = int(chosen["id"])
        cache[s] = pid
        return pid

    return cache, resolve


def _list_games(season: Optional[str] = None,
                explicit: Optional[Iterable[str]] = None) -> list[str]:
    if explicit:
        return list(explicit)
    if not BACKUP.exists():
        return []
    out: list[str] = []
    for d in sorted(BACKUP.iterdir()):
        if not d.is_dir():
            continue
        gid = d.name
        if not gid.startswith("002"):  # NBA regular-season game prefix
            continue
        # Season filter: "2024-25" → gid starts with "0022500" or similar
        if season:
            season_code = "00225" if season == "2024-25" else None
            if season_code and not gid.startswith(season_code):
                continue
        # Accept any game with either features.csv OR tracking_data.csv —
        # aggregator falls back to raw tracking when features.csv missing.
        if (d / "features.csv").exists() or (d / "tracking_data.csv").exists():
            out.append(gid)
    return out


def _clean_spatial(s: pd.Series) -> pd.Series:
    """Replace sentinel values with NaN."""
    s = pd.to_numeric(s, errors="coerce")
    s = s.mask(s >= SENTINEL_FT)
    s = s.mask(s <= 0)
    return s


def _quarter_velocity_dropoff(df: pd.DataFrame) -> float:
    """Velocity decline Q1→Q4 — fatigue proxy.

    Returns mean velocity_ewma in last 25% of frames / mean in first 25%.
    Values < 1.0 = decline (typical for high-minute players),
    values ≥ 1.0 = constant or rising (energy player or low-volume).
    """
    if "velocity_ewma" not in df.columns or len(df) < 200:
        return np.nan
    v = pd.to_numeric(df["velocity_ewma"], errors="coerce")
    n = len(v)
    q1 = v.iloc[: n // 4].mean()
    q4 = v.iloc[3 * n // 4 :].mean()
    if not np.isfinite(q1) or q1 <= 0:
        return np.nan
    return float(q4 / q1)


def _aggregate_one_player(g: pd.DataFrame) -> dict:
    """Compute cvb_* aggregates for a single player's frames in one game."""
    out: dict = {"n_frames": len(g)}

    # Defender distance: prefer rolling 90 from features.csv, else raw nearest_opponent
    if "defender_dist_mean_90" in g.columns:
        out["cvb_avg_defender_dist"] = _clean_spatial(
            g["defender_dist_mean_90"]
        ).mean()
    elif "nearest_opponent" in g.columns:
        out["cvb_avg_defender_dist"] = _clean_spatial(
            g["nearest_opponent"]
        ).mean()

    # Spacing: prefer team_spacing_imputed, else raw team_spacing
    if "team_spacing_imputed" in g.columns:
        out["cvb_avg_spacing"] = pd.to_numeric(
            g["team_spacing_imputed"], errors="coerce"
        ).mean()
    elif "team_spacing" in g.columns:
        out["cvb_avg_spacing"] = pd.to_numeric(
            g["team_spacing"], errors="coerce"
        ).mean()

    # Off-ball distance: prefer rolling, else raw off_ball_distance
    if "off_ball_dist_mean_90" in g.columns:
        out["cvb_off_ball_dist"] = pd.to_numeric(
            g["off_ball_dist_mean_90"], errors="coerce"
        ).mean()
    elif "off_ball_distance" in g.columns:
        out["cvb_off_ball_dist"] = pd.to_numeric(
            g["off_ball_distance"], errors="coerce"
        ).mean()

    if "off_ball_dist_std_90" in g.columns:
        out["cvb_off_ball_dist_std"] = pd.to_numeric(
            g["off_ball_dist_std_90"], errors="coerce"
        ).mean()

    # Velocity: prefer EWMA, else raw velocity
    if "velocity_ewma" in g.columns:
        v = pd.to_numeric(g["velocity_ewma"], errors="coerce")
        out["cvb_avg_velocity"] = v.mean()
    elif "velocity" in g.columns:
        v = pd.to_numeric(g["velocity"], errors="coerce")
        out["cvb_avg_velocity"] = v.mean()
    # Prefer the homography-corrected paint pressure (recompute_paint_pressure.py
    # populates these from in_paint_fixed). Falls back to broken originals.
    if "paint_pressure_own_90_fixed" in g.columns:
        out["cvb_paint_pressure_own"] = pd.to_numeric(
            g["paint_pressure_own_90_fixed"], errors="coerce"
        ).mean()
    elif "paint_pressure_90" in g.columns:
        out["cvb_paint_pressure_own"] = pd.to_numeric(
            g["paint_pressure_90"], errors="coerce"
        ).mean()
    if "paint_pressure_opp_90_fixed" in g.columns:
        out["cvb_paint_pressure_opp"] = pd.to_numeric(
            g["paint_pressure_opp_90_fixed"], errors="coerce"
        ).mean()
    elif "paint_pressure_opp_90" in g.columns:
        out["cvb_paint_pressure_opp"] = pd.to_numeric(
            g["paint_pressure_opp_90"], errors="coerce"
        ).mean()
    # Fatigue score: prefer dist_traveled_90 rolling, else derive from velocity sum
    if "dist_traveled_90" in g.columns:
        out["cvb_fatigue_score"] = pd.to_numeric(
            g["dist_traveled_90"], errors="coerce"
        ).sum()
    elif "velocity" in g.columns:
        v = pd.to_numeric(g["velocity"], errors="coerce").fillna(0)
        # Approximate cumulative distance: sum of velocity (assume 1 frame = 1/30 sec)
        out["cvb_fatigue_score"] = float(v.sum() / 30.0)
    if "passes_per100" in g.columns:
        out["cvb_passes_per100"] = pd.to_numeric(
            g["passes_per100"], errors="coerce"
        ).mean()
    if "dribbles_per100" in g.columns:
        out["cvb_dribbles_per100"] = pd.to_numeric(
            g["dribbles_per100"], errors="coerce"
        ).mean()
    # team_centroid_x/y are emitted in PIXELS (range 0-3384 on g279) while
    # ft_x/ft_y are in feet (0-94). Skip until unified_pipeline.py emits
    # team centroid in feet — see Open Issues #12.
    # if "team_centroid_x" in g.columns: out["cvb_team_centroid_x"] = ...
    # paint_time_pct: prefer the homography-corrected columns produced by
    # scripts/fix_homography_offset.py (per-game empirical basket calibration).
    # Falls back to player-relative quintile when corrected file isn't present.
    if "in_paint_fixed" in g.columns:
        out["cvb_paint_time_pct"] = pd.to_numeric(
            g["in_paint_fixed"], errors="coerce"
        ).fillna(0).mean()
    if "near_basket_fixed" in g.columns:
        out["cvb_near_basket_pct"] = pd.to_numeric(
            g["near_basket_fixed"], errors="coerce"
        ).fillna(0).mean()
    if "dist_to_basket_ft_fixed" in g.columns:
        out["cvb_avg_dist_to_basket"] = pd.to_numeric(
            g["dist_to_basket_ft_fixed"], errors="coerce"
        ).mean()
    elif "dist_to_basket_ft" in g.columns and len(g) >= MIN_FRAMES:
        # Fallback: player-relative quintile (robust to homography offset
        # but doesn't measure absolute paint occupancy).
        dtb = pd.to_numeric(g["dist_to_basket_ft"], errors="coerce").dropna()
        if len(dtb) > 0:
            close_threshold = dtb.quantile(0.20)
            out["cvb_close_to_basket_pct"] = (dtb <= close_threshold).mean()
            out["cvb_avg_dist_to_basket"] = dtb.mean()
    if "contested_fraction_90" in g.columns:
        out["cvb_contested_shot_pct"] = pd.to_numeric(
            g["contested_fraction_90"], errors="coerce"
        ).mean()

    # Pose features (work on ~22 of 80 games; mean only of NONZERO contest_arm
    # frames, since 0 = pose-not-run-for-this-frame, not "arm down")
    if "contest_arm_angle" in g.columns:
        ca = pd.to_numeric(g["contest_arm_angle"], errors="coerce").fillna(0)
        ca_nz = ca[ca > 0]
        if len(ca_nz) > 0:
            out["cvb_contest_arm_mean"] = float(ca_nz.mean())
            out["cvb_contest_arm_nonzero_pct"] = float((ca > 0).mean())
    if "ankle_x" in g.columns:
        ax = pd.to_numeric(g["ankle_x"], errors="coerce")
        # Pose ran when ankle_x is set; coverage signals contested-shot data density
        out["cvb_pose_coverage_pct"] = float(ax.notna().mean())
    if "jump_detected" in g.columns:
        jd = pd.to_numeric(g["jump_detected"], errors="coerce").fillna(0)
        out["cvb_jump_frequency"] = float((jd > 0).mean())

    out["cvb_velocity_q4_dropoff"] = _quarter_velocity_dropoff(g)

    # Minutes proxy: n_frames / fps (assume 30 fps broadcast)
    out["minutes_proxy"] = round(len(g) / (30 * 60), 2)

    # Round CV signals for readability
    for k, v in out.items():
        if isinstance(v, float) and np.isfinite(v):
            out[k] = round(v, 4)

    return out


def _aggregate_one_game(game_id: str) -> pd.DataFrame:
    """Load per-game CSV, aggregate per player, return DataFrame.

    Prefers features.csv (full rolling-window data). Falls back to
    tracking_data.csv when features.csv is missing (e.g., feature
    engineering didn't complete on a large game).

    Merges in tracking_data_corrected.csv (from fix_homography_offset.py)
    on (frame, player_id) when present, so paint features benefit from
    per-game homography calibration.
    """
    feat_path  = BACKUP / game_id / "features.csv"
    track_path = BACKUP / game_id / "tracking_data.csv"
    fix_path   = BACKUP / game_id / "tracking_data_corrected.csv"

    src_path = feat_path if feat_path.exists() else track_path
    if not src_path.exists():
        return pd.DataFrame()

    try:
        df = pd.read_csv(src_path, low_memory=False)
    except Exception as e:
        print(f"  [{game_id}] load failed: {e}", file=sys.stderr)
        return pd.DataFrame()

    if df.empty:
        return pd.DataFrame()

    # Merge in homography-corrected columns when available
    if fix_path.exists():
        try:
            # Read the corrected file's full schema so we pick up any new
            # columns (paint_pressure_*_fixed added by recompute_paint_pressure)
            fix = pd.read_csv(fix_path, low_memory=False)
            fix_cols = [c for c in fix.columns
                        if c.endswith("_fixed") or c.endswith("_corrected")
                        or c in ("frame", "player_id")]
            df = df.merge(fix[fix_cols],
                          on=["frame", "player_id"], how="left")
        except Exception as e:
            print(f"  [{game_id}] homography fix merge failed: {e}",
                  file=sys.stderr)

    # Bug 12 fix (2026-05-28): features.csv stores team-label names (green#?, white#?)
    # which fail NBA name resolution, dropping cvb_passes_per100 / cvb_dribbles_per100
    # for resolved players.  When jersey_number + jersey_name_map.json are present,
    # build a player_id -> real_name map and patch player_name before groupby so the
    # per-player aggregates (including passes_per100 / dribbles_per100) survive under
    # the resolved NBA name.
    if (
        "player_name" in df.columns
        and "jersey_number" in df.columns
        and df["player_name"].astype(str).str.contains(r"^(green|white)#", regex=True).any()
    ):
        jmap_path = BACKUP / game_id / "jersey_name_map.json"
        if jmap_path.exists():
            try:
                import json as _json
                with open(jmap_path, encoding="utf-8") as _jf:
                    _jdata = _json.load(_jf)
                # flat dict: {jersey_str: real_name}
                _flat = _jdata.get("flat", {}) if isinstance(_jdata, dict) else {}
                if _flat:
                    # Build player_id -> real_name via mode jersey_number per player_id
                    _jnum_mode = (
                        df.groupby("player_id")["jersey_number"]
                        .agg(lambda s: s.mode().iat[0] if not s.mode().empty else None)
                    )
                    _pid_to_name = {}
                    for _pid, _jnum in _jnum_mode.items():
                        if _jnum is None:
                            continue
                        _real = _flat.get(str(int(_jnum))) if _jnum == _jnum else None
                        if _real:
                            _pid_to_name[_pid] = _real
                    if _pid_to_name:
                        df["player_name"] = df.apply(
                            lambda r: _pid_to_name.get(r["player_id"], r["player_name"]),
                            axis=1,
                        )
            except Exception as _e:
                print(f"  [{game_id}] jersey name patch failed: {_e}", file=sys.stderr)

    # Group keys: prefer (player_id, team), fall back to player_name
    keys = []
    for k in ("player_id", "player_name", "team"):
        if k in df.columns:
            keys.append(k)
    if not keys:
        return pd.DataFrame()

    rows = []
    for grp_key, g in df.groupby(keys, dropna=False):
        if len(g) < MIN_FRAMES:
            continue
        row = {"game_id": game_id}
        if isinstance(grp_key, tuple):
            for k, v in zip(keys, grp_key):
                row[k] = v
        else:
            row[keys[0]] = grp_key
        row.update(_aggregate_one_player(g))
        rows.append(row)

    return pd.DataFrame(rows)


def build_per_game(games: list[str], verbose: bool = True) -> pd.DataFrame:
    parts = []
    for gid in games:
        df = _aggregate_one_game(gid)
        if verbose:
            print(f"  [{gid}] {len(df)} player rows aggregated")
        if not df.empty:
            parts.append(df)
    if not parts:
        return pd.DataFrame()
    out = pd.concat(parts, ignore_index=True)

    # Attach REAL NBA personId via static-dict resolver. The pre-existing
    # `player_id` column is the tracker's synthetic 1-10 track ID and is
    # preserved unchanged for downstream code that already depends on it.
    if "player_name" in out.columns:
        _, resolve = _build_resolver()
        out["nba_player_id"] = out["player_name"].map(resolve).astype("Int64")
    return out


def build_per_player(per_game: pd.DataFrame) -> pd.DataFrame:
    """Season-level aggregate from per-game table."""
    if per_game.empty:
        return pd.DataFrame()
    # Prefer NBA personId for grouping when present (collapses diacritic
    # variants of the same player into one row). Falls back to player_name
    # then synthetic track id.
    if "nba_player_id" in per_game.columns:
        grp_key = "nba_player_id"
    elif "player_name" in per_game.columns:
        grp_key = "player_name"
    else:
        grp_key = "player_id"
    if grp_key not in per_game.columns:
        return pd.DataFrame()

    cvb_cols = [c for c in per_game.columns if c.startswith("cvb_")]
    agg_spec = {"game_id": "nunique", "n_frames": "sum", "minutes_proxy": "sum"}
    for c in cvb_cols:
        agg_spec[c] = "mean"
    if "team" in per_game.columns:
        agg_spec["team"] = lambda s: s.mode().iat[0] if not s.mode().empty else ""
    if "player_name" in per_game.columns and grp_key != "player_name":
        agg_spec["player_name"] = lambda s: s.mode().iat[0] if not s.mode().empty else ""

    g = per_game.groupby(grp_key, dropna=False).agg(agg_spec).reset_index()
    g = g.rename(columns={"game_id": "n_games"})
    return g


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", default=None,
                    help="Season filter (e.g. 2024-25); inferred from game_id prefix")
    ap.add_argument("--games", default=None,
                    help="Comma-separated game IDs (overrides season)")
    ap.add_argument("--all", action="store_true",
                    help="Aggregate every game dir under nba-data-backup/tracking/")
    ap.add_argument("--out-per-game", type=Path, default=DEFAULT_OUT_PG)
    ap.add_argument("--out-per-player", type=Path, default=DEFAULT_OUT_PP)
    ap.add_argument("--no-write", action="store_true",
                    help="Don't write parquets, just print summary")
    args = ap.parse_args()

    if args.all:
        explicit = None  # _list_games with no season returns all
    else:
        explicit = [g.strip() for g in args.games.split(",")] if args.games else None
    games = _list_games(season=args.season, explicit=explicit)
    if not games:
        print("No games found.", file=sys.stderr)
        return 1
    print(f"Aggregating {len(games)} game(s)...")

    per_game = build_per_game(games)
    if per_game.empty:
        print("No data aggregated.", file=sys.stderr)
        return 2
    print(f"\nPer-game table: {per_game.shape}")

    # NBA personId resolution report + unresolved-name sidecar
    if "nba_player_id" in per_game.columns and "player_name" in per_game.columns:
        names = per_game[["player_name", "nba_player_id"]].drop_duplicates("player_name")
        real_names = names[~names["player_name"].astype(str).str.contains("#\\?", na=False)]
        n_total = len(real_names)
        n_res = int(real_names["nba_player_id"].notna().sum())
        n_unres = n_total - n_res
        print(f"\nNBA personId resolver: {n_res}/{n_total} unique names resolved "
              f"({100.0*n_res/max(n_total,1):.1f}%)")
        unresolved = sorted(
            real_names.loc[real_names["nba_player_id"].isna(), "player_name"]
            .dropna().astype(str).unique().tolist()
        )
        if unresolved:
            UNRESOLVED_PATH.parent.mkdir(parents=True, exist_ok=True)
            UNRESOLVED_PATH.write_text(
                json.dumps({"count": len(unresolved), "names": unresolved},
                           ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"  Unresolved sidecar: {UNRESOLVED_PATH} ({len(unresolved)} names)")

    cvb_cols = [c for c in per_game.columns if c.startswith("cvb_")]
    if cvb_cols:
        print(f"  cvb_* columns ({len(cvb_cols)}): {cvb_cols}")
        print("\n  Summary stats:")
        print(per_game[cvb_cols].describe().T.round(3).to_string())

    per_player = build_per_player(per_game)
    print(f"\nPer-player table: {per_player.shape}")
    if not per_player.empty and "player_name" in per_player.columns:
        sample_cols = ["player_name", "n_games", "minutes_proxy"] + cvb_cols[:5]
        sample_cols = [c for c in sample_cols if c in per_player.columns]
        print("\n  Top 10 by minutes (sample):")
        print(per_player.nlargest(10, "minutes_proxy")[sample_cols]
              .round(2).to_string(index=False))

    if not args.no_write:
        args.out_per_game.parent.mkdir(parents=True, exist_ok=True)
        per_game.to_parquet(args.out_per_game, index=False)
        per_player.to_parquet(args.out_per_player, index=False)
        print(f"\nWrote {args.out_per_game} and {args.out_per_player}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
