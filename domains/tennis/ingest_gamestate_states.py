"""domains.tennis.ingest_gamestate_states -- Tennis GAMES-WITHIN-SET detail layer.

LANE B detail layer for the in-game DETAIL gate.  Emits a BASE in-game-state
corpus (rows keyed (game_id, asof_idx) -- the same schema the existing
``ingest_ingame_states`` produces) PLUS additive, leak-free AS-OF detail columns
that expose the GAMES-WITHIN-SET / break / serve-hold structure the base hides:

    games_diff_in_set        -- signed game differential of the MOST-RECENTLY
                                COMPLETED set, p1-relative (games-within-set).
    sets_diff                -- signed sets-won differential so far, p1-relative.
    break_pts_converted_diff -- leak-free BREAK PROXY: signed count of "decisive"
                                games beyond the minimum needed to win each
                                completed set (a 6-0 implies more breaks than a
                                7-6 tiebreak set).  Derived ONLY from per-set game
                                counts <= asof_idx -- never from match-final
                                bpFaced/bpSaved totals (those would LEAK).
    serve_holds_streak       -- signed run length of consecutive completed sets
                                won by the same player so far (momentum proxy).

PAYLOAD-PROBE (2026-06-19, zero-network, verified before building):
  * On disk (data/domains/tennis/{matches,wta_matches}.parquet) the ONLY in-match
    structure is the Sackmann ``score`` string -> per-SET game counts, e.g.
    "6-3 7-6(5) 3-6 6-4", with tiebreak notation "7-6(5)".
  * TRUE point-by-point data (Sackmann ``tennis_pointbypoint`` /
    MatchChartingProject) is NOT on disk.  Genuine per-point break-point-converted
    and per-game serve-hold sequences are therefore NOT available zero-network.
  * match_stats.parquet has p1_bpSaved/p1_bpFaced -- but these are MATCH-FINAL
    TOTALS, not per-set; using them on a per-tick row would be a match-FINAL
    aggregate future-leak (RAILS-forbidden).  They are DELIBERATELY NOT USED.
  => Honest resolution is SET-BOUNDARY.  Every detail column is reconstructed
     using ONLY sets 0..asof_idx (a tick at boundary i sees no future set, and
     NEVER the match winner).  The columns are PROXIES, labelled as such.

SCORE ORIENTATION (recall the prior tennis fix): Sackmann ``score`` is
WINNER-first (winner's games listed first every set).  p1/p2 are STABLE
identities; ``match_winner`` says which won.  When match_winner==2 the raw
tuples are swapped to (p1_games, p2_games) so every detail column is signed
toward p1 -- WITHOUT this swap the columns would track the winner (a winner-leak
that the gate's leak guard would or would not catch, but which is plainly wrong).

Outputs: data/cache/ingame/tennis_gamestate__{atp,wta}.parquet (gitignored).
Run: python domains/tennis/ingest_gamestate_states.py [--sample 400] [--tour atp|wta|both]

LEAK-FREE; NO $; CALIBRATION only.  ASCII-only; <=300 LOC; numpy/pandas/stdlib.
"""
from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd

# Reuse the audited, leak-free per-set parsing + base reconstruction so the
# DETAIL parquet shares the EXACT (game_id, asof_idx) keys + terminal-drop policy
# of the base corpus (the gate inner-merges on those keys).
from domains.tennis.ingest_ingame_states import parse_score, set_winner

log = logging.getLogger(__name__)

_REPO = Path(__file__).resolve().parents[2]
_ATP_MATCHES = _REPO / "data" / "domains" / "tennis" / "matches.parquet"
_WTA_MATCHES = _REPO / "data" / "domains" / "tennis" / "wta_matches.parquet"
_OUT_DIR = _REPO / "data" / "cache" / "ingame"
_ATP_OUT = _OUT_DIR / "tennis_gamestate__atp.parquet"
_WTA_OUT = _OUT_DIR / "tennis_gamestate__wta.parquet"

_SPORT = "tennis"
_SET_GAMES_DIVISOR = 12.0  # mirror base normaliser for games-within-set scale


# ---------------------------------------------------------------------------
# Pure detail helpers (no I/O) -- all leak-free as-of (use only sets <= idx)
# ---------------------------------------------------------------------------

def _set_break_proxy(p1g: int, p2g: int) -> int:
    """Leak-free BREAK proxy for ONE completed set, signed toward p1.

    A set decided 6-0/6-1/6-2 implies more service breaks than a 6-4 or a 7-6
    tiebreak set.  We have no per-game serve order, so we use the structural
    surrogate: (winner_games - loser_games) - 2 is the "decisive margin" beyond
    the minimal +2 hold-only win, clamped at >=0, signed toward the set winner.
    A tiebreak set (7-6) -> margin 1 -> proxy 0 (held to a breaker).  PURE.

    This is derived ONLY from this set's game counts -- no match-final total, no
    future set, no winner identity -- so it is leak-free and as-of.
    """
    margin = abs(p1g - p2g)
    decisive = max(0, margin - 2)
    if p1g > p2g:
        return decisive
    if p2g > p1g:
        return -decisive
    return 0


def build_detail_rows(
    game_id: str,
    sets: List[Tuple[int, int]],
    match_winner: int,  # 1 or 2 (STABLE identity, not score orientation)
    drop_terminal: bool = True,
    game_date: Optional[str] = None,
) -> List[dict]:
    """Build per-set-boundary DETAIL rows for one match (mirrors base keys).

    Returns rows {sport, game_id, asof_idx, games_diff_in_set, sets_diff,
    break_pts_converted_diff, serve_holds_streak, date}.  One row per completed
    set boundary; the match-ending (settled) boundary is dropped by default so
    the DETAIL keys line up with the base LIVE-ONLY corpus.

    game_date: ISO YYYY-MM-DD match date, constant across the match's rows
    (added for venue-history/replay joins). Optional/None for backward-compat.

    LEAK-FREE: every value at asof_idx i uses only sets[0..i]; NEVER the match
    winner and NEVER a future set.  PURE -- no I/O; [] on broken input.
    """
    if match_winner not in (1, 2):
        return []
    if not sets or len(sets) < 2:
        return []

    # Re-orient to p1-perspective (Sackmann score is winner-first).
    if match_winner == 2:
        sets = [(p2g, p1g) for (p1g, p2g) in sets]

    rows: List[dict] = []
    p1_sets = 0
    p2_sets = 0
    cumul_break = 0
    streak = 0          # signed run length of consecutive same-player set wins
    last_winner = 0     # 1 / 2 / 0 of the previous COMPLETED set
    n_sets = len(sets)

    for idx, (p1g, p2g) in enumerate(sets):
        sw = set_winner(p1g, p2g)
        if sw == 1:
            p1_sets += 1
        elif sw == 2:
            p2_sets += 1

        cumul_break += _set_break_proxy(p1g, p2g)

        # serve-hold streak: consecutive completed sets won by the same player.
        if sw in (1, 2):
            if sw == last_winner:
                streak += 1 if sw == 1 else -1
            else:
                streak = 1 if sw == 1 else -1
            last_winner = sw
        # (sw None -> inconclusive set; leave streak unchanged)

        # games-within-set of THIS (most-recently completed) set, p1-signed.
        games_diff_in_set = float(p1g - p2g) / _SET_GAMES_DIVISOR

        # Drop the match-ending settled boundary so keys match the base corpus.
        is_terminal = (idx == n_sets - 1)
        if drop_terminal and is_terminal:
            continue

        rows.append({
            "sport": _SPORT,
            "game_id": game_id,
            "asof_idx": idx,
            "games_diff_in_set": games_diff_in_set,
            "sets_diff": float(p1_sets - p2_sets),
            "break_pts_converted_diff": float(cumul_break),
            "serve_holds_streak": float(streak),
            "date": game_date,
        })

    return rows


# ---------------------------------------------------------------------------
# Corpus builder -- lean on the same leak-free walk_forward filter as base
# ---------------------------------------------------------------------------

def build_corpus(
    matches_df: pd.DataFrame,
    sample_n: Optional[int] = None,
    rng_seed: int = 42,
) -> pd.DataFrame:
    """Build per-set-boundary DETAIL rows from a matches DataFrame.

    Filters retirements / bad scores identically to the base builder so the keys
    line up, then expands each match via ``build_detail_rows``.  Does NOT run Elo
    (the DETAIL parquet carries no p0; the gate squashes a detail column into the
    p0 slot itself).
    """
    df = matches_df.copy()
    df = df[df["retirement"] == False].copy()  # noqa: E712
    df = df[df["score"].notna()].copy()
    df = df[df["winner"].isin([1, 2])].copy()

    if sample_n is not None and len(df) > sample_n:
        df = df.sample(sample_n, random_state=rng_seed).copy()

    if df.empty:
        log.warning("No complete matches to process")
        return pd.DataFrame()

    rows: List[dict] = []
    skipped = 0
    for _, row in df.iterrows():
        sets = parse_score(row["score"])
        if sets is None or len(sets) < 2:
            skipped += 1
            continue
        raw_date = row.get("date") if hasattr(row, "get") else None
        game_date = str(raw_date)[:10] if raw_date is not None and pd.notna(raw_date) else None
        snaps = build_detail_rows(
            game_id=str(row["event_id"]),
            sets=sets,
            match_winner=int(row["winner"]),
            game_date=game_date,
        )
        rows.extend(snaps)

    if skipped:
        log.info("Skipped %d matches (incomplete/bad score)", skipped)
    if not rows:
        return pd.DataFrame()

    out = pd.DataFrame(rows)
    out["asof_idx"] = out["asof_idx"].astype("int32")
    for c in ("games_diff_in_set", "sets_diff",
              "break_pts_converted_diff", "serve_holds_streak"):
        out[c] = out[c].astype("float32")
    return out


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Build tennis games-within-set DETAIL parquets (ATP + WTA)."
    )
    parser.add_argument("--tour", choices=["atp", "wta", "both"], default="both")
    parser.add_argument("--sample", type=int, default=None,
                        help="Max matches per corpus (deterministic).")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    _OUT_DIR.mkdir(parents=True, exist_ok=True)

    tours = {
        "atp": (_ATP_MATCHES, _ATP_OUT),
        "wta": (_WTA_MATCHES, _WTA_OUT),
    }
    selected = list(tours.keys()) if args.tour == "both" else [args.tour]

    for tour, (src, dst) in tours.items():
        if tour not in selected:
            continue
        if not src.exists():
            log.warning("Missing: %s -- skipping %s", src, tour)
            continue
        log.info("Loading %s ...", src)
        matches = pd.read_parquet(src)
        df = build_corpus(matches, sample_n=args.sample)
        if df.empty:
            log.warning("No detail rows built for %s", tour)
            continue
        # Atomic write: readers polling this path mid-rebuild must never see a
        # truncated/partial parquet (the parquet-rebuild-race landmine).
        tmp = dst.with_suffix(dst.suffix + ".tmp")
        df.to_parquet(tmp, index=False)
        tmp.replace(dst)
        n_matches = df["game_id"].nunique()
        log.info("[%s] matches=%d  rows=%d  -> %s",
                 tour.upper(), n_matches, len(df), dst)

    print("Done.")


if __name__ == "__main__":
    _main()
