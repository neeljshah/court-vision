"""domains.basketball_nba.ingest_defender_matchup_states -- LEAK-FREE as-of
DEFENDER-MATCHUP profile layer over the already-on-disk
``data/defender_matchups_{2024-25,2025-26}.parquet`` corpus (37,395 rows combined,
fully populated, REAL ``def_player_id``, ZERO network).

This is the RECOMMENDED FIRST deep-data ingest from
``.planning/product/deepdata/basketball_nba.md``: the only deep, per-game,
clean-identity corpus on disk that the ``domains/basketball_nba`` ingest does not
already touch. It is genuinely NEW signal -- individual defensive impact (opponent
FG%/FG3% allowed, blocks, switches, matchup workload) -- not a recombination of the
score/clock micro-state the 4-sport meta-finding already rejected.

SIBLING PATTERN: identical snapshot-BEFORE-update walk-forward discipline as
``asof_box_extra.py`` / ``asof_features.py`` (the proven frozen-base + additive-asof
pattern), but keyed at the PLAYER/matchup level (one row per defender-game) and using
a PRIOR-N rolling window instead of an all-time trailing mean.

------------------------------------------------------------------------------------
FROZEN BASE schema (one row per defender-game; the matchup-level identity spine):
  game_id, game_date, def_player_id, def_team_tricode
------------------------------------------------------------------------------------
ADDITIVE as-of columns (every one is shift1 over the defender's STRICTLY PRIOR games,
sorted by game_date; NaN until >=1 prior game; NEVER reads the current game):
  def_priorN_fg_pct_allowed_asof    -- prior-N rolling FG% allowed in matchups
  def_priorN_fg3_pct_allowed_asof   -- prior-N rolling FG3% allowed in matchups
  def_priorN_pts_allowed_per36_asof -- prior-N rolling points allowed per 36 matchup-min
  def_priorN_blocks_per_game_asof   -- prior-N rolling blocks (matchup) per game
  def_priorN_switches_per_game_asof -- prior-N rolling switches-on per game
  def_priorN_matchup_min_asof       -- prior-N rolling matchup minutes per game (role proxy)
  def_n_prior                       -- support count (the gate MUST require >= a floor)
------------------------------------------------------------------------------------
DIAGNOSTICS (kept on the row, NEVER usable as features -- they are this game's REALIZED
matchup outcome, i.e. the label surface for the as-of features):
  realized_fg_pct_allowed, realized_fg3_pct_allowed, realized_points_allowed,
  realized_blocks_matchup, realized_switches_on, realized_matchup_minutes_total

LEAK-FREENESS (the non-negotiable rails):
- Every ``*_asof`` is computed snapshot-BEFORE-update: we record the defender's
  prior-N rolling rate using ONLY their games with strictly earlier game_date, THEN
  fold the current game into the rolling window. The current game NEVER informs its
  own ``*_asof`` value -> shift1 by construction.
- PRIOR-N only: a bounded deque of the last N games -> NO season-final / season-total
  aggregate ever touches a per-game row (the documented no-season-final-features trap).
- TRAIN/INFERENCE PARITY: a SINGLE builder (``build_defender_matchup_states``) emits
  both the as-of features and the realized diagnostics from the SAME corpus rows in the
  SAME pass. There is no separate inference path that could silently read 0.0 -- the
  test asserts the column set + dtypes are identical regardless of how the frame is
  sliced, so a feature cannot drift between train and inference.
- The close / market price is NEVER a column here (it is a held-out yardstick).

HONEST EXPECTED VERDICT: **likely REJECT for the close.** Individual-defender FG%-allowed
is noisy, opponent-shot-quality-driven, and largely priced into team defense; any
single-fold/direction lift is an ARTIFACT until replicated. A truthfully-reported REJECT
is a SUCCESS. The realistic survivor, if any, is a calibrated SCOUTING signal
(archetype-conditioned matchup), not a bettable $ edge. NO $ field anywhere; this module
emits a PROPOSAL parquet only -- it does NOT write data/registry/ and flips no flag.

INVARIANTS: never edit src/ kernel/ api/; pure stdlib/pandas; no network at import;
<=300 LOC; ASCII-only stdout.
CLI: python -m domains.basketball_nba.ingest_defender_matchup_states --prior-n 10
"""
from __future__ import annotations

import argparse
import logging
from collections import deque
from pathlib import Path
from typing import Deque, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_SOURCES = (
    _REPO_ROOT / "data" / "defender_matchups_2024-25.parquet",
    _REPO_ROOT / "data" / "defender_matchups_2025-26.parquet",
)
_DEFAULT_OUT = (
    _REPO_ROOT / "data" / "domains" / "basketball_nba" / "defender_matchup_states.parquet"
)

_DEFAULT_PRIOR_N = 10

# Frozen base identity spine for the player/matchup layer.
BASE_COLS = ("game_id", "game_date", "def_player_id", "def_team_tricode")

# Additive leak-free as-of feature columns (shift1 prior-N).
ASOF_COLS = (
    "def_priorN_fg_pct_allowed_asof",
    "def_priorN_fg3_pct_allowed_asof",
    "def_priorN_pts_allowed_per36_asof",
    "def_priorN_blocks_per_game_asof",
    "def_priorN_switches_per_game_asof",
    "def_priorN_matchup_min_asof",
    "def_n_prior",
)

# Realized this-game diagnostics -- NEVER features (the as-of label surface).
DIAG_COLS = (
    "realized_fg_pct_allowed",
    "realized_fg3_pct_allowed",
    "realized_points_allowed",
    "realized_blocks_matchup",
    "realized_switches_on",
    "realized_matchup_minutes_total",
)

OUTPUT_COLS = BASE_COLS + ASOF_COLS + DIAG_COLS

# Raw corpus columns we consume.
_SRC_COLS = (
    "game_id", "game_date", "def_player_id", "def_team_tricode",
    "matchup_minutes_total", "points_allowed",
    "fg_made_allowed", "fg_attempted_allowed",
    "fg3_made_allowed", "fg3_attempted_allowed",
    "blocks_matchup", "switches_on",
)


def load_corpus(sources: Optional[List[Path]] = None) -> pd.DataFrame:
    """Read + concat the on-disk defender-matchup parquet(s). ZERO network.

    Raises FileNotFoundError if NONE of the sources exist (caller should STOP and
    report the raw corpus is not on disk rather than fabricate a win).
    """
    srcs = list(sources) if sources is not None else list(_DEFAULT_SOURCES)
    frames: List[pd.DataFrame] = []
    for sp in srcs:
        if Path(sp).exists():
            frames.append(pd.read_parquet(sp))
    if not frames:
        raise FileNotFoundError(
            "No defender_matchups_*.parquet found on disk (zero-network corpus "
            f"missing); looked in: {[str(s) for s in srcs]}"
        )
    df = pd.concat(frames, ignore_index=True)
    return df


def _prep(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce types for the columns we consume; deterministic chronological sort.

    Sort key is (game_date, game_id, def_player_id) so the walk-forward replay is
    fully deterministic and stable across runs (mergesort)."""
    out = df.copy()
    out["game_id"] = out["game_id"].astype(str)
    out["def_team_tricode"] = out["def_team_tricode"].astype(str)
    out["def_player_id"] = pd.to_numeric(out["def_player_id"], errors="coerce").astype("int64")
    out["game_date"] = pd.to_datetime(out["game_date"], errors="coerce")
    for c in (
        "matchup_minutes_total", "points_allowed",
        "fg_made_allowed", "fg_attempted_allowed",
        "fg3_made_allowed", "fg3_attempted_allowed",
        "blocks_matchup", "switches_on",
    ):
        out[c] = pd.to_numeric(out.get(c), errors="coerce").fillna(0.0).astype(float)
    out = out.sort_values(
        ["game_date", "game_id", "def_player_id"], kind="mergesort"
    ).reset_index(drop=True)
    return out


def _safe_div(num: float, den: float) -> float:
    return float(num) / float(den) if den > 0 else np.nan


def build_defender_matchup_states(
    corpus: Optional[pd.DataFrame] = None,
    sources: Optional[List[Path]] = None,
    prior_n: int = _DEFAULT_PRIOR_N,
    out_path: Optional[str] = None,
    write: bool = True,
) -> pd.DataFrame:
    """SINGLE builder (train == inference parity) -> defender-game rows with the
    frozen base + additive shift1 prior-N as-of features + realized diagnostics.

    For each row, snapshot-BEFORE-update: read the defender's prior-N rolling
    rates from ONLY their strictly-earlier games, emit them, THEN push the current
    game's realized matchup totals onto the bounded (maxlen=prior_n) deque. The
    current game can never inform its own ``*_asof`` value.
    """
    dest = Path(out_path) if out_path is not None else _DEFAULT_OUT
    df = corpus if corpus is not None else load_corpus(sources)

    if len(df) == 0:
        out = pd.DataFrame(columns=list(OUTPUT_COLS))
        if write:
            dest.parent.mkdir(parents=True, exist_ok=True)
            out.to_parquet(str(dest), index=False)
        return out

    df = _prep(df)

    # Per-defender bounded windows of the LAST prior_n games (each a realized tuple).
    # Sums kept incrementally so the snapshot is O(1) per row.
    win: Dict[int, Deque[dict]] = {}
    rows: List[dict] = []

    for r in df.itertuples(index=False):
        pid = int(r.def_player_id)
        dq = win.get(pid)
        n_prior = len(dq) if dq is not None else 0

        if n_prior == 0:
            asof = {c: np.nan for c in ASOF_COLS if c != "def_n_prior"}
        else:
            fga = sum(x["fga"] for x in dq)
            fg3a = sum(x["fg3a"] for x in dq)
            fgm = sum(x["fgm"] for x in dq)
            fg3m = sum(x["fg3m"] for x in dq)
            pts = sum(x["pts"] for x in dq)
            mins = sum(x["min"] for x in dq)
            blk = sum(x["blk"] for x in dq)
            sw = sum(x["sw"] for x in dq)
            asof = {
                "def_priorN_fg_pct_allowed_asof": _safe_div(fgm, fga),
                "def_priorN_fg3_pct_allowed_asof": _safe_div(fg3m, fg3a),
                "def_priorN_pts_allowed_per36_asof": _safe_div(pts * 36.0, mins),
                "def_priorN_blocks_per_game_asof": blk / n_prior,
                "def_priorN_switches_per_game_asof": sw / n_prior,
                "def_priorN_matchup_min_asof": mins / n_prior,
            }

        row = {
            "game_id": r.game_id,
            "game_date": r.game_date,
            "def_player_id": pid,
            "def_team_tricode": r.def_team_tricode,
            **asof,
            "def_n_prior": int(n_prior),
            # realized this-game diagnostics (NEVER features)
            "realized_fg_pct_allowed": _safe_div(r.fg_made_allowed, r.fg_attempted_allowed),
            "realized_fg3_pct_allowed": _safe_div(r.fg3_made_allowed, r.fg3_attempted_allowed),
            "realized_points_allowed": float(r.points_allowed),
            "realized_blocks_matchup": float(r.blocks_matchup),
            "realized_switches_on": float(r.switches_on),
            "realized_matchup_minutes_total": float(r.matchup_minutes_total),
        }
        rows.append(row)

        # --- UPDATE (after snapshot): push current realized game onto the window ---
        if dq is None:
            dq = deque(maxlen=max(1, int(prior_n)))
            win[pid] = dq
        dq.append({
            "fga": float(r.fg_attempted_allowed), "fgm": float(r.fg_made_allowed),
            "fg3a": float(r.fg3_attempted_allowed), "fg3m": float(r.fg3_made_allowed),
            "pts": float(r.points_allowed), "min": float(r.matchup_minutes_total),
            "blk": float(r.blocks_matchup), "sw": float(r.switches_on),
        })

    out = pd.DataFrame(rows).reindex(columns=list(OUTPUT_COLS))
    out["def_player_id"] = out["def_player_id"].astype("int64")
    out["def_n_prior"] = out["def_n_prior"].astype("int64")
    out = out.sort_values(
        ["game_date", "game_id", "def_player_id"], kind="mergesort"
    ).reset_index(drop=True)

    if write:
        dest.parent.mkdir(parents=True, exist_ok=True)
        out.to_parquet(str(dest), index=False)
    return out


def _main(argv: Optional[List[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(
        description="On-disk defender_matchups_*.parquet -> leak-free as-of defender layer.")
    ap.add_argument("--prior-n", type=int, default=_DEFAULT_PRIOR_N)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    try:
        df = build_defender_matchup_states(prior_n=args.prior_n, out_path=args.out)
    except FileNotFoundError as exc:
        print(f"BLOCKED (zero-network corpus missing): {exc}")
        return 1
    n_def = df["def_player_id"].nunique() if len(df) else 0
    n_game = df["game_id"].nunique() if len(df) else 0
    print("LEAK-FREE as-of DEFENDER-MATCHUP layer (shift1 prior-N; snapshot-before-update).")
    print("Zero-network: pure transform of on-disk defender_matchups_*.parquet.")
    print("NOT a market edge -- additive col vs the base; gate decides (expect REJECT). NO $ field.")
    print(f"rows={len(df)} defenders={n_def} games={n_game} prior_n={args.prior_n}")
    if len(df):
        print(df.head(3).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
