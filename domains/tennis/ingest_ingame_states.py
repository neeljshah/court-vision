"""domains.tennis.ingest_ingame_states -- Tennis in-game trajectory states.

Builds NBA-style state snapshots from Sackmann match scores (ATP + WTA).
RESOLUTION: Set-level only (game-by-game within a set not available from ESPN
or Sackmann). One snapshot per completed set boundary.

Schema: sport, game_id, asof_idx, state_diff, frac_elapsed, p0, outcome
  + set_score, game_score, surface.  See frozen schema in mission brief.
LEAK-FREE: p0 = walk_forward_elo win_prob before match; state_diff from
  cumulative games/sets at asof_idx only.

Outputs: data/cache/ingame/tennis_states__{atp,wta}.parquet (gitignored).
Run: python domains/tennis/ingest_ingame_states.py [--sample 400] [--tour atp|wta|both]
"""
from __future__ import annotations

import argparse
import logging
import re
from pathlib import Path
from typing import Optional

import pandas as pd

log = logging.getLogger(__name__)

_REPO = Path(__file__).resolve().parents[2]
_ATP_MATCHES = _REPO / "data" / "domains" / "tennis" / "matches.parquet"
_WTA_MATCHES = _REPO / "data" / "domains" / "tennis" / "wta_matches.parquet"
_OUT_DIR = _REPO / "data" / "cache" / "ingame"
_ATP_OUT = _OUT_DIR / "tennis_states__atp.parquet"
_WTA_OUT = _OUT_DIR / "tennis_states__wta.parquet"

_SPORT = "tennis"
_SET_GAMES_DIVISOR = 12.0  # normaliser for games_within_set_diff


# ---------------------------------------------------------------------------
# Pure parsing helpers (no I/O)
# ---------------------------------------------------------------------------

def parse_score(score_str: str) -> Optional[list[tuple[int, int]]]:
    """Parse set scores from Sackmann format, e.g. '6-3 7-6(5) 3-6 6-4'.

    Returns list of (p1_games, p2_games) per set, or None if unparseable.
    Handles tiebreak notation '7-6(5)'. PURE -- no I/O.
    """
    if not isinstance(score_str, str) or not score_str.strip():
        return None
    pattern = r"(\d+)-(\d+)(?:\(\d+\))?"
    sets = re.findall(pattern, score_str)
    if not sets:
        return None
    return [(int(g1), int(g2)) for g1, g2 in sets]


def set_winner(p1g: int, p2g: int) -> Optional[int]:
    """Return 1 if player1 won this set, 2 if player2 won, None if inconclusive.

    A set is won by taking >=6 games with >=2 margin, or 7-6 (tiebreak).
    PURE.
    """
    if p1g >= 6 and p1g - p2g >= 2:
        return 1
    if p2g >= 6 and p2g - p1g >= 2:
        return 2
    if p1g == 7 and p2g == 6:
        return 1
    if p2g == 7 and p1g == 6:
        return 2
    return None


def build_snapshots(
    game_id: str,
    sets: list[tuple[int, int]],
    match_winner: int,  # 1 or 2
    p0: float,
    surface: str,
    drop_terminal: bool = True,
    best_of: int = 3,
    drop_near_terminal: bool = False,
    frac_max: float = 1.0,
) -> list[dict]:
    """Build in-game state rows for one match.

    One row per completed set boundary.  The FINAL set completion IS the match end
    -- a SETTLED row where frac_elapsed==1.0 and sign(state_diff)==outcome ~100%.
    Such rows are DECIDED-match leakage, not genuinely-live in-game states: they
    inflate base Brier/BSS and prop up a falsely "non-degenerate" gate verdict
    (HONESTY-CRITICAL re-check, 2026-06-18).  With ``drop_terminal=True`` (default)
    the match-ending set boundary is EXCLUDED so the served corpus holds only
    genuinely-undecided live states (frac_elapsed < 1.0).  Set ``drop_terminal=
    False`` only for unit tests that assert the raw terminal geometry.

    STRICTER LIVE-ONLY (robustness re-check, 2026-06-19): even after dropping the
    terminal set boundary, a few states are NEAR-terminal -- the match is all-but-
    decided though one set technically remains.  Two optional, more-conservative
    cuts let us re-test whether the in-game verdict SURVIVES when those almost-
    settled rows are removed (they cannot be fabricated finer; this only PRUNES):
      * ``frac_max`` (default 1.0 = no-op): drop any state with frac_elapsed
        strictly greater than ``frac_max`` (e.g. 0.9 excludes near-terminal rows).
      * ``drop_near_terminal`` (default False): in best-of-5, drop two-set-lead
        states (set_score 2-0 / 0-2) -- the leader is one set from the match and
        the empirical win-rate is ~0.95/0.07, i.e. effectively decided.  In best-
        of-3 such a two-set lead is itself terminal and already dropped, so this
        cut only bites best-of-5.  ``best_of`` is required to apply it correctly.

    SCORE ORIENTATION: Sackmann ``score`` is WINNER-first (winner's games listed
    first every set, e.g. "6-2 6-2" even when the winner is player2).  ``p1``/``p2``
    are STABLE identities (p1_id/p2_id); ``match_winner`` says which won.  When
    ``match_winner == 2`` the raw tuples are (p2g, p1g) and are SWAPPED below to
    (p1g, p2g) so ``state_diff`` is signed toward p1.  Without the swap state_diff
    favours the winner while outcome is p1-relative -> signal collapses (corr~0).

    PURE -- no I/O.  Returns [] for broken/incomplete data.
    """
    if not (0.0 <= p0 <= 1.0):
        return []
    if match_winner not in (1, 2):
        return []
    if not sets or len(sets) < 2:
        return []

    outcome = 1 if match_winner == 1 else 0

    # Re-orient score to p1-perspective.  Raw tuples are winner-first; when p1 is
    # the loser (match_winner==2) flip every set so (p1_games, p2_games) holds.
    if match_winner == 2:
        sets = [(p2g, p1g) for (p1g, p2g) in sets]

    # Total games in the match (for frac_elapsed denominator)
    total_games = sum(g1 + g2 for g1, g2 in sets)
    if total_games == 0:
        return []

    rows = []
    p1_sets = 0
    p2_sets = 0
    cumul_games = 0
    cumul_p1_games = 0
    cumul_p2_games = 0
    n_sets = len(sets)

    for idx, (p1g, p2g) in enumerate(sets):
        sw = set_winner(p1g, p2g)
        if sw == 1:
            p1_sets += 1
        elif sw == 2:
            p2_sets += 1
        # Even if set_winner returns None (unexpected), still track games

        cumul_games += p1g + p2g
        cumul_p1_games += p1g
        cumul_p2_games += p2g

        frac = min(cumul_games / total_games, 1.0)

        # The match-ending set boundary is a SETTLED row (frac==1.0, the outcome
        # is already decided).  Including it leaks decided-match rows into the
        # in-game gate pool and falsely props up base BSS.  Drop it by default so
        # only genuinely-live (undecided) states are served.  Guard on idx too:
        # the last set ALWAYS ends the match, even if rounding leaves frac<1.0.
        is_terminal = (idx == n_sets - 1) or (frac >= 1.0)
        if drop_terminal and is_terminal:
            continue

        # STRICTER live-only cuts (robustness re-check) -- pure pruning, no fabrication.
        # frac_max: drop near-terminal-by-elapsed states.
        if frac > frac_max:
            continue
        # near-terminal-by-sets: in best-of-5 a two-set lead is one set from the
        # match (win-rate ~0.95/0.07).  best_of==5 win-target is 3 sets.
        if drop_near_terminal and best_of == 5:
            lead = max(p1_sets, p2_sets)
            if lead >= 2:  # 2-x in bo5 => one set from match end
                continue

        # state_diff: sets_diff + games_within_next_set_diff/12
        # "games within current set" = the games of the NEXT unfinished set.
        # At set boundary, the current set just finished; the "in-progress" part
        # is 0 games into the next set => 0 contribution from games term.
        # We use cumulative game differential instead per the schema intent:
        #   state_diff = sets_won_diff + games_within_set_diff/12
        # where games_within_set_diff = total p1 games - total p2 games so far,
        # normalised by 12 to keep it < 1 per set on average.
        sets_diff = float(p1_sets - p2_sets)
        games_diff = float(cumul_p1_games - cumul_p2_games)
        state_diff = sets_diff + games_diff / _SET_GAMES_DIVISOR

        # Set score string e.g. "2-0"
        set_score_str = f"{p1_sets}-{p2_sets}"
        # Game score string e.g. "6-3,4-6"
        game_score_str = ",".join(f"{g1}-{g2}" for g1, g2 in sets[: idx + 1])

        rows.append({
            "sport": _SPORT,
            "game_id": game_id,
            "asof_idx": idx,
            "state_diff": state_diff,
            "frac_elapsed": frac,
            "p0": p0,
            "outcome": outcome,
            "set_score": set_score_str,
            "game_score": game_score_str,
            "surface": surface,
        })

    return rows


# ---------------------------------------------------------------------------
# Corpus builder -- lean on existing walk_forward_elo
# ---------------------------------------------------------------------------

def build_corpus(
    matches_df: pd.DataFrame,
    sample_n: Optional[int] = None,
    rng_seed: int = 42,
    drop_near_terminal: bool = False,
    frac_max: float = 1.0,
) -> pd.DataFrame:
    """Build in-game state rows from a matches DataFrame.

    Applies walk_forward_elo to get leak-free p0 per match, then expands
    each match into per-set-boundary rows via build_snapshots.

    Parameters
    ----------
    matches_df:
        DataFrame with cols: event_id, date, p1_id, p2_id, winner, surface,
        score, best_of, retirement (bool).
    sample_n:
        If set, deterministically sample this many COMPLETE matches (no
        retirement) before processing.  Useful for speed.

    Returns
    -------
    pd.DataFrame with the frozen state schema.
    """
    from domains.tennis.elo_walkforward import walk_forward_elo

    # Drop retirements and rows with missing score
    df = matches_df.copy()
    df = df[df["retirement"] == False].copy()  # noqa: E712
    df = df[df["score"].notna()].copy()
    df = df[df["winner"].isin([1, 2])].copy()

    if sample_n is not None and len(df) > sample_n:
        df = df.sample(sample_n, random_state=rng_seed).copy()

    if df.empty:
        log.warning("No complete matches to process")
        return pd.DataFrame()

    # Walk-forward Elo -- leak-free win_prob_p1 per match
    log.info("Running walk_forward_elo on %d matches ...", len(df))
    elo_df = walk_forward_elo(df)

    rows: list[dict] = []
    skipped = 0

    for _, row in elo_df.iterrows():
        sets = parse_score(row["score"])
        if sets is None or len(sets) < 2:
            skipped += 1
            continue

        bo = int(row["best_of"]) if row.get("best_of") in (3, 5) else 3
        snaps = build_snapshots(
            game_id=str(row["event_id"]),
            sets=sets,
            match_winner=int(row["winner"]),
            p0=float(row["win_prob_p1"]),
            surface=str(row.get("surface", "Unknown")),
            best_of=bo,
            drop_near_terminal=drop_near_terminal,
            frac_max=frac_max,
        )
        rows.extend(snaps)

    if skipped:
        log.info("Skipped %d matches (incomplete/bad score)", skipped)

    if not rows:
        return pd.DataFrame()

    out = pd.DataFrame(rows)
    # Enforce dtypes
    out["asof_idx"] = out["asof_idx"].astype("int32")
    out["outcome"] = out["outcome"].astype("int8")
    out["state_diff"] = out["state_diff"].astype("float32")
    out["frac_elapsed"] = out["frac_elapsed"].astype("float32")
    out["p0"] = out["p0"].astype("float32")
    return out


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _main() -> None:
    parser = argparse.ArgumentParser(
        description="Build tennis in-game state parquets (ATP + WTA)."
    )
    parser.add_argument(
        "--tour", choices=["atp", "wta", "both"], default="both",
        help="Which tour to process (default: both)."
    )
    parser.add_argument(
        "--sample", type=int, default=None,
        help="Max matches per corpus (deterministic). Omit for full corpus."
    )
    parser.add_argument(
        "--frac-max", type=float, default=1.0,
        help="Stricter live-only: drop states with frac_elapsed > this (e.g. 0.9)."
    )
    parser.add_argument(
        "--drop-near-terminal", action="store_true",
        help="Stricter live-only: drop best-of-5 two-set-lead (2-0/0-2) states."
    )
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
        df = build_corpus(
            matches, sample_n=args.sample,
            drop_near_terminal=args.drop_near_terminal, frac_max=args.frac_max,
        )
        if df.empty:
            log.warning("No states built for %s", tour)
            continue
        df.to_parquet(dst, index=False)
        n_matches = df["game_id"].nunique()
        avg_states = len(df) / max(n_matches, 1)
        p1_wr = df.groupby("game_id")["outcome"].first().mean()
        log.info(
            "[%s] matches=%d  total_rows=%d  avg_states/match=%.1f  "
            "p1_win_rate=%.3f  -> %s",
            tour.upper(), n_matches, len(df), avg_states, p1_wr, dst
        )

    print("Done.")


if __name__ == "__main__":
    _main()
