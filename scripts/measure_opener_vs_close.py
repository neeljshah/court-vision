"""
measure_opener_vs_close.py
--------------------------
Measures whether betting OPENING lines beats betting CLOSING lines for the
deployed CourtVision pregame model.

THESIS: The model uses stale pre-news features that approximate the OPENER.
If it loses to closes (because news moves lines) it may still beat openers.
The KEY number is opener_ROI - close_ROI (positive = freshness edge is real).

DATA SOURCES
------------
- data/live/<nba_gid>_pregame.json  -- deployed model predictions (keyed by NBA player_id)
- data/lines/<date>_<book>.csv      -- timestamped lines (captured_at, book, player_name, stat, line, over_price, under_price, start_time)
- data/lines/snapshots/             -- named close/opener snapshots for specific games
- data/cache/cv_fix/leaguegamelog_*.parquet -- actuals (PLAYER_ID, PLAYER_NAME, PTS/REB/AST/FG3M)

JOIN STRATEGY
-------------
- pregame.json key = NBA player_id (7-digit)
- lines CSVs: player_id column is BOOK-SPECIFIC (not NBA id), unreliable
- Join channel: player_name (normalized lowercase+strip)
- One game per day per player, so name collision across games is rare

OPENER / CLOSE DEFINITION
--------------------------
Per (player_name, stat, book, game):
  OPENER = earliest captured_at per group (strictly pre-game)
  CLOSE  = latest captured_at where captured_at < start_time per group
If a snapshot file exists for a game it is used preferentially (already filtered).

CLV (Close Line Value)
----------------------
For an OVER bet: CLV_pts = open_line - close_line  (positive = line went UP = we had softer number)
For an UNDER bet: CLV_pts = close_line - open_line  (positive = line went DOWN = we had higher number)
beat_close% = fraction of bets where CLV_pts > 0

HONEST FRAMING
--------------
Current corpus is ~2 games (0042500315 + 0042500316). Results are DIRECTIONAL only.
n << any statistical bar. Do not claim an edge from this output.
"""

import json
import os
import sys
import warnings
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO = Path(__file__).parent.parent
LIVE_DIR = REPO / "data" / "live"
LINES_DIR = REPO / "data" / "lines"
SNAP_DIR = LINES_DIR / "snapshots"
GL_PLAYOFF = REPO / "data" / "cache" / "cv_fix" / "leaguegamelog_playoffs.parquet"
GL_REG = REPO / "data" / "cache" / "cv_fix" / "leaguegamelog_regular_season.parquet"

# Stats the model predicts + props markets carry
GRADEABLE_STATS = ["pts", "reb", "ast", "fg3m"]
# Gamelog column names map
STAT_TO_GL_COL = {"pts": "PTS", "reb": "REB", "ast": "AST", "fg3m": "FG3M"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_name(name: str) -> str:
    """Lowercase, strip, collapse whitespace."""
    return " ".join(str(name).strip().lower().split())


def american_to_decimal(price: float) -> float | None:
    """Convert American odds to decimal multiplier. Returns None if invalid."""
    p = float(price)
    if abs(p) < 100:
        return None  # per spec: drop rows |odds| < 100
    if p > 0:
        return (p / 100.0) + 1.0
    else:
        return (100.0 / abs(p)) + 1.0


def settle_bet(model_pred: float, line: float, over_price: float, under_price: float,
               actual: float) -> tuple[str | None, float | None]:
    """
    Determine bet side and ROI per unit staked.
    Returns (bet_side, roi) or (None, None) if invalid odds.
    ROI = decimal_odds - 1 on win, -1 on loss, 0 on push.
    """
    if model_pred == line:
        return None, None  # no bet when model == line exactly
    bet_side = "OVER" if model_pred > line else "UNDER"
    odds = over_price if bet_side == "OVER" else under_price
    dec = american_to_decimal(odds)
    if dec is None:
        return None, None
    if actual == line:
        return bet_side, 0.0  # push
    won = (bet_side == "OVER" and actual > line) or (bet_side == "UNDER" and actual < line)
    return bet_side, (dec - 1.0) if won else -1.0


def clv_points(bet_side: str, open_line: float, close_line: float) -> float:
    """
    Line-point CLV: how many points better was the open vs close?
    Positive = we had a softer number (opener was friendlier than the close).
    OVER bet: positive if open_line < close_line (line rose, we were in early at low price)
    UNDER bet: positive if open_line > close_line (line fell, we were in early at high price)
    """
    if bet_side == "OVER":
        return close_line - open_line  # positive when close moved UP
    else:
        return open_line - close_line  # positive when close moved DOWN


# ---------------------------------------------------------------------------
# Load player name <-> NBA ID mapping from gamelogs
# ---------------------------------------------------------------------------

def _load_name_id_map() -> dict[str, int]:
    """Return {normalized_player_name: nba_player_id}."""
    dfs = []
    for path in [GL_PLAYOFF, GL_REG]:
        if path.exists():
            dfs.append(pd.read_parquet(path)[["PLAYER_ID", "PLAYER_NAME"]])
    if not dfs:
        return {}
    combined = pd.concat(dfs, ignore_index=True).drop_duplicates()
    out = {}
    for _, row in combined.iterrows():
        key = _normalize_name(row["PLAYER_NAME"])
        out[key] = int(row["PLAYER_ID"])
    return out


def _load_id_name_map() -> dict[int, str]:
    """Return {nba_player_id: canonical_player_name}."""
    dfs = []
    for path in [GL_PLAYOFF, GL_REG]:
        if path.exists():
            dfs.append(pd.read_parquet(path)[["PLAYER_ID", "PLAYER_NAME"]])
    if not dfs:
        return {}
    combined = pd.concat(dfs, ignore_index=True).drop_duplicates()
    return dict(zip(combined["PLAYER_ID"].astype(int), combined["PLAYER_NAME"]))


# ---------------------------------------------------------------------------
# Load pregame predictions
# ---------------------------------------------------------------------------

def load_pregame_preds() -> dict[str, dict]:
    """
    Returns {nba_gid: {nba_player_id_int: {stat: value}}}
    Only loads files matching *_pregame.json.
    """
    result = {}
    for path in LIVE_DIR.glob("*_pregame.json"):
        gid = path.stem.replace("_pregame", "")
        try:
            with open(path, encoding="utf-8") as f:
                raw = json.load(f)
            # Keys are string NBA player IDs
            result[gid] = {int(k): v for k, v in raw.items()}
        except Exception as e:
            print(f"  [WARN] Could not load {path.name}: {e}", file=sys.stderr)
    return result


# ---------------------------------------------------------------------------
# Load actuals from gamelogs
# ---------------------------------------------------------------------------

def load_actuals() -> pd.DataFrame:
    """
    Return DataFrame with columns:
      game_id, nba_player_id, player_name, pts, reb, ast, fg3m
    """
    dfs = []
    for path in [GL_PLAYOFF, GL_REG]:
        if path.exists():
            df = pd.read_parquet(path)
            df["game_id"] = df["GAME_ID"].astype(str)
            df = df[["game_id", "PLAYER_ID", "PLAYER_NAME", "PTS", "REB", "AST", "FG3M"]].copy()
            df.columns = ["game_id", "nba_player_id", "player_name", "pts", "reb", "ast", "fg3m"]
            df["nba_player_id"] = df["nba_player_id"].astype(int)
            dfs.append(df)
    if not dfs:
        return pd.DataFrame()
    return pd.concat(dfs, ignore_index=True).drop_duplicates(subset=["game_id", "nba_player_id"])


# ---------------------------------------------------------------------------
# Load lines from snapshot files (preferred) or raw CSVs
# ---------------------------------------------------------------------------

def _read_lines_csv(path: Path) -> pd.DataFrame | None:
    """Read a lines CSV robustly. Returns None on failure."""
    try:
        df = pd.read_csv(path, on_bad_lines="skip")
    except Exception:
        return None
    required = {"player_name", "stat", "line", "over_price", "under_price", "captured_at"}
    if not required.issubset(df.columns):
        return None
    df["player_name_norm"] = df["player_name"].apply(_normalize_name)
    df["captured_at"] = pd.to_datetime(df["captured_at"], utc=True, errors="coerce")
    df["line"] = pd.to_numeric(df["line"], errors="coerce")
    df["over_price"] = pd.to_numeric(df["over_price"], errors="coerce")
    df["under_price"] = pd.to_numeric(df["under_price"], errors="coerce")
    df = df.dropna(subset=["captured_at", "line", "over_price", "under_price"])
    df["stat"] = df["stat"].str.lower().str.strip()
    return df


def load_snapshot_lines(gid: str) -> pd.DataFrame | None:
    """
    For a given game_id, try to load a close snapshot from data/lines/snapshots/.
    The snapshot already covers the full opener-to-close timeline (multiple captured_at).
    Return DataFrame or None.
    """
    patterns = [f"{gid}_close_*.csv", f"{gid}_pre_close*.csv"]
    candidates = []
    for pat in patterns:
        candidates.extend(sorted(SNAP_DIR.glob(pat)))
    if not candidates:
        return None
    # Prefer the 'close_' file with latest timestamp in filename (most coverage)
    close_files = [f for f in candidates if "_close_" in f.name and "_mainline_" not in f.name]
    if close_files:
        chosen = max(close_files, key=lambda p: p.name)
    else:
        chosen = candidates[0]
    df = _read_lines_csv(chosen)
    if df is not None:
        df["source_file"] = chosen.name
    return df


def load_raw_lines_for_game(game_date_str: str, start_time_utc: datetime) -> pd.DataFrame | None:
    """
    Load raw line CSVs from data/lines/ for a game identified by its start_time.
    Looks at files from the day before and day of the game.
    Returns combined DataFrame or None.
    """
    from datetime import timedelta
    dfs = []
    # Check files from D-1 through game day
    check_dates = [
        (start_time_utc - timedelta(days=2)).strftime("%Y-%m-%d"),
        (start_time_utc - timedelta(days=1)).strftime("%Y-%m-%d"),
        start_time_utc.strftime("%Y-%m-%d"),
    ]
    for date_str in check_dates:
        for fpath in sorted(LINES_DIR.glob(f"{date_str}_*.csv")):
            if "mainline" in fpath.name or "inplay" in fpath.name:
                continue
            df = _read_lines_csv(fpath)
            if df is None:
                continue
            if "start_time" not in df.columns:
                continue
            df["start_time_raw"] = df["start_time"]
            # Filter to rows for this game by start_time
            df["start_time_parsed"] = pd.to_datetime(df["start_time"], utc=True, errors="coerce")
            # Allow ±5min window around known start
            close_to_start = df["start_time_parsed"].between(
                pd.Timestamp(start_time_utc) - pd.Timedelta(minutes=10),
                pd.Timestamp(start_time_utc) + pd.Timedelta(minutes=10),
            )
            df = df[close_to_start]
            if len(df) == 0:
                continue
            dfs.append(df)
    if not dfs:
        return None
    return pd.concat(dfs, ignore_index=True)


# ---------------------------------------------------------------------------
# Auto-discover games and build opener/close pairs
# ---------------------------------------------------------------------------

def discover_games(preds: dict[str, dict], actuals: pd.DataFrame,
                   id_to_name: dict[int, str]) -> list[dict]:
    """
    For each pregame gid, try to find matching lines + actuals.
    Returns list of game dicts with metadata.
    """
    games = []
    for gid, player_preds in preds.items():
        # Check actuals exist
        gid_actuals = actuals[actuals["game_id"] == gid]
        if len(gid_actuals) == 0:
            print(f"  [SKIP] {gid}: no actuals in gamelog (game may not be finished)")
            continue

        # Build pred player names
        pred_names = {}
        for pid, stat_vals in player_preds.items():
            name = id_to_name.get(pid)
            if name:
                pred_names[_normalize_name(name)] = (pid, stat_vals)

        if not pred_names:
            print(f"  [SKIP] {gid}: could not resolve any player names from pregame IDs")
            continue

        # Try to load snapshot lines first
        snap_df = load_snapshot_lines(gid)

        # If snapshot available, extract game start_time from it
        game_start = None
        if snap_df is not None and "start_time" in snap_df.columns:
            st = pd.to_datetime(snap_df["start_time"], utc=True, errors="coerce").dropna()
            if len(st) > 0:
                game_start = st.iloc[0].to_pydatetime()

        # Check player overlap with snapshot
        snap_overlap = 0
        if snap_df is not None:
            snap_names = set(snap_df["player_name_norm"].unique())
            snap_overlap = len(set(pred_names.keys()) & snap_names)

        # Try raw lines if no snapshot or low overlap
        raw_df = None
        raw_overlap = 0
        if snap_overlap < 5 and game_start is not None:
            raw_df = load_raw_lines_for_game(gid[:8], game_start)
            if raw_df is not None:
                raw_names = set(raw_df["player_name_norm"].unique())
                raw_overlap = len(set(pred_names.keys()) & raw_names)

        games.append({
            "gid": gid,
            "pred_names": pred_names,
            "player_preds": player_preds,
            "actuals": gid_actuals,
            "snap_df": snap_df,
            "snap_overlap": snap_overlap,
            "raw_df": raw_df,
            "raw_overlap": raw_overlap,
            "game_start": game_start,
        })
        print(f"  [FOUND] {gid}: snap_overlap={snap_overlap}, raw_overlap={raw_overlap}, "
              f"game_start={game_start}")

    return games


# ---------------------------------------------------------------------------
# Build bet rows for a single game
# ---------------------------------------------------------------------------

def build_bet_rows(game: dict) -> pd.DataFrame:
    """
    For each (player, stat) with a model pred, opener line, and actual:
      - If close line also available: compute open_roi, close_roi, CLV
      - If only opener: compute open_roi only (close columns = NaN)
    """
    pred_names = game["pred_names"]
    actuals = game["actuals"]
    gid = game["gid"]

    # Build actuals lookup: {norm_name: {stat: actual}}
    act_lookup: dict[str, dict] = {}
    for _, row in actuals.iterrows():
        nn = _normalize_name(row["player_name"])
        act_lookup[nn] = {s: float(row[s]) for s in GRADEABLE_STATS}

    rows = []

    # Determine which line source to use
    # PRIORITY: snapshot (has both opener + close in one file via time series)
    # FALLBACK: raw lines (may only have opener)

    def _extract_opener_close(df: pd.DataFrame, player_norm: str, stat: str,
                               game_start: datetime | None) -> tuple | None:
        """
        Returns (open_line, open_over, open_under, close_line, close_over, close_under)
        or (open_line, open_over, open_under, None, None, None) if no close available.
        """
        mask = (df["player_name_norm"] == player_norm) & (df["stat"] == stat)
        sub = df[mask].dropna(subset=["line", "over_price", "under_price"])
        if len(sub) == 0:
            return None

        sub = sub.sort_values("captured_at")

        # Opener = earliest captured_at
        opener_row = sub.iloc[0]

        # Close = latest row strictly before game start (if known)
        if game_start is not None:
            gs_ts = pd.Timestamp(game_start).tz_localize("UTC") if game_start.tzinfo is None else pd.Timestamp(game_start)
            pre_game = sub[sub["captured_at"] < gs_ts]
            close_row = pre_game.iloc[-1] if len(pre_game) > 0 else None
        else:
            # No start time: use last row as close
            close_row = sub.iloc[-1] if len(sub) > 1 else None

        # If opener and close are the same row (only one capture), there's no movement to measure
        has_close = (close_row is not None and
                     close_row["captured_at"] != opener_row["captured_at"])

        return (
            float(opener_row["line"]),
            float(opener_row["over_price"]),
            float(opener_row["under_price"]),
            float(close_row["line"]) if has_close else None,
            float(close_row["over_price"]) if has_close else None,
            float(close_row["under_price"]) if has_close else None,
        )

    # Choose line source
    line_df = None
    line_source = None
    if game["snap_df"] is not None and game["snap_overlap"] >= 3:
        line_df = game["snap_df"]
        line_source = "snapshot"
    elif game["raw_df"] is not None and game["raw_overlap"] >= 3:
        line_df = game["raw_df"]
        line_source = "raw_csv"

    if line_df is None:
        return pd.DataFrame()

    game_start = game["game_start"]

    for player_norm, (pid, stat_vals) in pred_names.items():
        if player_norm not in act_lookup:
            continue
        actuals_for_player = act_lookup[player_norm]

        for stat in GRADEABLE_STATS:
            if stat not in stat_vals:
                continue
            if stat not in actuals_for_player:
                continue

            model_pred = float(stat_vals[stat])
            actual = actuals_for_player[stat]

            result = _extract_opener_close(line_df, player_norm, stat, game_start)
            if result is None:
                continue

            open_line, open_over, open_under, close_line, close_over, close_under = result

            # Opener bet
            bet_side_open, roi_open = settle_bet(model_pred, open_line, open_over, open_under, actual)
            if bet_side_open is None:
                continue

            # Close bet (if available)
            roi_close = None
            clv_pts_val = None
            beat_close = None
            if close_line is not None:
                bet_side_close, roi_close = settle_bet(model_pred, close_line, close_over, close_under, actual)
                if bet_side_close is not None:
                    clv_pts_val = clv_points(bet_side_open, open_line, close_line)
                    beat_close = clv_pts_val > 0

            model_hit_open = roi_open > 0 if roi_open is not None else None
            model_hit_close = roi_close > 0 if roi_close is not None else None

            rows.append({
                "game_id": gid,
                "player_name": player_norm,
                "stat": stat,
                "model_pred": model_pred,
                "open_line": open_line,
                "close_line": close_line,
                "line_moved": (close_line - open_line) if close_line is not None else None,
                "bet_side": bet_side_open,
                "actual": actual,
                "roi_open": roi_open,
                "roi_close": roi_close,
                "clv_pts": clv_pts_val,
                "beat_close": beat_close,
                "model_hit_open": model_hit_open,
                "model_hit_close": model_hit_close,
                "line_source": line_source,
            })

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Summarise results
# ---------------------------------------------------------------------------

def summarise(df: pd.DataFrame) -> None:
    if len(df) == 0:
        print("\nNo gradeable rows.")
        return

    n_games = df["game_id"].nunique()
    has_close = df["roi_close"].notna().sum()
    print(f"\n{'='*70}")
    print(f"OPENER vs CLOSE FRESHNESS GRADE")
    print(f"  Games graded: {n_games}")
    print(f"  Total bet rows: {len(df)}")
    print(f"  Rows with both opener+close: {has_close}")
    print(f"{'='*70}")

    stats_order = ["pts", "reb", "ast", "fg3m", "ALL"]
    header = f"{'STAT':<8}  {'n':>4}  {'open_ROI':>9}  {'close_ROI':>10}  {'delta':>7}  {'CLV_pts':>8}  {'beat_close%':>12}  {'model_hit%':>11}"
    print(header)
    print("-" * len(header))

    for stat in stats_order:
        if stat == "ALL":
            sub = df
            label = "ALL"
        else:
            sub = df[df["stat"] == stat]
            label = stat.upper()

        n = len(sub)
        if n == 0:
            continue

        open_roi = sub["roi_open"].mean() * 100
        sub_close = sub[sub["roi_close"].notna()]
        nc = len(sub_close)

        close_roi_str = f"{sub_close['roi_close'].mean()*100:+.1f}%" if nc > 0 else "N/A"
        delta_str = (f"{(sub_close['roi_open'].mean() - sub_close['roi_close'].mean())*100:+.1f}pp"
                     if nc > 0 else "N/A")
        clv_str = (f"{sub_close['clv_pts'].mean():+.2f}" if nc > 0 else "N/A")
        bc_pct = (f"{sub_close['beat_close'].mean()*100:.0f}%" if nc > 0 else "N/A")
        mh_pct = f"{sub['model_hit_open'].mean()*100:.0f}%"

        print(f"{label:<8}  {n:>4}  {open_roi:>+8.1f}%  {close_roi_str:>10}  "
              f"{delta_str:>7}  {clv_str:>8}  {bc_pct:>12}  {mh_pct:>11}")

    print()
    print("KEY: delta = open_ROI - close_ROI (positive = freshness edge favours OPENER)")
    print("     beat_close% = fraction of bets where we got a better number than the close")
    print("     model_hit% = fraction settled correctly vs OPENER line (not a profitability claim)")

    print(f"\n{'='*70}")
    print("HONEST FRAMING")
    print(f"{'='*70}")
    print(f"  Corpus = {n_games} game(s). n << any statistical bar (need ~300+ for 80% power).")
    print("  These numbers are DIRECTIONAL ONLY. Do NOT claim a freshness edge from this output.")
    print("  Corpus auto-grows: every future game with _pregame.json + timestamped lines")
    print("  logged before tipoff will add rows automatically on next run.")

    # Per-game breakdown
    print(f"\n--- Per-game breakdown ---")
    for gid, gdf in df.groupby("game_id"):
        gc = gdf[gdf["roi_close"].notna()]
        open_roi = gdf["roi_open"].mean() * 100
        close_roi = gc["roi_close"].mean() * 100 if len(gc) > 0 else float("nan")
        print(f"  {gid}: n={len(gdf)}, open_ROI={open_roi:+.1f}%, "
              f"close_ROI={close_roi:+.1f}% (n_close={len(gc)})")

    # CLV direction sanity check
    if has_close > 0:
        clv_sub = df[df["clv_pts"].notna()]
        mean_clv = clv_sub["clv_pts"].mean()
        pct_pos = (clv_sub["clv_pts"] > 0).mean() * 100
        print(f"\n  CLV summary: mean={mean_clv:+.2f} line-pts, beat_close={pct_pos:.0f}%")
        if pct_pos < 30:
            print("  [NOTE] beat_close% < 30% = line mostly moved AGAINST model direction")
            print("         (market disagreed with model, normal for playoff sharp markets)")
        elif pct_pos > 60:
            print("  [NOTE] beat_close% > 60% = line moved WITH model direction (positive signal)")


# ---------------------------------------------------------------------------
# Growth / gap report
# ---------------------------------------------------------------------------

def corpus_gap_report(preds: dict[str, dict], actuals: pd.DataFrame) -> None:
    print(f"\n{'='*70}")
    print("CORPUS GAP ANALYSIS (what to log to grow the corpus)")
    print(f"{'='*70}")
    print(f"  Pregame JSON files found: {len(preds)}")
    print(f"  Game IDs: {sorted(preds.keys())}")
    for gid in sorted(preds.keys()):
        gid_actuals = actuals[actuals["game_id"] == gid]
        snap_exists = bool(list(SNAP_DIR.glob(f"{gid}_close_*.csv")))
        raw_files = sorted(LINES_DIR.glob(f"*_dk.csv")) + sorted(LINES_DIR.glob(f"*_fd.csv"))
        print(f"\n  {gid}:")
        print(f"    Actuals in gamelog: {len(gid_actuals) > 0}")
        print(f"    Close snapshot in snapshots/: {snap_exists}")
        print(f"    Pregame model preds: {len(preds[gid])} players")

    print("""
  TO GROW THE CORPUS (per future game):
    1. Ensure a line scraper runs at game OPEN (earliest available lines)
       and again 30-60 min before tipoff (CLOSE capture).
       Save to data/lines/<date>_<book>.csv with captured_at populated.
    2. Log predictions at tip-minus-X to data/live/<nba_gid>_pregame.json
       (already done by the existing poller when CV_LIVE_PREGAME=1 or similar).
    3. After game, final box scores auto-populate into leaguegamelog_*.parquet
       (or run the gamelog fetch script).
    4. Re-run this script: it auto-discovers all (pregame_json, lines, actuals) triples.
  NOTE: this script relies on player_name JOIN (not player_id) because
  book-specific player_ids differ from NBA IDs. Name normalization handles
  common variants but will miss players with accent characters if the
  lines scraper strips them differently from the gamelog (e.g. diacritic variants).
""")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> pd.DataFrame:
    print("Loading player name<->ID mapping...")
    id_to_name = _load_id_name_map()
    name_to_id = {_normalize_name(v): k for k, v in id_to_name.items()}
    print(f"  {len(id_to_name)} players in gamelog")

    print("\nLoading pregame predictions...")
    preds = load_pregame_preds()
    print(f"  {len(preds)} pregame JSON(s) found: {sorted(preds.keys())}")

    if not preds:
        print("\n  No _pregame.json files found in data/live/.")
        print("  To enable measurement, log predictions before each game to:")
        print("    data/live/<nba_gid>_pregame.json")
        print("  Format: {\"<nba_player_id>\": {\"pts\": X, \"reb\": X, ...}, ...}")
        return pd.DataFrame()

    # Check pregame JSON structure
    print("\nPregame JSON schema check:")
    for gid, player_preds in sorted(preds.items()):
        n_players = len(player_preds)
        sample_pid = next(iter(player_preds))
        sample_stats = list(player_preds[sample_pid].keys())
        has_gradeable = bool(set(sample_stats) & set(GRADEABLE_STATS))
        print(f"  {gid}: {n_players} players, sample stats={sample_stats}, "
              f"has_gradeable_stats={has_gradeable}")

    print("\nLoading actuals from gamelogs...")
    actuals = load_actuals()
    print(f"  {len(actuals)} player-game rows")

    print("\nDiscovering games with lines coverage...")
    games = discover_games(preds, actuals, id_to_name)

    if not games:
        print("\nNo games found with both pregame predictions + actuals. "
              "Run after games complete.")
        corpus_gap_report(preds, actuals)
        return pd.DataFrame()

    print("\nBuilding bet rows...")
    all_rows = []
    for game in games:
        df_game = build_bet_rows(game)
        if len(df_game) > 0:
            all_rows.append(df_game)
            print(f"  {game['gid']}: {len(df_game)} rows "
                  f"({df_game['roi_close'].notna().sum()} with close)")
        else:
            print(f"  {game['gid']}: 0 rows (no line/player overlap)")

    if not all_rows:
        print("\nNo gradeable rows built.")
        corpus_gap_report(preds, actuals)
        return pd.DataFrame()

    df_all = pd.concat(all_rows, ignore_index=True)

    summarise(df_all)
    corpus_gap_report(preds, actuals)

    return df_all


if __name__ == "__main__":
    df_results = main()
    if len(df_results) > 0:
        out_path = REPO / "data" / "cache" / "opener_close_results.csv"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df_results.to_csv(out_path, index=False)
        print(f"\nResults saved to {out_path}")
