"""scripts.platformkit.ingame.mlb_games_outcome_fallback -- S91: a SECOND
on-disk MLB outcome source, shaped like the ESPN box parquet.

THE GAP (S91): data/domains/mlb/espn_boxscores.parquet was truncated to 2 rows
(2026-07-14 / 07-16) by domains/mlb/ingest_espn_box.ingest_range's
"Could not read existing parquet -- overwriting" branch, so
ingame_outcome_label.MlbOutcomeResolver resolved 1 of the 235 captured Kalshi
MLB tickers and the scored tick store (data/cache/ingame_grade_joined/mlb)
could not be re-joined from raw. Re-fetching ESPN is Neel's S62 decision, so
this module supplies the outcome from data ALREADY on disk instead.

WHAT IT DOES: reads data/domains/mlb/games{,_current}.parquet (final run
totals, 39,162 rows, 2010-04-04..2026-07-12) and returns them in the box
parquet's own column shape (event_id/date/status/home_abbr/away_abbr/
home_score/away_score/start_time) so a resolver can ingest it unchanged.

TWO DELIBERATE NARROWINGS (both measured, see
docs/evidence/harness/S91_mlb_outcome_source_2026-09-03.md):
  * team codes are mapped to ESPN abbrs and any row whose mapped code is not
    one of the 30 current franchises is DROPPED -- games.parquet carries relic
    codes (LOS 2010-2017, BRS/SFG/CHC one-offs in 2020) that would otherwise
    widen the ticker tail-split alphabet and could make a split ambiguous.
  * start_time is EMPTY. games.parquet has no clock, so a doubleheader key
    (2 rows) fails CLOSED in the resolver rather than guessing -- and the
    caller must apply these rows on the ticker's EXACT date only: the +1/-1
    day tolerances in MlbOutcomeResolver._resolve exist for ESPN's UTC-dated
    rows, and applied here they mislabelled KXMLBGAME-26JUL071415MILSTLG1
    with the 2026-07-08 game's result (measured: 1 wrong label out of 225).

HONESTY: realized final scores only; no $/ROI/edge field; never writes
data/registry/; never raises out of load_games_box_frame.

Per-file test:
  python -m pytest scripts/platformkit/ingame/test_mlb_games_outcome_fallback.py -q
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MLB_DIR = _REPO_ROOT / "data" / "domains" / "mlb"
DEFAULT_GAMES_PARQUETS: Sequence[Path] = (
    _MLB_DIR / "games.parquet", _MLB_DIR / "games_current.parquet")

# games.parquet team code -> ESPN box abbr, ONLY where they differ.
GAMES_TO_ESPN: Dict[str, str] = {
    "CUB": "CHC", "CWS": "CHW", "KAN": "KC", "SDG": "SD", "SFO": "SF",
    "TAM": "TB", "WAS": "WSH", "OAK": "ATH", "LOS": "LAD", "SFG": "SF",
}
# The 30 current franchises in ESPN abbr space. A mapped code outside this set
# is a relic row and is dropped (see module docstring).
CURRENT_ABBRS = frozenset((
    "ARI", "ATH", "ATL", "BAL", "BOS", "CHC", "CHW", "CIN", "CLE", "COL",
    "DET", "HOU", "KC", "LAA", "LAD", "MIA", "MIL", "MIN", "NYM", "NYY",
    "PHI", "PIT", "SD", "SEA", "SF", "STL", "TB", "TEX", "TOR", "WSH"))

_BOX_COLS = ("event_id", "date", "status", "home_abbr", "away_abbr",
             "home_score", "away_score", "start_time")


def _abbr(code: Any) -> str:
    c = str(code or "").strip().upper()
    return GAMES_TO_ESPN.get(c, c)


def load_games_box_frame(paths: Optional[Sequence[Path]] = None) -> Optional[Any]:
    """games{,_current}.parquet as an espn_boxscores-shaped DataFrame, or None
    if nothing on disk parses. status is always STATUS_FINAL (games.parquet
    holds finals only) and start_time is always "". Never raises."""
    try:
        import pandas as pd
    except Exception as exc:  # noqa: BLE001 -- no pandas -> no fallback, not fatal
        logger.debug("load_games_box_frame: pandas unavailable: %s", exc)
        return None
    frames: List[Any] = []
    for p in (paths if paths is not None else DEFAULT_GAMES_PARQUETS):
        try:
            d = pd.read_parquet(p)
        except Exception as exc:  # noqa: BLE001 -- a missing/bad file is skipped
            logger.debug("load_games_box_frame: %s unreadable: %s", p, exc)
            continue
        need = {"event_id", "date", "home_team", "away_team",
                "home_runs", "away_runs"}
        if not need.issubset(set(d.columns)):
            logger.debug("load_games_box_frame: %s missing %s", p,
                         sorted(need - set(d.columns)))
            continue
        home = d["home_team"].map(_abbr)
        away = d["away_team"].map(_abbr)
        keep = home.isin(CURRENT_ABBRS) & away.isin(CURRENT_ABBRS)
        frames.append(pd.DataFrame({
            "event_id": d["event_id"].astype(str),
            "date": pd.to_datetime(d["date"], errors="coerce"),
            "status": "STATUS_FINAL",
            "home_abbr": home, "away_abbr": away,
            "home_score": pd.to_numeric(d["home_runs"], errors="coerce"),
            "away_score": pd.to_numeric(d["away_runs"], errors="coerce"),
            "start_time": "",
        })[keep.values])
    if not frames:
        return None
    out = pd.concat(frames, ignore_index=True)
    out = out.dropna(subset=["date", "home_score", "away_score"])
    return out[list(_BOX_COLS)] if len(out) else None


__all__ = ["CURRENT_ABBRS", "DEFAULT_GAMES_PARQUETS", "GAMES_TO_ESPN",
           "load_games_box_frame"]
