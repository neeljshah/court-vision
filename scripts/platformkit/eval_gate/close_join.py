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
    price_suffixes: tuple[str, ...] = ()
    spine_files: tuple[str, ...] = ()
_SPECS = {
    "soccer": JoinSpec(
        sport="soccer", spine="event_id", date_col="date",
        side_a="ou_close_over", side_b="ou_close_under",
        fallback_a="avgc_over", fallback_b="avgc_under",
        name_a="over25", name_b="under25",
    ),
    "tennis": JoinSpec(
        sport="tennis", spine="event_id", date_col="date",
        side_a="ps_p1", side_b="ps_p2",
        fallback_a="b365_p1", fallback_b="b365_p2",
        name_a="p1_win", name_b="p2_win",
        price_suffixes=("_p1", "_p2"),
        spine_files=("matches.parquet", "wta_matches.parquet"),
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
def _check_orientation(spec: JoinSpec) -> None:
    """Refuse outcome-oriented or off-spec close columns."""
    for column in (spec.side_a, spec.side_b, spec.fallback_a, spec.fallback_b):
        off_spec = bool(spec.price_suffixes) and not column.endswith(spec.price_suffixes)
        if column.endswith(("_w", "_l")) or (off_spec and column.endswith(("w", "l"))):
            raise ValueError(
                f"leaky winner/loser close column: {column!r} (use the de-leaked pair)")
        if off_spec:
            raise ValueError(
                f"close column {column!r} must end with one of {spec.price_suffixes}")
def close_column(odds: pd.DataFrame, spec: JoinSpec) -> pd.Series:
    """Return fair probability for ``name_a`` and expose all close-drop counts."""
    _check_orientation(spec)
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
def _named_spine(spec: JoinSpec, key: str) -> pd.DataFrame:
    """Union the per-unit spine files, exposing date + the two side names."""
    base = _ROOT / "data" / "domains" / spec.sport
    columns = [spec.spine, spec.date_col, "p1_name", "p2_name"]
    if key != spec.spine:
        columns.insert(1, key)
    frames = []
    for filename in spec.spine_files:
        path = base / filename
        if not path.exists():
            raise FileNotFoundError(f"missing spine file: {path}")
        frame = pd.read_parquet(path)
        missing = [c for c in columns if c not in frame.columns]
        if missing:
            raise KeyError(f"{path.name} lacks join column(s): {missing}")
        frames.append(frame[columns])
    spine = pd.concat(frames, ignore_index=True).rename(
        columns={"p1_name": "home_team", "p2_name": "away_team"})
    for column in {spec.spine, key}:
        spine[column] = spine[column].astype(str)
    return spine
def _joined_spine_first(spec: JoinSpec, start: str | None, end: str | None, key: str):
    """Join odds ONTO the full corpus spine: every spine row stays in the denominator."""
    odds_path = _ROOT / "data" / "domains" / spec.sport / "odds.parquet"
    if not odds_path.exists():
        raise FileNotFoundError(f"missing local close inputs: {odds_path}")
    odds = pd.read_parquet(odds_path).copy()
    if key not in odds.columns:
        raise KeyError(f"odds.parquet lacks join column: {key}")
    odds[key] = odds[key].astype(str)
    ambiguous = odds[key].duplicated(keep=False)
    odds = odds.loc[~ambiguous].copy()
    close = close_column(odds, spec)
    counts = dict(close.attrs)
    counts["ambiguous_event_id_drop_count"] = int(ambiguous.sum())
    odds = odds[[key]].copy()
    odds["devig_close_prob"] = close

    corpus = load_gate_corpus(spec.sport).copy()
    corpus[spec.spine] = corpus[spec.spine].astype(str)
    spine = _named_spine(spec, key)
    for name, frame, column in (
        ("odds", odds, key), ("spine", spine, spec.spine), ("corpus", corpus, spec.spine),
    ):
        if frame[column].duplicated().any():
            raise ValueError(f"duplicate {column} in {name}")
    joined = corpus[[spec.spine, "corpus_unit", "y", "p_base"]].merge(
        spine, on=spec.spine, how="left", validate="one_to_one")
    joined[spec.date_col] = pd.to_datetime(joined[spec.date_col], errors="raise")
    if start is not None:
        joined = joined.loc[joined[spec.date_col] >= pd.Timestamp(start)].copy()
    if end is not None:
        joined = joined.loc[joined[spec.date_col] <= pd.Timestamp(end)].copy()
    joined = joined.merge(
        odds, on=key, how="left", validate="one_to_one", indicator="_spine_join")
    return joined, counts
def _joined(sport: str, start: str | None = None, end: str | None = None, key: str | None = None) -> tuple[pd.DataFrame, dict[str, int]]:
    spec = _spec(sport)
    if spec.spine_files:
        return _joined_spine_first(spec, start, end, key or spec.spine)
    if key is not None and key != spec.spine:
        raise ValueError(f"{sport}: alternative join key {key!r} is not supported")
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
def gate_corpus_states(sport: str, start: str, end: str, counts: dict[str, int] | None = None) -> list[dict]:
    """Build vintage-safe states and account for every discarded input row."""
    joined, close_counts = _joined(sport, start, end)
    matched = joined["_spine_join"].eq("both")
    priced = joined["devig_close_prob"].notna()
    targeted = joined["y"].notna() & joined["p_base"].notna()
    ready = joined.loc[matched & priced & targeted].sort_values("date")
    if counts is not None:
        counts.clear()
        counts.update({**{k: int(v) for k, v in close_counts.items()},
                       "n_joined": int(len(joined)),
                       "spine_unmatched": int((~matched).sum()),
                       "null_close": int((matched & ~priced).sum()),
                       "null_target": int((matched & priced & ~targeted).sum()),
                       "n_states": int(len(ready))})
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
            # S34: no real odds timestamp exists yet, so state_ts is constructed.
            "vintage": "SYNTHETIC",
        })
    return states
def _rate(numerator: int, denominator: int) -> float:
    return float(numerator / denominator) if denominator else 0.0
def _spine_coverage(sport: str, joined: pd.DataFrame) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Summarize the gate-corpus spine, including corpus rows without odds."""
    spec = _spec(sport)
    corpus = load_gate_corpus(sport)
    joined_ids = set(joined.loc[joined["_spine_join"].eq("both"), spec.spine].astype(str))
    spine = corpus.assign(_corpus_joined=corpus[spec.spine].astype(str).isin(joined_ids))

    def summary(frame: pd.DataFrame) -> dict[str, Any]:
        denominator = len(frame)
        matched = int(frame["_corpus_joined"].sum())
        return {"corpus_denominator": denominator, "corpus_joined": matched,
                "corpus_join_rate": _rate(matched, denominator)}

    overall = summary(spine)
    return overall, {str(unit): summary(frame) for unit, frame in spine.groupby("corpus_unit", sort=True)}
def coverage_report(sport: str, key: str | None = None) -> dict[str, Any]:
    """Report existing odds-side coverage plus additive corpus-spine coverage."""
    joined, drops = _joined(sport, key=key)
    corpus, by_corpus_unit_spine = _spine_coverage(sport, joined)
    denominator = len(joined)
    matched = joined["_spine_join"].eq("both")
    scored = matched & joined["devig_close_prob"].notna() & joined["y"].notna() & joined["p_base"].notna()
    y = joined.loc[scored, "y"].to_numpy(float)
    close = joined.loc[scored, "devig_close_prob"].to_numpy(float)
    base = joined.loc[scored, "p_base"].to_numpy(float)

    def summary(frame: pd.DataFrame) -> dict[str, Any]:
        total = len(frame)
        hit = int(frame["_spine_join"].eq("both").sum())
        fit = frame.loc[scored.reindex(frame.index, fill_value=False)]
        out: dict[str, Any] = {
            "denominator": total, "joined": hit, "join_rate": _rate(hit, total),
            "scored": len(fit),
        }
        if len(fit):
            truth = fit["y"].to_numpy(float)
            out["brier_devig_close"] = float(np.mean((fit["devig_close_prob"].to_numpy(float) - truth) ** 2))
            out["brier_p_base"] = float(np.mean((fit["p_base"].to_numpy(float) - truth) ** 2))
        return out

    by_year = {
        str(year): summary(frame) for year, frame in joined.groupby(joined["date"].dt.year, sort=True)
    }
    by_unit = {
        str(unit): summary(frame) for unit, frame in joined.groupby("corpus_unit", sort=True)
    }
    unjoined = int((~matched).sum())
    if unjoined and any(u["join_rate"] == 1.0 for u in by_unit.values()):
        raise ValueError("degenerate by_corpus_unit denominator: per-unit rate 1.0 with unjoined rows")
    corpus_unjoined = corpus["corpus_denominator"] - corpus["corpus_joined"]
    if corpus_unjoined and any(u["corpus_join_rate"] == 1.0 for u in by_corpus_unit_spine.values()):
        raise ValueError("degenerate by_corpus_unit_spine denominator: per-unit rate 1.0 with unjoined rows")
    return {
        "sport": sport, "join_key": key or _spec(sport).spine,
        "denominator": denominator, "joined": int(matched.sum()),
        "unjoined": unjoined, "join_rate": _rate(int(matched.sum()), denominator),
        **corpus, "corpus_unjoined": corpus_unjoined,
        "vintage": "SYNTHETIC",
        **drops, "scored": int(scored.sum()),
        "brier_devig_close": float(np.mean((close - y) ** 2)) if len(y) else None,
        "brier_p_base": float(np.mean((base - y) ** 2)) if len(y) else None,
        "by_year": by_year, "by_corpus_unit": by_unit,
        "by_corpus_unit_spine": by_corpus_unit_spine,
    }
__all__ = ["JoinSpec", "close_column", "coverage_report", "gate_corpus_states"]
