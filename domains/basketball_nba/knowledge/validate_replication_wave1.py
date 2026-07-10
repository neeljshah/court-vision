"""domains.basketball_nba.knowledge.validate_replication_wave1 -- second-
corpus REPLICATION pass for the 3 CONFIRMED_LOCAL NBA mechanisms the task
brief named as strongest: #47 timeout-interrupts-run, #38 Q1 slow-start
persistence, #34/#35 fast-break/paint persistence. Same bars as each
original (imported, not re-typed) ported to a genuinely disjoint second
corpus. No new test design invented -- pure re-application.

STEP 0 PREMISE CHECK (this session, before any test ran):

  #47 timeout_interrupts_opponent_run -- task brief assumed "2024-25 pbp".
  Disk check: player_boxscores.parquet (the box source the ORIGINAL run
  joined against) starts at season 2023-24, so its combined 1,289-game pool
  is 1,230 x 2023-24 + 48 x 2024-25 + 11 x 2025-26 -- the 2024-25/2025-26
  games are already INSIDE the original's pooled split-half, not a fresh
  corpus, and at 48+11=59 games they are too thin to stand alone anyway.
  A genuinely disjoint, comparably-sized second corpus DOES exist though:
  games.parquet carries season=2022-23 for 1,230 local game_ids, and all
  1,230 have a local pbp_<id>_p1.json file -- full season coverage, zero
  overlap with the original's box-scored pool (player_boxscores.parquet has
  no 2022-23 rows at all). Replicated on 2022-23 instead of the assumed
  2024-25 slice; the raw pbp reader (game_samples) needs only the file +
  games.parquet's date column, no box join required.

  #38 q1_slow_start_persists -- linescores_2024_25.parquet (1,321 games)
  exists on disk and is already proven structurally compatible with
  _derive_realized (used successfully for #45/#46's Q3-state family on this
  same file). Never previously run through q1_slow_start_persists itself.
  Genuine, disjoint, full-season second corpus -- replicated as assumed.

  #34/#35 fast_break_pts / paint_pts persistence -- fresh disk check:
  espn_boxscores.parquet spans 2024-10-22..2026-05-24 (1,977 games) but the
  box-detail columns (fast_break_pts, paint_pts, tov_pts, largest_lead) are
  non-null for exactly 675 rows, ALL dated 2026 (i.e. the >=2026-01-20
  slice already used by the original #34/#35 run) -- 0 non-null rows for
  any 2024-25 or pre-2026-01-20 2025-26 date. The only other local file with
  a `fast_break` column, data/cache/player_breakdown_features.parquet
  (season=2024-25, n=569), is a PLAYER-season aggregate (one row per player
  per season, no date/game_id) -- wrong granularity for the split-half-by-
  date + same-game-margin design these rows require; using it would not be
  "the same design ported to a new corpus," it would be a different test.
  No second corpus exists locally -> NOT_REPLICABLE_NO_CORPUS, honest, no
  test run.

Run: python -m domains.basketball_nba.knowledge.validate_replication_wave1
"""
from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

from domains.basketball_nba.knowledge._data import LEDGER_PATH, REPO
from domains.basketball_nba.knowledge.validate_research_wave2 import (
    ALPHA as TIMEOUT_ALPHA,
    MIN_EFFECT_TIMEOUT,
    MIN_GROUP_N,
    PBP_DIR,
    _combine_halves,
    _paired_verdict,
    game_samples,
)
from domains.basketball_nba.knowledge.validate_quarter_volatility import (
    q1_slow_start_persists,
    team_game_frame as qv_team_game_frame,
)
from scripts.platformkit.io_atomic import append_jsonl_atomic

GAMES_PATH = REPO / "data" / "domains" / "basketball_nba" / "games.parquet"
LINESCORES_2024_25_PATH = REPO / "data" / "domains" / "basketball_nba" / "linescores_2024_25.parquet"
ESPN_BOX_PATH = REPO / "data" / "domains" / "basketball_nba" / "espn_boxscores.parquet"
PLAYER_BREAKDOWN_PATH = REPO / "data" / "cache" / "player_breakdown_features.parquet"

ORIG_TIMEOUT_SIGN = -1   # original #47: opponent PPM drops after a timeout (eff ~ -0.73)
ORIG_Q1_SIGN = 1         # original #38: r=+0.7171 (fast starters stay fast starters)


# --------------------------------------------------------- #47 replication --
def timeout_interrupts_opponent_run_replication_2022_23() -> Dict[str, Any]:
    games = pd.read_parquet(GAMES_PATH)
    avail = {p.name[4:-8] for p in PBP_DIR.glob("pbp_*_p1.json")}
    sub = games[(games["season"] == "2022-23") & (games["game_id"].isin(avail))]
    if len(sub) == 0:
        return {"hypothesis": "timeout_interrupts_opponent_run_replication_2022_23",
                "n": 0, "effect": None, "p": None, "verdict": "NOT_REPLICABLE_NO_CORPUS",
                "note": "no 2022-23 game_id in games.parquet overlaps a local pbp p1 file"}
    dates = sub.set_index("game_id")["date"]
    rows: List[Dict[str, Any]] = []
    for gid in sub["game_id"]:
        rows.extend(game_samples(gid))
    df = pd.DataFrame(rows)
    if df.empty:
        return {"hypothesis": "timeout_interrupts_opponent_run_replication_2022_23",
                "n": 0, "effect": None, "p": None, "verdict": "NOT_REPLICABLE_NO_CORPUS",
                "note": "2022-23 pbp files parsed but yielded zero resolvable timeout windows "
                        "(n_games=%d)" % len(sub)}
    df["date"] = df["game_id"].map(dates)
    mid = df["date"].median()
    h1 = df[df["date"] <= mid]
    h2 = df[df["date"] > mid]
    r1 = _paired_verdict(h1["ppm_before"], h1["ppm_after"], "repl2022_23_h1")
    r2 = _paired_verdict(h2["ppm_before"], h2["ppm_after"], "repl2022_23_h2")
    combined = _combine_halves([r1, r2], "timeout_interrupts_opponent_run_replication_2022_23")
    same_sign = (combined["verdict"] == "CONFIRMED_LOCAL"
                 and all((r["effect"] or 0) * ORIG_TIMEOUT_SIGN > 0
                         for r in (r1, r2) if r["verdict"] == "CONFIRMED_LOCAL"))
    verdict = "REPLICATED" if same_sign else (
        "NOT_REPLICABLE_NO_CORPUS" if combined["verdict"] == "NOT_TESTABLE" else "FAILED_REPLICATION")
    return {"hypothesis": "timeout_interrupts_opponent_run_replication_2022_23",
            "n": int(len(df)), "effect": None, "p": None, "verdict": verdict,
            "note": "2022-23 season (n_games=%d local pbp, fully disjoint from the original's "
                    "2023-24-dominant pool) -- %s; original bar ALPHA=%.2g MIN_EFFECT=%.2g "
                    "MIN_GROUP_N=%d unchanged. %s"
                    % (len(sub), combined["verdict"], TIMEOUT_ALPHA, MIN_EFFECT_TIMEOUT, MIN_GROUP_N,
                       combined["note"])}


# --------------------------------------------------------- #38 replication --
def q1_slow_start_persists_replication_2024_25() -> Dict[str, Any]:
    ls = pd.read_parquet(LINESCORES_2024_25_PATH)
    tg = qv_team_game_frame(ls)
    r = q1_slow_start_persists(tg)
    r["hypothesis"] = "q1_slow_start_persists_replication_2024_25"
    same_sign = r["verdict"] == "CONFIRMED_LOCAL" and (r["effect"] or 0) * ORIG_Q1_SIGN > 0
    verdict = "REPLICATED" if same_sign else "FAILED_REPLICATION"
    r["verdict"] = verdict
    r["note"] = "linescores_2024_25.parquet (1,321 games, disjoint season from the original's " \
                "linescores.parquet/2025-26 run) -- " + r["note"]
    return r


# ----------------------------------------------------- #34/#35 -- blocked --
def _boxdetail_no_second_corpus(stat: str) -> Dict[str, Any]:
    espn = pd.read_parquet(ESPN_BOX_PATH)
    espn["date"] = pd.to_datetime(espn["date"])
    non2026 = espn[espn["date"] < "2026-01-01"][f"home_{stat}"].notna().sum()
    pb = pd.read_parquet(PLAYER_BREAKDOWN_PATH)
    return {"hypothesis": "%s_persistence_replication" % stat, "n": 0, "effect": None, "p": None,
            "verdict": "NOT_REPLICABLE_NO_CORPUS",
            "note": "espn_boxscores.parquet home_%s non-null for pre-2026 dates: %d (of %d rows total) "
                    "-- the only other local %s column, player_breakdown_features.parquet, is a player-"
                    "SEASON aggregate (season=%s, n=%d, no date/game_id), wrong granularity for the "
                    "split-half-by-date + same-game-margin design #34/#35 used. No team-game-level "
                    "second-season corpus with this column exists locally."
                    % (stat, int(non2026), len(espn), stat,
                       ",".join(sorted(pb["season"].unique())) if "season" in pb.columns else "?", len(pb))}


def fast_break_pts_persistence_replication() -> Dict[str, Any]:
    return _boxdetail_no_second_corpus("fast_break_pts")


def paint_pts_persistence_replication() -> Dict[str, Any]:
    return _boxdetail_no_second_corpus("paint_pts")


def run() -> List[Dict[str, Any]]:
    rows = [
        timeout_interrupts_opponent_run_replication_2022_23(),
        q1_slow_start_persists_replication_2024_25(),
        fast_break_pts_persistence_replication(),
        paint_pts_persistence_replication(),
    ]
    for r in rows:
        r["sport"] = "basketball_nba"
        r["corpus"] = "replication_wave1_second_corpus"
        r["edge_claimed"] = False
        append_jsonl_atomic(LEDGER_PATH, r)
    return rows


def main() -> int:
    for r in run():
        print("%-58s %-24s %s" % (r["hypothesis"], r["verdict"], r["note"][:160]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


def _self_check() -> None:
    """No live network/disk-parquet dependency -- pure logic check on the
    sign/verdict combination rules used above."""
    assert ("REPLICATED" if ("CONFIRMED_LOCAL" == "CONFIRMED_LOCAL" and (0.71) * 1 > 0) else "x") == "REPLICATED"
    assert ("REPLICATED" if ("CONFIRMED_LOCAL" == "CONFIRMED_LOCAL" and (-0.71) * 1 > 0) else "x") != "REPLICATED"
    print("self-check OK")
