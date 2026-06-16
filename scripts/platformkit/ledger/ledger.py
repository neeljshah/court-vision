"""Append-only track-record store (blueprint X3 / mcp-and-ledger PART B).

Every prediction appends ONE immutable row. Writes are ATOMIC (temp file + os.replace)
and IDEMPOTENT on pred_id (drop_duplicates keep="first"), so a re-run never doubles a
row and a crash mid-write never corrupts the live file. Predictions are immutable: this
module never mutates an existing row (grading is a separate no-overwrite pass).

Parquet via pyarrow when available; JSONL fallback otherwise (the JSONL core mirrors the
verified eval_gate/ledger.py append_row/load). The live store lives under the GITIGNORED
vault/_TrackRecord/. Logs probabilities + outcomes ONLY -- no units / ROI / edge column
exists in SCHEMA_COLS, so a dollar claim cannot be stored.
"""
from __future__ import annotations
import json
import os
import pathlib
from typing import List, Optional

import pandas as pd

try:  # package import when run as `-m scripts.platformkit.ledger...`
    from scripts.platformkit.ledger.schema import (
        SCHEMA_COLS, LedgerRow, hash_inputs, make_pred_id)
except ImportError:  # direct-script / sys.path-injected (per-file test) fallback
    from schema import SCHEMA_COLS, LedgerRow, hash_inputs, make_pred_id

try:  # parquet preferred; degrade to JSONL on a clone without pyarrow
    import pyarrow  # noqa: F401
    _HAVE_PARQUET = True
except Exception:  # pragma: no cover - environment-dependent
    _HAVE_PARQUET = False

_REPO = pathlib.Path(__file__).resolve().parents[3]
_DEFAULT_DIR = _REPO / "vault" / "_TrackRecord"


def _store_paths(base_dir: Optional[str]) -> tuple:
    d = pathlib.Path(base_dir) if base_dir else _DEFAULT_DIR
    d.mkdir(parents=True, exist_ok=True)
    ext = "parquet" if _HAVE_PARQUET else "jsonl"
    return d / f"predictions.{ext}", d / "predictions.csv"


def _read_frame(path: pathlib.Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=list(SCHEMA_COLS))
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    rows = []
    with open(path, encoding="ascii") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    df = pd.DataFrame(rows)
    return df if not df.empty else pd.DataFrame(columns=list(SCHEMA_COLS))


def _atomic_write(df: pd.DataFrame, path: pathlib.Path) -> None:
    """Write to a temp sibling then os.replace -> the live file is never half-written."""
    df = df.reindex(columns=list(SCHEMA_COLS))
    tmp = path.with_suffix(path.suffix + ".tmp")
    if path.suffix == ".parquet":
        df.to_parquet(tmp, index=False)
    else:
        with open(tmp, "w", encoding="ascii") as f:
            for _, r in df.iterrows():
                f.write(json.dumps({k: _jsonable(r[k]) for k in SCHEMA_COLS},
                                   ensure_ascii=True) + "\n")
    os.replace(tmp, path)


def _jsonable(v):
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, float):
        return float(v)
    return v


def _mirror_csv(df: pd.DataFrame, csv_path: pathlib.Path) -> None:
    df.reindex(columns=list(SCHEMA_COLS)).to_csv(csv_path, index=False)


def append_rows(rows: List[LedgerRow], base_dir: Optional[str] = None) -> List[str]:
    """Append LedgerRows atomically + idempotently. Returns the pred_ids written/kept."""
    if not rows:
        return []
    store, csv_path = _store_paths(base_dir)
    existing = _read_frame(store)
    new = pd.DataFrame([r.as_record() for r in rows])
    merged = new if existing.empty else pd.concat([existing, new], ignore_index=True)
    # idempotent: a re-appended pred_id collapses to the FIRST (immutable) copy
    merged = merged.drop_duplicates("pred_id", keep="first").reset_index(drop=True)
    _atomic_write(merged, store)
    _mirror_csv(merged, csv_path)
    return [r.pred_id for r in rows]


def append_prediction(sport: str, layer: str, market: str, home: str, away: str,
                      calibrated_prob: float, inputs: dict, pred_ts: str,
                      model_version: str = "unknown", point_proj: Optional[float] = None,
                      game_date: Optional[str] = None, game_id: Optional[str] = None,
                      base_dir: Optional[str] = None) -> str:
    """Build one row (pred_id derived from inputs+vintage) and append. Returns pred_id."""
    ih = hash_inputs(inputs)
    pid = make_pred_id(sport, home, away, market, layer, ih, pred_ts)
    row = LedgerRow(pred_id=pid, pred_ts=pred_ts, sport=sport, layer=layer, market=market,
                    home=home, away=away, inputs_hash=ih, model_version=model_version,
                    calibrated_prob=float(calibrated_prob), point_proj=point_proj,
                    game_date=game_date, game_id=game_id)
    append_rows([row], base_dir=base_dir)
    return pid


def _iter_binary_markets(sport: str, block: dict):
    """Yield (market, prob) binary forecasts from a build_result() layer block.

    Defensive: only emits keys present + in [0,1]. Never invents a number.
    """
    for key, market in (("home_win_prob", "ml"), ("over_prob", "total"),
                        ("p1_win_prob", "p1_match_win"), ("cover_prob", "spread")):
        v = block.get(key)
        if isinstance(v, (int, float)) and 0.0 <= float(v) <= 1.0:
            yield market, float(v)


def append_from_result(result: dict, pred_ts: str, model_version: str = "unknown",
                       layer_filter: Optional[str] = None,
                       base_dir: Optional[str] = None) -> List[str]:
    """Turn a predict_matchup.build_result() dict into ledger rows + append.

    The LLM never reaches this path with a number it authored: `prob` is read verbatim
    from the quant block. Returns the list of pred_ids.
    """
    sport = result.get("sport", "nba")
    home = result.get("home", "?")
    away = result.get("away", "?")
    game_date = result.get("game_date")
    game_id = result.get("game_id")
    inputs = result.get("inputs", {})
    ih = hash_inputs(inputs)
    out: List[LedgerRow] = []
    for layer in ("pregame", "ingame"):
        block = result.get(layer)
        if not block or (layer_filter and layer != layer_filter):
            continue
        for market, prob in _iter_binary_markets(sport, block):
            pid = make_pred_id(sport, home, away, market, layer, ih, pred_ts)
            out.append(LedgerRow(pred_id=pid, pred_ts=pred_ts, sport=sport, layer=layer,
                                 market=market, home=home, away=away, inputs_hash=ih,
                                 model_version=model_version, calibrated_prob=prob,
                                 point_proj=block.get("point_proj"), game_date=game_date,
                                 game_id=game_id))
    return append_rows(out, base_dir=base_dir)


def read_ledger(graded_only: bool = False, base_dir: Optional[str] = None) -> pd.DataFrame:
    """Load the full ledger as a DataFrame (SCHEMA_COLS order); optionally graded rows only."""
    store, _ = _store_paths(base_dir)
    df = _read_frame(store).reindex(columns=list(SCHEMA_COLS))
    if graded_only and not df.empty:
        df = df[df["outcome"].notna()].reset_index(drop=True)
    return df
