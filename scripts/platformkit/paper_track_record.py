"""Consolidate append-only paper decisions into an attributed unit-only record."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

import pandas as pd

DEFAULT_CACHE = Path(r"C:\Users\neelj\nba-ai-system\data\cache")
DEFAULT_LEDGER = DEFAULT_CACHE.parents[1] / "data" / "frontend" / "clv_ledger.jsonl"
OUTPUT = Path("data/ab_reports/paper_track_record.parquet")
_PRICE = ("market_prob", "market_price", "price_prob", "entry_market_prob")
_PROB = ("model_prob", "prob_at_entry", "fair_prob", "calibrated_prob")


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if 0.0 <= result <= 1.0 else None


def _price(row: Dict[str, Any]) -> float | None:
    for key in _PRICE:
        value = _number(row.get(key))
        if value is not None:
            return value
    try:
        decimal = float(row.get("taken_decimal"))
        return 1.0 / decimal if decimal > 1.0 else None
    except (TypeError, ValueError):
        return None


def _value(row: Dict[str, Any], keys: Sequence[str]) -> Any:
    return next((row[key] for key in keys if row.get(key) not in (None, "")), None)


def _key(row: Dict[str, Any]) -> str:
    key = _value(row, ("bet_id", "edge_key", "decision_id", "id"))
    if key is not None:
        return str(key)
    return "|".join(str(_value(row, (k,)) or "") for k in
                    ("market_id", "game_id", "event_id", "market", "side", "ts"))


def _outcome(row: Dict[str, Any]) -> str | None:
    status = str(_value(row, ("outcome", "result", "status")) or "").lower()
    if status in {"won", "win", "lost", "loss", "push", "void"}:
        return {"win": "won", "loss": "lost"}.get(status, status)
    try:
        unit = float(row.get("unit_result"))
        return "won" if unit > 0 else "lost" if unit < 0 else "push"
    except (TypeError, ValueError):
        return None


def _is_paper(row: Dict[str, Any]) -> bool:
    text = " ".join(str(row.get(k, "")).lower()
                     for k in ("channel", "source", "daemon", "taken_book", "strategy"))
    return "paper" in text


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError("non-object JSONL record")
            rows.append(value)
    return rows


def discover_stores(cache_root: Path, ledger: Path | None = None) -> List[Path]:
    """Return likely paper JSONL stores, including the daemon canonical ledger."""
    found = [p for p in cache_root.rglob("*.jsonl")
             if "paper" in str(p).lower() or "clv_ledger" in p.name.lower()
             or "clv_close" in p.name.lower()]
    found.extend(p for p in (cache_root / "settled_bets.json",
                              cache_root / "auto_settle_seen.json") if p.exists())
    canonical = ledger if ledger is not None else DEFAULT_LEDGER
    if canonical.exists():
        found.append(canonical)
    return sorted(set(found))


def consolidate(stores: Iterable[Path]) -> Tuple[pd.DataFrame, List[str]]:
    """Read stores, fold append-only paper rows, and return decisions plus skip notes."""
    events: List[Dict[str, Any]] = []
    notes: List[str] = []
    for store in stores:
        try:
            records = _read_jsonl(store)
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as exc:
            notes.append("SKIP unparseable {}: {}".format(store.name, type(exc).__name__))
            continue
        paper = [row for row in records if _is_paper(row)]
        if not paper:
            notes.append("SKIP no paper decisions: {}".format(store.name))
        events.extend(paper)
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for event in events:
        grouped[_key(event)].append(event)
    rows: List[Dict[str, Any]] = []
    for key, history in grouped.items():
        history.sort(key=lambda row: str(row.get("ts") or row.get("created_at") or ""))
        entry = next((row for row in history if str(row.get("status", "open")).lower()
                      not in {"settled", "won", "lost", "void", "push"}), history[0])
        settled = next((row for row in reversed(history) if _outcome(row) is not None), {})
        entry_price = _price(entry)
        entry_index = history.index(entry)
        last_price = _price(settled) if settled and settled is not entry else None
        if last_price is None and settled:
            for later in reversed(history[entry_index + 1:]):
                last_price = _price(later)
                if last_price is not None:
                    break
        prob = _number(_value(entry, _PROB))
        strategy = _value(entry, ("strategy", "strategy_tag", "channel", "source", "daemon"))
        source = _value(entry, ("daemon", "source", "channel")) or "unknown"
        rows.append({
            "decision_id": key, "ts": _value(entry, ("ts", "created_at", "signal_ts")),
            "market_id": _value(entry, ("market_id", "game_id", "event_id", "market", "matchup")),
            "side": entry.get("side"), "prob_at_entry": prob,
            "market_price_at_entry": entry_price,
            "size_units": _value(entry, ("stake_units", "stake", "units", "size_units")) or 1.0,
            "strategy": strategy or source, "source_daemon": source,
            "settle_outcome": _outcome(settled), "last_pre_settle_price": last_price,
            "clv_probability": (entry_price - last_price
                                if entry_price is not None and last_price is not None else None),
        })
    return pd.DataFrame(rows), notes


def summary(rows: pd.DataFrame) -> pd.DataFrame:
    """Compute conservative paper-only strategy statistics."""
    result: List[Dict[str, Any]] = []
    for name, group in rows.groupby("strategy", dropna=False):
        settled = group[group["settle_outcome"].isin(["won", "lost"])]
        actual = settled["settle_outcome"].eq("won").astype(float)
        probs = pd.to_numeric(settled["prob_at_entry"], errors="coerce")
        valid = probs.notna()
        count = len(group)
        result.append({"strategy": name, "n": count,
                       "win_rate": actual.mean() if len(actual) else None,
                       "avg_clv_probability": pd.to_numeric(group["clv_probability"], errors="coerce").mean(),
                       "brier_entry_prob": ((probs[valid] - actual[valid]) ** 2).mean() if valid.any() else None,
                       "date_start": group["ts"].min(), "date_end": group["ts"].max(),
                       "verdict": "INSUFFICIENT" if count < 30 else "PAPER ONLY"})
    return pd.DataFrame(result)


def render_summary(stats: pd.DataFrame, notes: Sequence[str]) -> str:
    lines = ["PAPER ONLY | prospective record | no dollar claims | units not currency",
             "strategy | n | win_rate | avg_clv_probability | brier_entry_prob | date_range | verdict"]
    for _, row in stats.iterrows():
        lines.append("{} | {} | {} | {} | {} | {} to {} | {}".format(
            row["strategy"], row["n"], _fmt(row["win_rate"]), _fmt(row["avg_clv_probability"]),
            _fmt(row["brier_entry_prob"]), row["date_start"], row["date_end"], row["verdict"]))
    return "\n".join(lines + list(notes))


def _fmt(value: Any) -> str:
    return "NA" if pd.isna(value) else "{:.4f}".format(float(value))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a paper-only unit track record.")
    parser.add_argument("--cache-root", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    rows, notes = consolidate(discover_stores(args.cache_root, args.ledger))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rows.to_parquet(args.output, index=False)
    print(render_summary(summary(rows), notes))


if __name__ == "__main__":
    main()
