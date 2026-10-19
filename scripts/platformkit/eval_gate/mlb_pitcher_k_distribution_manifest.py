"""S450 FIX 1b: starter manifest + opponent/league K-rate pools.

Split out of mlb_pitcher_k_distribution_arms.py (which was pushing the 300 LOC
rail) so the ordinal-based starter fix (AMENDMENT 2(a)) and the finite-input
K-rate fix (AMENDMENT 2(e)) have room without crowding the PMF/arm math.

ORDINAL RULE (AMENDMENT 2(a)): the starter for a (game_pk, team) is the pitcher
whose pitching line carries the SMALLEST preserved source ordinal in
ORDINAL_COL -- the appearance order the gamelog source itself records (0 =
first pitcher used). Realised inningsPitched / battersFaced are NEVER used to
rank (an opener at 1.0 IP followed by a bulk arm at 7.0 IP -> the opener is the
start). A (game_pk, team) group with no row carrying a finite ordinal is
REFUSED wholesale, counted "no_pitching_order", never a max-IP fallback -- the
real player_gamelogs.parquet corpus carries no such column today (checked this
session: the boxscore ingest records battingOrder for batters and nothing
analogous for pitchers), so a real run is expected to refuse every game until
the corpus gains one.

Run the per-file test (full pytest freezes the box):
  python -m pytest tests/platformkit/eval_gate/test_mlb_pitcher_k_distribution.py -q
"""
from __future__ import annotations

import math
from typing import Dict, Optional

import pandas as pd

ORDINAL_COL = "pitching_appearance_ordinal"
NO_PITCHING_ORDER = "no_pitching_order"
_MANIFEST_COLS = ("game_pk", "date", "team", "player_id", "battersFaced", "y")
# Exported so a caller (AMENDMENT 12(f)'s pre-charge ordinal_column_absent
# check) can confirm build_start_manifest is safe to call -- never itself
# raise KeyError -- before calling it, instead of duplicating this set.
MANIFEST_REQUIRED_COLS = frozenset(
    {"game_pk", "date", "team", "player_id", "is_pitcher", "pitch_strikeOuts"})
ORDINAL_COLUMN_ABSENT = "ordinal_column_absent"
MANIFEST_KEY_INVALID = "manifest_key_invalid"


def manifest_columns_refusal(gamelogs_df: pd.DataFrame) -> Optional[str]:
    """AMENDMENT 12(f)/13(b)/15(b): the CLI's pre-charge guard as one call,
    so main() stays thin. Refuses ordinal_column_absent when ORDINAL_COL is
    absent, when any MANIFEST_REQUIRED_COLS column other than "date" is
    absent (round 12's finding: ORDINAL_COL present but pitch_strikeOuts
    absent used to be charged, then build_start_manifest raised KeyError),
    or when the manifest would be empty. Refuses manifest_key_invalid when a
    pitcher row's game_pk or team is NaN -- checked BEFORE the self-test call
    below, which would otherwise raise (build_start_manifest's own groupby
    drops a NaN key, leaving a non-boolean NaN in the transform result: a
    TypeError, never a named refusal). A missing "date" ALONE is not decided
    here -- the caller's corpus-bound check owns that
    (holdout_b_end_mismatch)."""
    missing_required = (MANIFEST_REQUIRED_COLS - {"date"}) - set(gamelogs_df.columns)
    if ORDINAL_COL not in gamelogs_df.columns or missing_required:
        return ORDINAL_COLUMN_ABSENT
    if {"is_pitcher", "game_pk", "team"} <= set(gamelogs_df.columns):
        pit_keys = gamelogs_df.loc[gamelogs_df["is_pitcher"] == True, ["game_pk", "team"]]  # noqa: E712
        if pit_keys.isna().any().any():
            return MANIFEST_KEY_INVALID
    if "date" in gamelogs_df.columns and len(build_start_manifest(gamelogs_df)[0]) == 0:
        return ORDINAL_COLUMN_ABSENT
    return None


def coerce_count(value: object) -> "tuple[Optional[int], Optional[str]]":
    """Strict-int coercion for a COUNT field (RAILS a). (int, None) or
    (None, reason). Bool, non-integer float and numeric strings are refused,
    never silently coerced."""
    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            return None, "unrecoverable_scalar"
    if value is None:
        return None, "missing"
    if isinstance(value, bool):
        return None, "bool_not_count"
    if isinstance(value, str):
        return None, "numeric_string_not_count"
    if isinstance(value, float):
        if not math.isfinite(value):
            return None, "non_finite"
        if value != math.floor(value):
            return None, "non_integer_float"
        value = int(value)
    if isinstance(value, int):
        if value < 0:
            return None, "negative"
        return value, None
    return None, "unsupported_type"


def battersfaced_missing(value: object) -> bool:
    """True when battersFaced is missing or nonpositive (AMENDMENT 1(c): such
    rows are KEPT in the manifest and scored with projected exposure, never
    dropped or treated as an outcome)."""
    if hasattr(value, "item"):
        try:
            value = value.item()
        except Exception:
            return True
    if value is None:
        return True
    try:
        v = float(value)
    except (TypeError, ValueError):
        return True
    return (not math.isfinite(v)) or v <= 0.0


STARTER_CONFLICT = "starter_conflict"
_DERIVED_HELPER_COLS = frozenset({"_ordinal", "_finite"})


def _row_signature(row: "pd.Series") -> tuple:
    """The manifest-relevant byte identity of one eligible row (AMENDMENT
    15(b)): every ORIGINAL source column counts (excluding only the derived
    helper columns this module itself adds), never a fixed subset -- a
    difference in ANY source field (e.g. inningsPitched) is a real conflict.
    NaN is mapped to a sentinel string so two NaNs compare equal by content,
    never by float object identity; None is left as bare None, so None and
    NaN are never mistaken for the same value (both still count against a
    differing value, per AMENDMENT 15(b))."""
    cols = sorted(c for c in row.index if c not in _DERIVED_HELPER_COLS)
    vals = []
    for col in cols:
        v = row.get(col)
        vals.append("__nan__" if isinstance(v, float) and math.isnan(v) else v)
    return tuple(vals)


def _resolve_starters(eligible: pd.DataFrame) -> "tuple[pd.DataFrame, Dict[str, int]]":
    """AMENDMENT 14(b): order-independent starter selection. Per (game_pk,
    team), the candidates at the MINIMUM finite ordinal are taken; if they
    are all byte-equivalent (a duplicate row) they collapse to one, else the
    group is a genuine conflict -- refused ``starter_conflict`` (counted)
    and excluded -- never an unstable-sort coin flip on a tied ordinal."""
    starter_rows, conflicts = [], 0
    for _, group in eligible.groupby(["game_pk", "team"], sort=False):
        candidates = group.loc[group["_ordinal"] == group["_ordinal"].min()]
        signatures = {_row_signature(r) for _, r in candidates.iterrows()}
        if len(signatures) == 1:
            starter_rows.append(candidates.iloc[0])
        else:
            conflicts += 1
    starters = pd.DataFrame(starter_rows) if starter_rows else eligible.iloc[0:0]
    refusals = {STARTER_CONFLICT: conflicts} if conflicts else {}
    return starters, refusals


def build_start_manifest(gamelogs_df: pd.DataFrame) -> "tuple[pd.DataFrame, Dict[str, int]]":
    """One row per (game_pk, team): the pitcher with the smallest preserved
    source ordinal, timestamp-free (AMENDMENT 1(c)/2(a)) -- no probables
    snapshot, no K outcome used to pick the starter. Rows with missing or
    nonpositive battersFaced are KEPT, never dropped. Returns
    (manifest_df, refusal_counts) -- refusal_counts names "no_pitching_order"
    when one or more (game_pk, team) groups carry no finite ordinal, and
    "manifest_key_invalid" (AMENDMENT 15(b)) when a pitcher row's game_pk or
    team is NaN. Never raises for either reason."""
    missing = MANIFEST_REQUIRED_COLS - set(gamelogs_df.columns)
    if missing:
        raise KeyError(f"gamelogs_df missing columns: {sorted(missing)}")
    pit = gamelogs_df.loc[gamelogs_df["is_pitcher"] == True].copy()  # noqa: E712
    if len(pit) == 0:
        return pd.DataFrame(columns=list(_MANIFEST_COLS)), {}

    # AMENDMENT 15(b): a NaN game_pk or team can never form a groupby key --
    # pandas silently drops such rows from the group, leaving a non-boolean
    # NaN in the "has_ordinal" transform below and a TypeError at `~`. Refuse
    # those rows by name, counted, before they ever reach the groupby.
    key_invalid = pit["game_pk"].isna() | pit["team"].isna()
    n_key_invalid = int(key_invalid.sum())
    pit = pit.loc[~key_invalid]
    refusals: Dict[str, int] = {MANIFEST_KEY_INVALID: n_key_invalid} if n_key_invalid else {}
    if len(pit) == 0:
        return pd.DataFrame(columns=list(_MANIFEST_COLS)), refusals

    if ORDINAL_COL in pit.columns:
        ordinal = pd.to_numeric(pit[ORDINAL_COL], errors="coerce")
    else:
        ordinal = pd.Series(float("nan"), index=pit.index)
    # AMENDMENT 3(a): NaN, +inf and -inf all refuse as no_pitching_order --
    # notna() alone treats +-inf as a "known" ordinal, which is wrong.
    finite_ordinal = ordinal.apply(math.isfinite)
    pit = pit.assign(_ordinal=ordinal, _finite=finite_ordinal)

    has_ordinal = pit.groupby(["game_pk", "team"])["_finite"].transform("any")
    refused_groups = pit.loc[~has_ordinal, ["game_pk", "team"]].drop_duplicates()
    if len(refused_groups):
        refusals = {**refusals, NO_PITCHING_ORDER: int(len(refused_groups))}

    eligible = pit.loc[has_ordinal & pit["_finite"]].copy()
    if len(eligible) == 0:
        return pd.DataFrame(columns=list(_MANIFEST_COLS)), refusals

    starters, conflict_refusals = _resolve_starters(eligible)
    refusals = {**refusals, **conflict_refusals}
    if len(starters) == 0:
        return pd.DataFrame(columns=list(_MANIFEST_COLS)), refusals
    if "battersFaced" not in starters.columns:
        starters = starters.assign(battersFaced=None)
    out = starters[["game_pk", "date", "team", "player_id", "battersFaced",
                    "pitch_strikeOuts"]].rename(columns={"pitch_strikeOuts": "y"})
    return out.sort_values(["date", "game_pk", "team"]).reset_index(drop=True), refusals


def opponent_team(gamelogs_df: pd.DataFrame, game_pk, team) -> Optional[str]:
    """The other team in this game_pk, or None if the game has zero or more
    than two distinct teams on record (bad or incomplete data -> abstain)."""
    teams = gamelogs_df.loc[gamelogs_df["game_pk"] == game_pk, "team"]
    others = sorted(set(teams.astype(str)) - {str(team)})
    return others[0] if len(others) == 1 else None


def _pool_k_rate(gamelogs_df: pd.DataFrame, as_of, team: Optional[str]) -> Optional[float]:
    """Pooled batter strikeOuts/atBats, rows strictly before as_of. team=None
    pools the whole league; a team pools only that team's own batting rows.
    AMENDMENT 3(c): the pool is ALL-OR-NOTHING -- if ANY selected row's (K, AB)
    pair is missing, non-finite or negative, the WHOLE pool is unavailable
    (None), never a rate computed from the remaining valid rows and never
    fillna(0)'d. A pool with zero rows is likewise unavailable, not NaN.
    AMENDMENT 12(b): each K/AB value must be a non-negative int or an
    integral finite float (reuses ``coerce_count``, the same strict-COUNT
    coercion the manifest's own "y" already uses) -- a fractional value (a
    parquet count column can arrive as float64), a bool, NaN, inf or a
    negative rejects the WHOLE pool for this row, never a partial aggregate
    over the remaining valid rows."""
    ts = pd.Timestamp(as_of)
    dates = pd.to_datetime(gamelogs_df["date"], errors="coerce")
    mask = dates.notna() & (dates < ts) & (gamelogs_df["is_pitcher"] == False)  # noqa: E712
    if team is not None:
        mask &= gamelogs_df["team"].astype(str) == str(team)
    rows = gamelogs_df.loc[mask]
    if len(rows) == 0 or "atBats" not in rows.columns or "strikeOuts" not in rows.columns:
        return None
    ab_total = 0
    k_total = 0
    for ab_raw, k_raw in zip(rows["atBats"], rows["strikeOuts"]):
        ab_val, ab_reason = coerce_count(ab_raw)
        k_val, k_reason = coerce_count(k_raw)
        if ab_reason is not None or k_reason is not None:
            return None
        ab_total += ab_val
        k_total += k_val
    if ab_total <= 0:
        return None
    rate = k_total / ab_total
    return rate if math.isfinite(rate) else None


def opp_k_rate_as_of(gamelogs_df: pd.DataFrame, opp_team: Optional[str], as_of) -> Optional[float]:
    if opp_team is None:
        return None
    return _pool_k_rate(gamelogs_df, as_of, opp_team)


def league_k_rate_as_of(gamelogs_df: pd.DataFrame, as_of) -> Optional[float]:
    return _pool_k_rate(gamelogs_df, as_of, None)
