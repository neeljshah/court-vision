"""build_cv_pace_features.py — INT-118: Extract per-game pace from CV possessions.csv.

Pace formula (per-team per-game):
    cv_pace = (n_possessions / sum_duration_sec) * 2880   [2880 = 48min * 60sec]

Outputs:
    data/intelligence/cv_pace_per_game.parquet
    data/intelligence/cv_pace_features_sidecar.parquet
"""
from __future__ import annotations

import json
import os
import sys
import warnings
from datetime import datetime
from pathlib import Path

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

PROJECT_DIR = Path(__file__).resolve().parent.parent
TRACKING_ROOT = PROJECT_DIR / "data" / "tracking"
NBA_DATA_DIR = PROJECT_DIR / "data" / "nba"
INTEL_DIR = PROJECT_DIR / "data" / "intelligence"
INTEL_DIR.mkdir(parents=True, exist_ok=True)

OUT_GAME = INTEL_DIR / "cv_pace_per_game.parquet"
OUT_SIDECAR = INTEL_DIR / "cv_pace_features_sidecar.parquet"

PACE_SCALE = 2880.0  # 48 * 60

# Possession duration filter: exclude dead-time outliers (timeouts, halftime spans)
# NBA shot clock is 24s; with some buffer allow up to 40s per possession
POSS_DUR_MIN_SEC = 1.0
POSS_DUR_MAX_SEC = 40.0


# ---------------------------------------------------------------------------
# Step 1: Build game_id -> (game_date, home_team, away_team) map
# ---------------------------------------------------------------------------
def _build_game_map() -> dict:
    """Load season_games_*.json to get game_id -> date + team info."""
    game_map: dict = {}
    for fn in sorted(NBA_DATA_DIR.iterdir()):
        if not fn.name.startswith("season_games_"):
            continue
        with open(fn) as f:
            data = json.load(f)
        rows = data.get("rows", data) if isinstance(data, dict) else data
        for r in rows:
            gid = str(r.get("game_id", ""))
            if gid:
                game_map[gid] = {
                    "game_date": str(r.get("game_date", ""))[:10],
                    "home_team": r.get("home_team", ""),
                    "away_team": r.get("away_team", ""),
                    "home_pace": r.get("home_pace"),
                    "away_pace": r.get("away_pace"),
                }
    print(f"  Loaded {len(game_map)} games from season_games_*.json")
    return game_map


# ---------------------------------------------------------------------------
# Step 2: Parse possessions.csv or fall back to tracking_data.csv
# ---------------------------------------------------------------------------
def _parse_game_pace(game_dir: Path) -> list[dict]:
    """Return list of {game_id, team, n_poss, sum_duration_sec, cv_pace} per team."""
    game_id = game_dir.name
    poss_path = game_dir / "possessions.csv"
    track_path = game_dir / "tracking_data.csv"

    records = []

    # Primary: possessions.csv
    if poss_path.exists() and poss_path.stat().st_size > 100:
        try:
            df = pd.read_csv(poss_path)
            if "possession_id" in df.columns and "duration_sec" in df.columns and "team" in df.columns:
                df = df.dropna(subset=["duration_sec", "team"])
                # Filter: exclude dead-time outliers (halftime spans, long timeouts)
                # NBA shot clock = 24s; allow up to 40s with small buffer
                df = df[(df["duration_sec"] >= POSS_DUR_MIN_SEC) &
                        (df["duration_sec"] <= POSS_DUR_MAX_SEC)]
                if len(df) < 6:
                    return records  # not enough valid possessions
                # Denominator = total filtered possession time across BOTH teams
                # (captures proportional time share; removes dead time)
                total_dur = df["duration_sec"].sum()
                for team, grp in df.groupby("team"):
                    n_poss = len(grp)
                    if n_poss >= 3 and total_dur > 0:
                        # pace = per-team possessions / total possession clock * 2880
                        pace = (n_poss / total_dur) * PACE_SCALE
                        records.append({
                            "game_id": game_id,
                            "team_raw": str(team),
                            "n_poss": n_poss,
                            "sum_duration_sec": float(total_dur),
                            "cv_pace": float(pace),
                            "source": "possessions_csv",
                        })
                if records:
                    return records
        except Exception as e:
            print(f"    WARN: possessions.csv parse error in {game_id}: {e}")

    # Fallback: tracking_data.csv grouped by team + possession_id
    if track_path.exists() and track_path.stat().st_size > 1000:
        try:
            df = pd.read_csv(track_path, usecols=lambda c: c in [
                "team", "possession_id", "possession_duration_sec",
                "possession_duration", "frame",
            ])
            if "possession_id" not in df.columns or "team" not in df.columns:
                return []
            # Use possession_duration_sec if present, else estimate from frame count * 1/60
            dur_col = "possession_duration_sec" if "possession_duration_sec" in df.columns else None
            for team, grp in df.groupby("team"):
                poss_groups = grp.groupby("possession_id")
                n_poss = poss_groups.ngroups
                if dur_col:
                    sum_dur = poss_groups[dur_col].max().sum()
                else:
                    # frames at ~10fps
                    sum_dur = len(grp) / 10.0
                if sum_dur > 0 and n_poss >= 3:
                    pace = (n_poss / sum_dur) * PACE_SCALE
                    records.append({
                        "game_id": game_id,
                        "team_raw": str(team),
                        "n_poss": n_poss,
                        "sum_duration_sec": float(sum_dur),
                        "cv_pace": float(pace),
                        "source": "tracking_data_fallback",
                    })
        except Exception as e:
            print(f"    WARN: tracking_data.csv fallback error in {game_id}: {e}")

    return records


# ---------------------------------------------------------------------------
# Step 3: Resolve team_raw -> team_abbrev using game_map
# ---------------------------------------------------------------------------
def _resolve_team_abbrev(df_game: pd.DataFrame, game_map: dict) -> pd.DataFrame:
    """Add team_abbrev column by matching home/away team from game_map.

    CV uses jersey colors ('green', 'white', 'red', etc.) not abbrevs.
    We assign: the two unique team_raw values per game map to home/away
    (arbitrary — doesn't affect pace metric itself).
    """
    rows = []
    for game_id, grp in df_game.groupby("game_id"):
        info = game_map.get(str(game_id), {})
        home = info.get("home_team", "")
        away = info.get("away_team", "")
        teams_raw = grp["team_raw"].unique().tolist()

        # We need to match both teams — assign alpha-sorted teams to raw color-sorted teams
        teams_raw_sorted = sorted(teams_raw)
        abbrevs_sorted = sorted([t for t in [home, away] if t])

        mapping = {}
        if len(teams_raw_sorted) == 2 and len(abbrevs_sorted) >= 2:
            mapping = dict(zip(teams_raw_sorted, abbrevs_sorted))
        elif len(teams_raw_sorted) == 1 and len(abbrevs_sorted) >= 1:
            mapping = {teams_raw_sorted[0]: abbrevs_sorted[0]}

        for _, row in grp.iterrows():
            r = row.to_dict()
            r["team_abbrev"] = mapping.get(row["team_raw"], row["team_raw"])
            r["game_date"] = info.get("game_date", "")
            r["home_team"] = home
            r["away_team"] = away
            r["home_pace_api"] = info.get("home_pace")
            r["away_pace_api"] = info.get("away_pace")
            rows.append(r)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Step 4: Player-grain sidecar — rolling L5/L10 per team
# ---------------------------------------------------------------------------
def _build_sidecar(df_pace: pd.DataFrame) -> pd.DataFrame:
    """Expand pace to player-grain via gamelog team membership and compute rolling L5/L10."""
    # Load all gamelogs to get player -> team -> game_date mapping
    gamelog_dir = NBA_DATA_DIR
    player_game_records = []
    for fn in gamelog_dir.iterdir():
        if not fn.name.startswith("gamelog_"):
            continue
        try:
            with open(fn) as f:
                rows = json.load(f)
            if not isinstance(rows, list) or not rows:
                continue
            # Extract player_id from filename: gamelog_<player_id>_<season>.json
            parts = fn.stem.split("_")
            if len(parts) < 2:
                continue
            pid = int(parts[1])
            for r in rows:
                gd_raw = str(r.get("GAME_DATE", ""))
                matchup = str(r.get("MATCHUP", ""))
                if not gd_raw or not matchup:
                    continue
                # Parse 'Apr 02, 2025' -> '2025-04-02'
                try:
                    gd = datetime.strptime(gd_raw, "%b %d, %Y").strftime("%Y-%m-%d")
                except ValueError:
                    # fallback: already ISO format or partial
                    gd = gd_raw[:10]
                player_game_records.append({
                    "player_id": pid,
                    "game_date": gd,
                    "matchup": matchup,
                })
        except Exception:
            continue

    if not player_game_records:
        print("  WARN: No gamelog records found — sidecar will be empty")
        return pd.DataFrame()

    pg_df = pd.DataFrame(player_game_records).drop_duplicates(["player_id", "game_date"])
    print(f"  Loaded {len(pg_df)} player-game records from gamelogs ({pg_df['player_id'].nunique()} players)")

    # Extract home/away team from matchup (e.g., "BOS vs. NYK" or "BOS @ NYK")
    def _parse_matchup(matchup: str):
        """Return (own_team, opp_team) from matchup string."""
        m = matchup.strip()
        if " vs. " in m:
            parts = m.split(" vs. ")
            return parts[0].strip(), parts[1].strip()
        elif " @ " in m:
            parts = m.split(" @ ")
            return parts[0].strip(), parts[1].strip()
        return m[:3], ""

    pg_df[["own_team", "opp_team"]] = pd.DataFrame(
        pg_df["matchup"].apply(_parse_matchup).tolist(), index=pg_df.index
    )

    # Build team-game pace lookup: (team_abbrev, game_date) -> cv_pace
    pace_lookup = (
        df_pace[["team_abbrev", "game_date", "cv_pace"]]
        .dropna(subset=["game_date"])
        .set_index(["team_abbrev", "game_date"])["cv_pace"]
        .to_dict()
    )

    # For each player-game, look up team and opp pace on that game_date
    pg_df = pg_df.sort_values(["player_id", "game_date"]).reset_index(drop=True)

    def _rolling_pace(player_df: pd.DataFrame, team_col: str, window: int, pace_lkp: dict):
        """Strict-as-of rolling: for each row, use L{window} prior games' pace (exclude current)."""
        results = []
        for i, row in enumerate(player_df.itertuples()):
            prior = player_df.iloc[:i]
            vals = []
            for pr in prior.itertuples():
                key = (getattr(pr, team_col), pr.game_date)
                v = pace_lkp.get(key)
                if v is not None:
                    vals.append(v)
            if len(vals) >= 1:
                results.append(float(np.mean(vals[-window:])))
            else:
                results.append(np.nan)
        return results

    # Compute per-team career mean/std for matchup_z
    team_career = {}
    for team in df_pace["team_abbrev"].dropna().unique():
        vals = df_pace[df_pace["team_abbrev"] == team]["cv_pace"].dropna().values
        if len(vals) >= 3:
            team_career[team] = (float(np.mean(vals)), max(float(np.std(vals)), 0.01))

    sidecar_rows = []
    grouped = pg_df.groupby("player_id", sort=False)
    total_players = len(grouped)
    for i, (pid, pgrp) in enumerate(grouped):
        if i % 500 == 0:
            print(f"    sidecar: {i}/{total_players} players ...", flush=True)
        pgrp = pgrp.sort_values("game_date").reset_index(drop=True)

        team_l5 = _rolling_pace(pgrp, "own_team", 5, pace_lookup)
        team_l10 = _rolling_pace(pgrp, "own_team", 10, pace_lookup)
        opp_l5 = _rolling_pace(pgrp, "opp_team", 5, pace_lookup)
        opp_l10 = _rolling_pace(pgrp, "opp_team", 10, pace_lookup)

        for idx, row in enumerate(pgrp.itertuples()):
            tl5 = team_l5[idx]
            ol5 = opp_l5[idx]
            team = row.own_team
            cm, cs = team_career.get(team, (np.nan, np.nan))

            if not np.isnan(tl5) and not np.isnan(ol5) and not np.isnan(cm):
                matchup_z = ((tl5 + ol5) / 2.0 - cm) / cs
            else:
                matchup_z = np.nan

            sidecar_rows.append({
                "player_id": int(pid),
                "game_date": row.game_date,
                "cv_pace_team_l5": tl5,
                "cv_pace_team_l10": team_l10[idx],
                "cv_pace_opp_l5": ol5,
                "cv_pace_opp_l10": opp_l10[idx],
                "cv_pace_matchup_z": matchup_z,
            })

    sidecar_df = pd.DataFrame(sidecar_rows)
    print(f"  Sidecar built: {len(sidecar_df)} rows, {sidecar_df['player_id'].nunique()} players")
    return sidecar_df


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("INT-118: build_cv_pace_features.py")
    print("=" * 60)

    game_map = _build_game_map()

    tracking_dirs = sorted([
        d for d in TRACKING_ROOT.iterdir() if d.is_dir()
    ])
    print(f"  Scanning {len(tracking_dirs)} tracking dirs ...")

    all_records = []
    n_empty = 0
    for d in tracking_dirs:
        recs = _parse_game_pace(d)
        if recs:
            all_records.extend(recs)
        else:
            n_empty += 1

    print(f"  Parsed {len(all_records)} team-game records from {len(tracking_dirs)-n_empty} dirs "
          f"({n_empty} empty/failed)")

    if not all_records:
        print("BLOCKED: No pace records extracted — check possessions.csv presence.")
        sys.exit(1)

    df_raw = pd.DataFrame(all_records)

    # Sanity check: pace should be in [80, 130]
    median_pace = float(df_raw["cv_pace"].median())
    p25 = float(df_raw["cv_pace"].quantile(0.25))
    p75 = float(df_raw["cv_pace"].quantile(0.75))
    print(f"\n  PACE DISTRIBUTION: median={median_pace:.1f}  p25={p25:.1f}  p75={p75:.1f}")
    print(f"  Range: [{df_raw['cv_pace'].min():.1f}, {df_raw['cv_pace'].max():.1f}]")

    if not (80 <= median_pace <= 130):
        print(f"\nHALT: median cv_pace={median_pace:.1f} is outside [80, 130] sanity band.")
        print("  This indicates possession over/under-segmentation. Aborting.")
        sys.exit(2)

    print("  [PASS] Sanity band [80, 130] — median pace OK")

    # Resolve team abbrevs and game dates
    df_resolved = _resolve_team_abbrev(df_raw, game_map)

    # Save per-game parquet
    cols_out = ["game_id", "team_abbrev", "cv_pace", "n_poss", "sum_duration_sec",
                "game_date", "home_team", "away_team", "source"]
    df_out = df_resolved[[c for c in cols_out if c in df_resolved.columns]].copy()
    df_out.to_parquet(OUT_GAME, index=False)
    print(f"\n  Written: {OUT_GAME}  ({len(df_out)} rows)")

    # Step 4: Build sidecar
    print("\n  Building player-grain sidecar ...")
    sidecar = _build_sidecar(df_out)

    if sidecar.empty:
        print("  WARN: Sidecar is empty — cannot proceed to G1 gate.")
    else:
        sidecar.to_parquet(OUT_SIDECAR, index=False)
        print(f"  Written: {OUT_SIDECAR}  ({len(sidecar)} rows)")

        # G1: coverage in holdout-like slice (last 30% of dates)
        sidecar_sorted = sidecar.sort_values("game_date")
        n_total = len(sidecar_sorted)
        fold4_slice = sidecar_sorted.iloc[int(n_total * 0.7):]
        g1_cov = fold4_slice["cv_pace_team_l5"].notna().mean()
        print(f"\n  G1 COVERAGE (fold-4 slice): {g1_cov:.3f} ({g1_cov*100:.1f}%)")
        if g1_cov >= 0.30:
            print("  [G1 PASS]")
        else:
            print("  [G1 FAIL] Coverage < 30% — signal will be NaN-heavy in holdout")

        # G2: orthogonality vs NBA-API pace (use per-game parquet with home_pace_api/away_pace_api)
        df_g2 = df_resolved.copy()
        df_g2 = df_g2.dropna(subset=["cv_pace"])
        # Pair cv_pace with api_pace (home or away depending on position)
        df_g2["api_pace"] = np.where(
            df_g2["team_abbrev"] == df_g2["home_team"],
            df_g2["home_pace_api"],
            df_g2["away_pace_api"],
        )
        df_g2 = df_g2.dropna(subset=["api_pace", "cv_pace"])
        if len(df_g2) >= 50:
            corr = float(df_g2["cv_pace"].corr(df_g2["api_pace"].astype(float)))
            print(f"\n  G2 ORTHOGONALITY: corr(cv_pace, api_pace)={corr:.4f}")
            if abs(corr) < 0.95:
                print("  [G2 PASS] Not redundant with NBA-API pace")
            else:
                print("  [G2 FAIL] SHIP-DEFER: |r| >= 0.95 — high redundancy with NBA-API pace")
        else:
            print(f"\n  G2: Insufficient overlap for correlation ({len(df_g2)} rows) — skipping")

    print("\nDone.")


if __name__ == "__main__":
    main()
