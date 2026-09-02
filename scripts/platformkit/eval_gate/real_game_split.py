"""S106 -- split a re-used in-game `game_id` into its real games.

THE DEFECT (S105 filed it, this module measures and repairs it downstream):
`data/cache/ingame_grade/mlb` is keyed by KALSHI TICKER, and the capture loop
bridges a live game onto a ticker BY TEAM PAIR with no date check
(`inplay_capture_loop._process_game` -> `_scan_live_by_legs`).  A NYM@ATL series
therefore parks several nights of ticks under ONE ticker, e.g.
`KXMLBGAME-26JUL061915NYMATL` carries 2026-07-05 (inning 2, 3-5) and
2026-07-07 (inning 10, 6-7) ticks.  `ticker_settlement_join` is a faithful 1:1
copy of that file, so the joined store inherits the defect and every MLB in-game
denominator is quoted against a cluster unit that is not one real game.

THE SPLIT (pure, no I/O): within one `game_id`, in tick order, a new real game
starts at any of
  (a) an INNING RESET   -- the inning decreases (a return to inning 1 after an
      inning >= 2 IS this case: the previous in-play tick of the segment always
      carries the higher inning, so no separate rule is reachable);
  (b) a TIME GAP        -- more than `gap_hours` between consecutive in-play ticks;
  (c) a SCORE RESET     -- back to 0-0 after a non-zero score.
A tick with no parsed state (no inning) never opens or closes a segment: it
inherits the current `real_game_seq` (missing is not bad -- contract B3).

USE: cluster = (game_id, real_game_seq).  Nothing here recomputes a model, a
label or a price; it only re-labels the cluster unit a CI is quoted against.

Per-file test:
  python -m pytest scripts/platformkit/eval_gate/test_real_game_split.py -q
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

DEFAULT_GAP_HOURS = 5.0

_INNING_RE = re.compile(r"inning=(\d+)")
_HOME_RE = re.compile(r"home_score=(-?[\d.]+)")
_AWAY_RE = re.compile(r"away_score=(-?[\d.]+)")


def parse_state(summary: Any) -> Tuple[Optional[int], Optional[float], Optional[float]]:
    """(inning, home_score, away_score) out of a `state_summary` string.

    Every field is independently optional: a summary with a score but no inning
    yields (None, h, a).  Never raises -- an unparseable summary is all-None,
    which the splitter treats as "no state", not as a boundary."""
    text = "" if summary is None else str(summary)
    m = _INNING_RE.search(text)
    inning = int(m.group(1)) if m else None
    mh, ma = _HOME_RE.search(text), _AWAY_RE.search(text)

    def _f(match: Optional[Any]) -> Optional[float]:
        if match is None:
            return None
        try:
            return float(match.group(1))
        except ValueError:
            return None

    return inning, _f(mh), _f(ma)


def _ts(value: Any) -> Optional[datetime]:
    """Parse an ISO-Z timestamp; None on anything unparseable (never raises)."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None


def _boundary(prev: Dict[str, Any], inning: Optional[int], home: Optional[float],
              away: Optional[float], stamp: Optional[datetime], gap_hours: float
              ) -> Optional[str]:
    """Reason this in-play tick starts a NEW real game, or None to continue."""
    if prev["inning"] is not None and inning is not None and inning < prev["inning"]:
        return "inning_decrease"
    if (stamp is not None and prev["ts"] is not None
            and (stamp - prev["ts"]).total_seconds() > gap_hours * 3600.0):
        return "ts_gap"
    if home == 0.0 and away == 0.0 and prev["nonzero_score"]:
        return "score_reset"
    return None


def assign_real_game_seq(frame: pd.DataFrame, *, game_col: str = "game_id",
                         ts_col: str = "ts", state_col: str = "state_summary",
                         gap_hours: float = DEFAULT_GAP_HOURS,
                         out_col: str = "real_game_seq",
                         ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Return (copy of *frame* with `real_game_seq`, summary).

    `real_game_seq` is 1-based within each `game_col`, assigned in tick order
    (rows are sorted by `ts_col` within the group, stably).  The returned frame
    keeps the caller's original row order.  Pure: *frame* is not modified.

    Summary: n_game_ids, n_real_games, n_multi (game_ids holding more than one
    real game), n_ticks, n_ticks_reassigned (ticks landing in seq >= 2), and
    boundary_reasons (a count per rule that fired).
    """
    for name in (game_col, ts_col, state_col):
        if name not in frame.columns:
            raise ValueError("missing required column: %s" % name)
    out = frame.copy()
    order: List[Any] = out.index.to_list()
    work = out.assign(_ts_parsed=[_ts(v) for v in out[ts_col]])
    work = work.sort_values([game_col, "_ts_parsed"], kind="stable")

    seqs: Dict[Any, int] = {}
    reasons: Dict[str, int] = {}
    per_game: Dict[str, int] = {}
    current_gid: Any = object()
    prev: Dict[str, Any] = {}
    seq = 0
    for idx, gid, stamp, summary in zip(work.index, work[game_col].astype(str),
                                        work["_ts_parsed"], work[state_col]):
        if gid != current_gid:
            current_gid, seq = gid, 1
            prev = {"inning": None, "ts": None, "nonzero_score": False}
        inning, home, away = parse_state(summary)
        if inning is None:  # no state -> inherits the current segment (contract B3)
            seqs[idx] = seq
            per_game[gid] = max(per_game.get(gid, 0), seq)
            continue
        reason = _boundary(prev, inning, home, away, stamp, gap_hours)
        if reason is not None:
            seq += 1
            reasons[reason] = reasons.get(reason, 0) + 1
            prev = {"inning": None, "ts": None, "nonzero_score": False}
        prev["inning"] = inning
        if stamp is not None:
            prev["ts"] = stamp
        if (home or 0.0) != 0.0 or (away or 0.0) != 0.0:
            prev["nonzero_score"] = True
        seqs[idx] = seq
        per_game[gid] = max(per_game.get(gid, 0), seq)

    out[out_col] = [seqs[i] for i in order]
    summary: Dict[str, Any] = {
        "n_game_ids": int(len(per_game)),
        "n_real_games": int(sum(per_game.values())),
        "n_multi": int(sum(1 for v in per_game.values() if v > 1)),
        "n_ticks": int(len(out)),
        "n_ticks_reassigned": int((out[out_col] > 1).sum()),
        "gap_hours": float(gap_hours),
        "boundary_reasons": reasons,
    }
    return out, summary


def cluster_ids(frame: pd.DataFrame, *, game_col: str = "game_id",
                out_col: str = "real_game_seq") -> pd.Series:
    """`game_id#seq` -- the corrected cluster label a DM/ESS quote groups by."""
    return frame[game_col].astype(str) + "#" + frame[out_col].astype(int).astype(str)


def demo() -> None:  # pragma: no cover -- manual smoke
    rows: List[Dict[str, Any]] = [
        {"game_id": "T", "ts": "2026-07-05T00:00:00Z", "state_summary": "home_score=0 away_score=0 inning=1"},
        {"game_id": "T", "ts": "2026-07-05T02:00:00Z", "state_summary": "home_score=2 away_score=3 inning=7"},
        {"game_id": "T", "ts": "2026-07-06T01:00:00Z", "state_summary": "home_score=0 away_score=0 inning=1"},
        {"game_id": "T", "ts": "2026-07-06T03:00:00Z", "state_summary": ""},
    ]
    frame, summary = assign_real_game_seq(pd.DataFrame(rows))
    assert list(frame["real_game_seq"]) == [1, 1, 2, 2], list(frame["real_game_seq"])
    assert summary["n_real_games"] == 2 and summary["n_multi"] == 1, summary
    print("real_game_split demo OK: %s" % summary)


if __name__ == "__main__":  # pragma: no cover
    demo()


__all__ = ["DEFAULT_GAP_HOURS", "parse_state", "assign_real_game_seq", "cluster_ids"]
