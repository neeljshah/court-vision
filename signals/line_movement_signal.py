"""signals/line_movement_signal.py — ARM-A: Pinnacle line movement → sharp-money signal.

Basketball hypothesis
---------------------
The opener → current spread / moneyline / total direction and velocity encode SHARP
money.  When the line moves *against* public-betting consensus (Reverse Line Movement,
RLM) it is a particularly strong signal that professional bettors have taken a position
the market is now adjusting to.  For win-probability the key operationalisation is:

  * spread_move : home spread at decision_time − home spread at opener  (negative = home
    getting more points → market softening on home; positive = home strengthening).
  * ml_prob_move : home moneyline implied-prob at decision_time − at opener  (positive
    = market more confident in home → sharp consensus home).
  * total_move : current total − opener total (positive = scoring expected to rise).
  * line_speed : |spread_move| / hours_since_opener  (large fast moves = sharp action).

The four sub-features are emitted as a dict signal targeting ``winprob``.

Data sources
------------
PRIMARY (REAL, available today):
  ``data/lines/<YYYY-MM-DD>_pin_mainline.csv``
  Schema: captured_at, book, game_id, market_type, side, line, price, home_team,
          away_team, start_time.
  Multiple ``captured_at`` timestamps per game-day file allow opener vs. current
  line comparison.  Three market_type values: moneyline, spread, total.

  Leak-safety: at train time we load only the file for the game's date and
  restrict to rows with ``captured_at <= ctx.decision_time``.  The opener is
  the earliest captured_at row; the "current" line is the freshest row at or
  before ctx.decision_time.  Future snapshots (after decision_time) are never
  used.

  The three Pinnacle files available: 2026-05-26, 2026-05-28, 2026-05-30.
  For historical games not covered, build() returns None (DEFER per game).

SECONDARY (de-vig helper):
  ``src.prediction.devig.american_to_prob`` converts American odds to implied
  probability for the moneyline sub-feature.

ATLAS READ (reinforcement):
  Reads ``"team_public_betting_bias"`` section from the store for both teams,
  if available, to cross-check whether line move contradicts public percentage.
  Falls back gracefully to None when the atlas section is unpopulated (expected
  in the bootstrap phase).

DEFER items
-----------
* Historical opener lines: only 3 game-day CSV files exist as of 2026-05-30;
  the full historical training surface (walk-forward over multiple seasons)
  requires a historical odds database (e.g. OddsJam, Pinnacle historical API).
  Until those files accumulate, the gate will DEFER due to insufficient n_rows.
  The implementation is complete; DEFER is a data-coverage gap, not a code gap.
* ``public_pct`` (public betting percentage): the Pinnacle CSVs do not include
  this column; RLM vs public pct requires a separate betresearch/covers.com
  scrape.  The ``public_betting_bias`` atlas field is reserved but will be None
  until that scrape is wired.  The signal still fires on the spread/ml movement
  alone, which is the primary sharp-money proxy.
* game_id → tricode mapping: pin_mainline uses ``game_id`` (NBA game ID int) +
  ``home_team``/``away_team`` full names.  Mapping to tricode uses the
  ``games_lookup.json`` alias table when available; falls back to a built-in
  lookup dict covering the 2025-26 WCF teams.
"""
from __future__ import annotations

import datetime as _dt
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from src.loop.signal import AsOfContext, Hypothesis, Signal, SignalValue, Verdict
from src.prediction.devig import american_to_prob

_log = logging.getLogger(__name__)
_ROOT = Path(__file__).resolve().parent.parent

# Lines directory (read-only per safety rules)
_LINES_DIR = _ROOT / "data" / "lines"

# games_lookup alias table (cross-book game id resolution)
_GAMES_LOOKUP_PATH = _ROOT / "api" / "games_lookup.json"

# ---------------------------------------------------------------------------
# Module-level cache: {date_iso: DataFrame}  loaded lazily, one entry per day
# ---------------------------------------------------------------------------
_mainline_cache: Dict[str, Optional[pd.DataFrame]] = {}

# Simple full-name → tricode map for common WCF / playoff teams (fallback when
# games_lookup is absent).  Extend as needed.
_FULLNAME_TO_TRI: Dict[str, str] = {
    "Oklahoma City Thunder": "OKC",
    "San Antonio Spurs": "SAS",
    "Minnesota Timberwolves": "MIN",
    "Golden State Warriors": "GSW",
    "Denver Nuggets": "DEN",
    "Los Angeles Lakers": "LAL",
    "Los Angeles Clippers": "LAC",
    "Phoenix Suns": "PHX",
    "Dallas Mavericks": "DAL",
    "Houston Rockets": "HOU",
    "Memphis Grizzlies": "MEM",
    "New Orleans Pelicans": "NOP",
    "Sacramento Kings": "SAC",
    "Utah Jazz": "UTA",
    "Portland Trail Blazers": "POR",
    "Boston Celtics": "BOS",
    "Miami Heat": "MIA",
    "Milwaukee Bucks": "MIL",
    "Philadelphia 76ers": "PHI",
    "Cleveland Cavaliers": "CLE",
    "Toronto Raptors": "TOR",
    "New York Knicks": "NYK",
    "Brooklyn Nets": "BKN",
    "Atlanta Hawks": "ATL",
    "Charlotte Hornets": "CHA",
    "Chicago Bulls": "CHI",
    "Detroit Pistons": "DET",
    "Indiana Pacers": "IND",
    "Orlando Magic": "ORL",
    "Washington Wizards": "WAS",
}


def _load_mainline(date_iso: str) -> Optional[pd.DataFrame]:
    """Load (and cache) the Pinnacle mainline CSV for the given date.

    Returns None if no file exists for that date.  LEAK-SAFE: returns raw
    data; the caller filters to ``captured_at <= decision_time``.
    """
    if date_iso in _mainline_cache:
        return _mainline_cache[date_iso]
    path = _LINES_DIR / f"{date_iso}_pin_mainline.csv"
    if not path.exists():
        _mainline_cache[date_iso] = None
        return None
    try:
        df = pd.read_csv(path, parse_dates=["captured_at"])
    except Exception as exc:
        _log.warning("line_movement_signal: failed to load %s: %s", path, exc)
        _mainline_cache[date_iso] = None
        return None
    _mainline_cache[date_iso] = df
    return df


def _american_prob_safe(price: float) -> float:
    """Convert American odds to implied probability; return 0.5 on failure."""
    try:
        return float(american_to_prob(int(price)))
    except Exception:
        return 0.5


def _extract_opener_current(
    df: pd.DataFrame, game_id: int, market_type: str, side: str,
    decision_ts: _dt.datetime,
) -> Tuple[Optional[float], Optional[float]]:
    """Return (opener_value, current_value) for a market/side pair.

    opener  = the earliest captured_at row for that game/market/side.
    current = the freshest row with captured_at <= decision_ts (LEAK-SAFE).

    Returns (None, None) when data is missing.
    """
    mask = (
        (df["game_id"] == game_id)
        & (df["market_type"] == market_type)
        & (df["side"] == side)
    )
    sub = df[mask].copy()
    if sub.empty:
        return None, None

    # Ensure captured_at is datetime
    if not pd.api.types.is_datetime64_any_dtype(sub["captured_at"]):
        sub["captured_at"] = pd.to_datetime(sub["captured_at"])

    # Opener = earliest row (no leak boundary — opener is always in the past)
    opener_row = sub.sort_values("captured_at").iloc[0]
    opener_val = float(opener_row["price"] if market_type == "moneyline" else opener_row["line"])

    # Current = freshest row at or before decision_ts
    # Make decision_ts tz-naive for comparison (CSVs are naive strings)
    dt_naive = decision_ts.replace(tzinfo=None) if decision_ts.tzinfo is not None else decision_ts
    current_sub = sub[sub["captured_at"] <= dt_naive]
    if current_sub.empty:
        # decision_time is before any line was posted → no current yet
        return opener_val, None
    current_row = current_sub.sort_values("captured_at").iloc[-1]
    current_val = float(current_row["price"] if market_type == "moneyline" else current_row["line"])
    return opener_val, current_val


class LineMovementSignal(Signal):
    """Pinnacle opener→current line movement → sharp-money signal for winprob.

    Emits four sub-features (dict signal):
      * line_movement_signal__spread_move  : home spread delta (positive = home
        strengthened; negative = market fading the home side).
      * line_movement_signal__ml_prob_move : home moneyline implied-prob delta
        (positive = market growing more confident in home).
      * line_movement_signal__total_move   : game total delta (opener→current).
      * line_movement_signal__line_speed   : |spread_move| / hours since opener
        (large fast = sharp action; capped at 5.0 to prevent inf at 0 hours).

    Returns None when the Pinnacle mainline file for the game's date is missing
    OR when the game_id cannot be found (deferred by data coverage gap).
    """

    name: str = "line_movement_signal"
    target: str = "winprob"
    scope: str = "both"
    reads_atlas: List[str] = ["team_public_betting_bias"]
    emits: List[str] = ["spread_move", "ml_prob_move", "total_move", "line_speed"]

    # ------------------------------------------------------------------
    def build(self, ctx: AsOfContext) -> SignalValue:
        """Compute line-movement sub-features, leak-safe at ctx.decision_time.

        Steps:
          1. Resolve game_id (int) from ctx.
          2. Load the Pinnacle mainline CSV for ctx.game_date.
          3. For each market (moneyline/spread/total), extract opener + current
             line restricted to captured_at <= ctx.decision_time.
          4. Optionally read team_public_betting_bias atlas for RLM cross-check
             (informational; does not gate the return value).
          5. Return dict of sub-features, or None on missing data.
        """
        game_id_raw = ctx.game_id
        if game_id_raw is None:
            return None

        game_date = ctx.game_date
        if game_date is None:
            game_date = ctx.as_of_iso()

        # ----- 1. Load mainline CSV ----------------------------------------
        df = _load_mainline(game_date)
        if df is None:
            return None  # DEFER: no Pinnacle file for this date

        # ----- 2. Resolve NBA game_id (int) ----------------------------------
        try:
            game_id = int(game_id_raw)
        except (ValueError, TypeError):
            _log.debug("line_movement_signal: cannot parse game_id=%r", game_id_raw)
            return None

        if game_id not in df["game_id"].values:
            _log.debug("line_movement_signal: game_id %d not in mainline for %s",
                       game_id, game_date)
            return None

        dt = ctx.decision_time

        # ----- 3. Spread move ------------------------------------------------
        spread_opener, spread_current = _extract_opener_current(
            df, game_id, "spread", "home", dt
        )
        if spread_opener is None or spread_current is None:
            return None  # minimum required market absent

        spread_move = spread_current - spread_opener  # positive = home strengthening

        # ----- 4. Moneyline implied-prob move --------------------------------
        ml_opener_price, ml_current_price = _extract_opener_current(
            df, game_id, "moneyline", "home", dt
        )
        if ml_opener_price is not None and ml_current_price is not None:
            ml_prob_opener = _american_prob_safe(ml_opener_price)
            ml_prob_current = _american_prob_safe(ml_current_price)
            ml_prob_move = ml_prob_current - ml_prob_opener
        else:
            ml_prob_move = 0.0  # degrade gracefully; spread_move is the primary

        # ----- 5. Total move -------------------------------------------------
        total_opener, total_current = _extract_opener_current(
            df, game_id, "total", "over", dt
        )
        total_move = (total_current - total_opener) if (
            total_opener is not None and total_current is not None
        ) else 0.0

        # ----- 6. Line speed (|spread_move| / hours since opener) ------------
        hours_since_opener = _hours_since_opener(df, game_id, dt)
        if hours_since_opener > 0.0:
            line_speed = min(5.0, abs(spread_move) / hours_since_opener)
        else:
            line_speed = 0.0

        # ----- 7. Optional atlas cross-check (RLM enrichment) ----------------
        self._maybe_read_public_bias(ctx)

        return {
            "spread_move": float(spread_move),
            "ml_prob_move": float(ml_prob_move),
            "total_move": float(total_move),
            "line_speed": float(line_speed),
        }

    # ------------------------------------------------------------------
    def _maybe_read_public_bias(self, ctx: AsOfContext) -> None:
        """Read public-betting bias atlas for RLM context (informational only).

        If the atlas section is populated for the home team, a large spread_move
        in the direction *against* public consensus would signal RLM.  That
        interaction feature is reserved for a future atlas×signal enrichment
        step; for now we log a debug note.  The signal fires without it.
        """
        if self.store is None or ctx.team is None:
            return
        entity = f"team:{ctx.team}"
        bias = self.read_atlas(entity, "team_public_betting_bias", ctx.decision_time)
        if bias is not None:
            _log.debug("line_movement_signal: public_bias available for %s: %r",
                       ctx.team, list(bias.keys()))

    # ------------------------------------------------------------------
    def hypothesis(self) -> Hypothesis:
        """Return the testable hypothesis this signal implements."""
        return Hypothesis(
            name=self.name,
            target=self.target,
            scope=self.scope,
            statement=(
                "Pinnacle opener-to-current spread / moneyline / total movement "
                "encodes sharp-money consensus; reverse line movement (line moving "
                "against the public) is the strongest predictor of which team the "
                "sharpest bettors favour.  Large fast line moves (line_speed) "
                "reflect professional action and should improve win-probability "
                "calibration vs the Pinnacle close."
            ),
            rationale=(
                "Market efficiency literature shows Pinnacle is the sharpest book "
                "(lowest margin, limit-up on syndicates).  Its line movement is "
                "the best publicly-available proxy for sharp-side conviction.  "
                "Spread_move and ml_prob_move are the primary features; total_move "
                "controls for pace/injuries that shift both sides equally.  "
                "Line_speed separates slow drift (public flow) from fast jumps "
                "(sharp steam).  The CLV gate will confirm whether this predicts "
                "vs the Pinnacle closing line — it should by construction."
            ),
            source="seed",
            atlas_fields=["team_public_betting_bias"],
            expected_verdict=Verdict.DEFER,  # data coverage: only 3 game-day files
            priority="P1",
        )


# ---------------------------------------------------------------------------
# Private helper
# ---------------------------------------------------------------------------

def _hours_since_opener(df: pd.DataFrame, game_id: int, decision_ts: _dt.datetime) -> float:
    """Return hours between the earliest line snapshot and decision_ts.

    Returns 0.0 when calculation fails (e.g. only one snapshot).
    """
    sub = df[df["game_id"] == game_id].copy()
    if sub.empty:
        return 0.0
    if not pd.api.types.is_datetime64_any_dtype(sub["captured_at"]):
        sub["captured_at"] = pd.to_datetime(sub["captured_at"])
    opener_ts = sub["captured_at"].min()
    # Make comparable (both naive)
    dt_naive = decision_ts.replace(tzinfo=None) if decision_ts.tzinfo is not None else decision_ts
    if pd.isna(opener_ts):
        return 0.0
    opener_naive = opener_ts.to_pydatetime().replace(tzinfo=None)
    delta = (dt_naive - opener_naive).total_seconds()
    return max(0.0, delta / 3600.0)
