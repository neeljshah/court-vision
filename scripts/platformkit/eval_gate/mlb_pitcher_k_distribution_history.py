"""S450 FIX 1o: pitcher-history validation, mirroring the SERVED CONSUMER's
own row selection exactly (AMENDMENT 15(a)).

Split out of mlb_pitcher_k_distribution_fit.py (at the 300 LOC rail) so the
consumer-mirrored guard has room without crowding the fold-level fit/score
loop.

domains/mlb/player_rates_mlb.pitcher_rate sums TWO pools that this guard
must validate identically, never `is_pitcher == True`:
  - OWN rows: selected by player_id ALONE (_own_rows, player_rates_mlb.py
    :142-145) -- every one of this player's own rows contributes its raw
    pitch_strikeOuts/battersFaced (fillna(0.0)) regardless of is_pitcher.
  - LEAGUE rows: selected by is_pitcher.fillna(False).astype(bool)
    (player_rates_mlb.py:189) -- ANY truthy is_pitcher (2, "True", "1", a
    real numpy bool True) counts a row in, never only Python's `is True`.

Run the per-file test (full pytest freezes the box):
  python -m pytest tests/platformkit/eval_gate/test_mlb_pitcher_k_distribution_fix1o.py -q
"""
from __future__ import annotations

from typing import Dict, Tuple

import pandas as pd

from scripts.platformkit.eval_gate.mlb_pitcher_k_distribution_manifest import coerce_count

PITCHER_HISTORY_INVALID = "pitcher_history_invalid"
_REQUIRED_COUNT_COLS = ("pitch_strikeOuts", "battersFaced")

# AMENDMENT 15(a): memoised per (id(df), as_of) -- computed once per corpus
# and cut, never once per scored row. Module-global cache is deliberate: the
# CLI process scores one corpus per run; a stale id(df) can only collide
# after garbage collection frees a prior df, which never happens mid-run.
# AMENDMENT 16(b): the cached df ITSELF is stored alongside its verdict (not
# just its id) so (1) holding a reference keeps that id from being freed and
# reused for the lifetime of the entry, and (2) a lookup can confirm identity
# with `is` before trusting a hit -- a foreign df that lands on the same
# id(df) key (e.g. a freed frame's id reused by a new one) is never trusted.
_memo: Dict[Tuple[int, str], "Tuple[pd.DataFrame, bool, frozenset]"] = {}


def clear_memo() -> None:
    """FIX 1q (verdict finding 1): the memo above pins every scored frame's
    id(df) reference for the process lifetime -- never evicted, so it grows
    without bound across repeated build_report calls (3 calls measured
    75/150/225 entries, 41/82/123 distinct frames pinned). The caller
    (build_report) clears it at the start of every report and again in a
    finally, so no frame outlives the report that scored it."""
    _memo.clear()


def _native(value: object) -> object:
    """Unwrap a numpy scalar to its native Python type (mirrors coerce_count's
    own ``hasattr(value, "item")`` pattern) so a real bool-dtype column's
    np.bool_ values compare equal to Python True/False, while non-boolean
    values (2, "True", "1", pd.NA) still fail the exact-bool check below."""
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return value
    return value


def _own_row_invalid(is_pitcher_value: object, row: "pd.Series") -> bool:
    """AMENDMENT 15(a): an own-player_id row whose is_pitcher is not exactly
    bool True or False is invalid regardless of its counts (ambiguous --
    cannot tell whether this was a real pitching turn). bool False (two-way
    batting lines, 0/0 neutral) is exempt from count validation. bool True
    requires finite/integral pitch_strikeOuts and battersFaced."""
    v = _native(is_pitcher_value)
    if v is False:
        return False
    if not isinstance(v, bool):
        return True
    for col in _REQUIRED_COUNT_COLS:
        if coerce_count(row.get(col))[1] is not None:
            return True
    return False


def _compute_invalid_sets(df: pd.DataFrame, as_of) -> "Tuple[bool, frozenset]":
    """One pass over rows strictly before ``as_of`` (AMENDMENT 1(b): a bad
    row on or after as_of has no effect). Returns (league_bad, own_bad_ids):
    league_bad is True when any is_pitcher-truthy row anywhere in the corpus
    has a non-finite/non-integral count (poisons the shared league baseline
    for every later forecast, AMENDMENT 15(a)'s corpus-wide exposure);
    own_bad_ids names every player_id whose OWN history contains an invalid
    row."""
    dates = pd.to_datetime(df["date"], errors="coerce")
    prior = df.loc[dates.notna() & (dates < pd.Timestamp(as_of))]
    if "is_pitcher" not in prior.columns:
        return False, frozenset()

    league_mask = prior["is_pitcher"].fillna(False).astype(bool)
    league_bad = False
    for _, row in prior.loc[league_mask].iterrows():
        for col in _REQUIRED_COUNT_COLS:
            if coerce_count(row.get(col))[1] is not None:
                league_bad = True
                break
        if league_bad:
            break

    own_bad_ids = set()
    if "player_id" in prior.columns:
        for pid, group in prior.groupby(prior["player_id"].astype(str)):
            for _, row in group.iterrows():
                if _own_row_invalid(row.get("is_pitcher"), row):
                    own_bad_ids.add(pid)
                    break
    return league_bad, frozenset(own_bad_ids)


def pitcher_history_invalid(df: pd.DataFrame, as_of, player_id) -> bool:
    """AMENDMENT 15(a)/16(a): True when this forecast's history is unsafe to
    sum -- a missing pitch_strikeOuts/battersFaced COLUMN (checked FIRST,
    corpus-wide, not memoised: cheap and as_of-independent, and BEFORE the
    empty-frame/dateless early return below -- an empty or dateless frame
    still names a missing required column as invalid, never silently False),
    OR the shared league pool is poisoned (league_bad), OR this player's OWN
    rows contain an ambiguous/invalid is_pitcher value or bad counts
    (own_bad). Never itself raises; ``df`` with no rows or no date column,
    once both required columns are present, is trivially not invalid
    (nothing to poison it with)."""
    if df is None:
        return False
    for col in _REQUIRED_COUNT_COLS:
        if col not in df.columns:
            return True
    if len(df) == 0 or "date" not in df.columns:
        return False
    key = (id(df), str(as_of))
    cached = _memo.get(key)
    if cached is not None and cached[0] is df:
        _, league_bad, own_bad_ids = cached
    else:
        # AMENDMENT 16(b): a hit whose stored frame is NOT `df` (a stale/
        # foreign entry parked under a colliding id(df) key) is never
        # trusted -- fall through and recompute for the real df.
        league_bad, own_bad_ids = _compute_invalid_sets(df, as_of)
        _memo[key] = (df, league_bad, own_bad_ids)
    return league_bad or (str(player_id) in own_bad_ids)
