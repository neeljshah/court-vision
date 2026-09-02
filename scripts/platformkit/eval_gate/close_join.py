"""Read-only decimal-close join for gate corpora; calibration evidence only."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from kernel.validation.proof_metrics import devig2
from scripts.platformkit.combo.corpus_cache import load_gate_corpus

_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class JoinSpec:
    """Columns and outcome orientation for one sport's two-sided close."""

    sport: str
    spine: str
    date_col: str
    side_a: str
    side_b: str
    fallback_a: str
    fallback_b: str
    name_a: str
    name_b: str


_SPECS = {
    "soccer": JoinSpec(
        sport="soccer", spine="event_id", date_col="date",
        side_a="ou_close_over", side_b="ou_close_under",
        fallback_a="avgc_over", fallback_b="avgc_under",
        name_a="over25", name_b="under25",
    ),
}


def _spec(sport: str) -> JoinSpec:
    try:
        return _SPECS[sport]
    except KeyError as exc:
        raise ValueError(f"unsupported close join sport: {sport!r}") from exc


def _number(frame: pd.DataFrame, primary: str, fallback: str) -> pd.Series:
    if primary not in frame:
        raise KeyError(f"missing close column: {primary}")
    value = pd.to_numeric(frame[primary], errors="coerce")
    if fallback in frame:
        value = value.where(value.notna(), pd.to_numeric(frame[fallback], errors="coerce"))
    return value.astype(float)


def close_column(odds: pd.DataFrame, spec: JoinSpec) -> pd.Series:
    """Return fair probability for ``name_a`` and expose all close-drop counts."""
    price_a = _number(odds, spec.side_a, spec.fallback_a)
    price_b = _number(odds, spec.side_b, spec.fallback_b)
    missing = price_a.isna() | price_b.isna()
    invalid = (~missing) & (
        ~np.isfinite(price_a) | ~np.isfinite(price_b) | (price_a <= 1.0) | (price_b <= 1.0)
    )
    valid = ~(missing | invalid)
    result = pd.Series(np.nan, index=odds.index, dtype=float, name="devig_close_prob")
    result.loc[valid] = [
        devig2(float(a), float(b))[0] for a, b in zip(price_a.loc[valid], price_b.loc[valid])
    ]
    result.attrs = {
        "bad_price_drop_count": int(invalid.sum()),
        "null_close_count": int(missing.sum()),
        "valid_close_count": int(valid.sum()),
    }
    return result


def _paths(sport: str) -> tuple[Path, Path]:
    base = _ROOT / "data" / "domains" / sport
    return base / "odds.parquet", base / "matches.parquet"


def _joined(sport: str, start: str | None = None, end: str | None = None) -> tuple[pd.DataFrame, dict[str, int]]:
    spec = _spec(sport)
    odds_path, matches_path = _paths(sport)
    if not odds_path.exists() or not matches_path.exists():
        raise FileNotFoundError(f"missing local close inputs: {odds_path} or {matches_path}")
    odds = pd.read_parquet(odds_path).copy()
    matches = pd.read_parquet(matches_path)
    corpus = load_gate_corpus(sport).copy()
    odds[spec.date_col] = pd.to_datetime(odds[spec.date_col], errors="raise")
    if start is not None:
        odds = odds.loc[odds[spec.date_col] >= pd.Timestamp(start)].copy()
    if end is not None:
        odds = odds.loc[odds[spec.date_col] <= pd.Timestamp(end)].copy()
    for name, frame in (("odds", odds), ("matches", matches), ("corpus", corpus)):
        if frame[spec.spine].duplicated().any():
            raise ValueError(f"duplicate {spec.spine} in {name}")
    close = close_column(odds, spec)
    counts = dict(close.attrs)
    odds = odds[[spec.spine, spec.date_col]].copy()
    odds["devig_close_prob"] = close
    match_fields = [spec.spine, "home_team", "away_team"]
    joined = odds.merge(matches[match_fields], on=spec.spine, how="left", validate="one_to_one")
    joined = joined.merge(
        corpus[[spec.spine, "corpus_unit", "y", "p_base"]], on=spec.spine,
        how="left", validate="one_to_one", indicator="_spine_join",
    )
    return joined, counts


def gate_corpus_states(sport: str, start: str, end: str) -> list[dict]:
    """Build vintage-safe pregame states carrying a devigged decimal close."""
    joined, _ = _joined(sport, start, end)
    ready = joined.loc[
        joined["_spine_join"].eq("both")
        & joined["devig_close_prob"].notna()
        & joined["y"].notna()
        & joined["p_base"].notna()
    ].sort_values("date")
    states: list[dict] = []
    for row in ready.itertuples(index=False):
        day = pd.Timestamp(row.date).date().isoformat()
        states.append({
            "game_id": str(row.event_id), "season": str(day[:4]), "sport": sport,
            "regime": "pregame", "game_date": day, "state_ts": f"{day}T12:00:00",
            "home": str(row.home_team), "away": str(row.away_team),
            "features": {"p_base": float(row.p_base)},
            "feature_avail": {"p_base": f"{day}T00:00:00"},
            "devig_close_prob": float(row.devig_close_prob), "truth_wp": float(row.y),
            "outcome": int(row.y),
        })
    return states


def _rate(numerator: int, denominator: int) -> float:
    return float(numerator / denominator) if denominator else 0.0


def coverage_report(sport: str) -> dict[str, Any]:
    """Report join coverage with all odds rows retained in its denominator."""
    joined, drops = _joined(sport)
    denominator = len(joined)
    matched = joined["_spine_join"].eq("both")
    scored = matched & joined["devig_close_prob"].notna() & joined["y"].notna() & joined["p_base"].notna()
    y = joined.loc[scored, "y"].to_numpy(float)
    close = joined.loc[scored, "devig_close_prob"].to_numpy(float)
    base = joined.loc[scored, "p_base"].to_numpy(float)

    def summary(frame: pd.DataFrame) -> dict[str, float | int]:
        total = len(frame)
        hit = int(frame["_spine_join"].eq("both").sum())
        return {"denominator": total, "joined": hit, "join_rate": _rate(hit, total)}

    by_year = {
        str(year): summary(frame) for year, frame in joined.groupby(joined["date"].dt.year, sort=True)
    }
    by_unit = {
        str(unit): summary(frame) for unit, frame in joined.loc[matched].groupby("corpus_unit", sort=True)
    }
    return {
        "sport": sport, "denominator": denominator, "joined": int(matched.sum()),
        "unjoined": int((~matched).sum()), "join_rate": _rate(int(matched.sum()), denominator),
        **drops, "scored": int(scored.sum()),
        "brier_devig_close": float(np.mean((close - y) ** 2)) if len(y) else None,
        "brier_p_base": float(np.mean((base - y) ** 2)) if len(y) else None,
        "by_year": by_year, "by_corpus_unit": by_unit,
    }


__all__ = ["JoinSpec", "close_column", "coverage_report", "gate_corpus_states"]
