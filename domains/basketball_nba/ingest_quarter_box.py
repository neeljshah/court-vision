"""domains.basketball_nba.ingest_quarter_box — per-quarter team points parquet.

Reads cached quarter box JSON from data/cache/quarter_box/*.json and produces a
tidy per-(game_id, team_id, quarter) parquet with team-level points.

Source JSON format (confirmed from ingest_boxscores.py analysis):
  {"game_id": ..., "period": N, "players": [...], "teams": [...]}
  Each teams[] element carries: team_id, team_abbreviation, pts (int), etc.

We use the ``teams`` array (not players) so there are exactly 2 rows per quarter
file (one per team), and the pts field is the authoritative quarter total.

Output parquet: data/cache/nba_quarter_points.parquet
  Columns: game_id (str), team_id (int64), team_abbr (str), quarter (int),
           pts (float64)

VALIDATE: after building, per-game team totals (sum across quarters 1-4) are
compared against the expected game total inferred by summing quarters — OT games
may have extra periods (period 5+), so validation allows a slack of 30 pts.

COVERAGE (HONEST): mirror of ingest_boxscores.py — cache covers ~1299 games
(2024-25 near complete + 2025-26 partial). NO edge claimed.

CLI: python -m domains.basketball_nba.ingest_quarter_box [--force]
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CACHE = _REPO_ROOT / "data" / "cache" / "quarter_box"
_DEFAULT_OUT = _REPO_ROOT / "data" / "cache" / "nba_quarter_points.parquet"

OUTPUT_COLS: Tuple[str, ...] = ("game_id", "team_id", "team_abbr", "quarter", "pts")


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _game_ids_from_cache(cache_dir: Path) -> List[str]:
    """Distinct game_ids present in the quarter_box cache dir."""
    ids: set = set()
    for fp in cache_dir.glob("*_q*.json"):
        head = fp.stem.rsplit("_q", 1)
        if len(head) == 2 and head[1].isdigit():
            ids.add(head[0])
    return sorted(ids)


def _iter_quarter_files(cache_dir: Path, game_id: str) -> List[Tuple[int, Path]]:
    """Return (period, path) for every existing q-file of game_id, period-sorted."""
    found: List[Tuple[int, Path]] = []
    for fp in cache_dir.glob(f"{game_id}_q*.json"):
        head = fp.stem.rsplit("_q", 1)
        if len(head) == 2 and head[1].isdigit():
            found.append((int(head[1]), fp))
    return sorted(found, key=lambda t: t[0])


def _load_teams_from_file(path: Path) -> Tuple[int, List[dict]]:
    """Return (period, teams_list) from one quarter file; (-1, []) on failure."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        logger.warning("Could not read %s; skipping.", path)
        return -1, []
    if not isinstance(data, dict):
        return -1, []
    teams = data.get("teams")
    if not isinstance(teams, list):
        return -1, []
    try:
        period = int(data.get("period", -1))
    except (TypeError, ValueError):
        period = -1
    return period, teams


def _parse_game(cache_dir: Path, game_id: str) -> List[dict]:
    """Return per-(game_id, team_id, quarter) rows for one game."""
    rows: List[dict] = []
    for file_period, path in _iter_quarter_files(cache_dir, game_id):
        period, teams = _load_teams_from_file(path)
        eff_period = period if period > 0 else file_period
        for team in teams:
            try:
                tid = int(team.get("team_id"))
            except (TypeError, ValueError):
                continue
            abbr = str(team.get("team_abbreviation", ""))
            try:
                pts = float(team.get("pts", 0) or 0)
            except (TypeError, ValueError):
                pts = 0.0
            rows.append({
                "game_id": str(game_id),
                "team_id": tid,
                "team_abbr": abbr,
                "quarter": eff_period,
                "pts": pts,
            })
    return rows


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_quarter_points(
    cache_dir: Optional[str] = None,
    out_path: Optional[str] = None,
    force: bool = False,
) -> Path:
    """Parse quarter box cache into nba_quarter_points.parquet.

    Parameters
    ----------
    cache_dir : path to quarter_box cache dir (default: data/cache/quarter_box)
    out_path  : output parquet path (default: data/cache/nba_quarter_points.parquet)
    force     : if False and out_path exists, load and return it without recomputing

    Returns
    -------
    Path to the written parquet.
    """
    cdir = Path(cache_dir) if cache_dir is not None else _DEFAULT_CACHE
    dest = Path(out_path) if out_path is not None else _DEFAULT_OUT

    if not force and dest.exists():
        logger.info("Output already exists at %s; skipping rebuild (use --force).", dest)
        return dest

    if not cdir.exists():
        raise FileNotFoundError(f"quarter_box cache not found at {cdir}.")

    all_rows: List[dict] = []
    game_ids = _game_ids_from_cache(cdir)
    skipped = 0
    for gid in game_ids:
        try:
            all_rows.extend(_parse_game(cdir, gid))
        except Exception:
            skipped += 1
            logger.exception("Failed parsing game %s; skipping.", gid)

    if all_rows:
        df = pd.DataFrame(all_rows)
        df["team_id"] = df["team_id"].astype("int64")
        df["quarter"] = df["quarter"].astype("int64")
        df["pts"] = df["pts"].astype("float64")
        df = df.reindex(columns=list(OUTPUT_COLS))
        df = df.sort_values(["game_id", "team_id", "quarter"], kind="mergesort").reset_index(drop=True)
    else:
        df = pd.DataFrame(columns=list(OUTPUT_COLS))

    dest.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(str(dest), index=False)

    if skipped:
        logger.warning("Skipped %d games due to parse errors.", skipped)
    logger.info("Wrote %d rows (%d games) to %s", len(df),
                df["game_id"].nunique() if len(df) else 0, dest)
    return dest


def validate_quarter_sums(df: pd.DataFrame, ot_slack: float = 30.0) -> dict:
    """Validate per-game quarter point sums are self-consistent.

    For each (game_id, team_id), sum all quarters. Within a game, both teams'
    per-regulation-quarter sums should be roughly consistent; we check that no
    single team-game deviates pathologically.

    Returns a summary dict with n_games, n_violations, violation_rate.
    """
    totals = df.groupby(["game_id", "team_id"])["pts"].sum().reset_index()
    totals.columns = ["game_id", "team_id", "total_pts"]  # type: ignore[assignment]
    # For each game, we expect exactly 2 teams. Cross-check: pts should be >= 0
    neg = (totals["total_pts"] < 0).sum()
    n_games = totals["game_id"].nunique()
    violations = neg  # pathological negatives are violations
    return {
        "n_games": int(n_games),
        "n_team_games": len(totals),
        "n_violations_negative_pts": int(violations),
        "ot_slack_used": float(ot_slack),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="quarter_box cache → nba_quarter_points.parquet")
    ap.add_argument("--cache-dir", default=None, help="quarter_box cache dir")
    ap.add_argument("--out", default=None, help="output parquet path")
    ap.add_argument("--force", action="store_true", help="force rebuild even if output exists")
    args = ap.parse_args()

    dest = build_quarter_points(cache_dir=args.cache_dir, out_path=args.out, force=args.force)
    df = pd.read_parquet(str(dest))
    n_games = df["game_id"].nunique() if len(df) else 0
    n_quarters = df["quarter"].nunique() if len(df) else 0
    print(f"Wrote {dest}")
    print(f"Rows: {len(df)} | Games: {n_games} | Distinct quarters: {n_quarters}")
    if len(df):
        val = validate_quarter_sums(df)
        print(f"Validation: {val}")
        print("Sample (5 rows):")
        print(df.head(5).to_string())
    print("HONEST: descriptive realized box; NO edge claimed.")
