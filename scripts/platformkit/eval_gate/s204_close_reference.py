"""S204 read-only calibration comparison against verified pregame closes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from scripts.platformkit.eval_gate.calibration_report import _bin_table, _oof_per_regime
from scripts.platformkit.eval_gate.close_join import _spec, close_column
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.scoring import brier, ece, log_loss
from scripts.platformkit.regime_calibration import buckets

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUT = ROOT / "docs" / "evidence" / "harness"
DATE = "2026-09-04"
PREREG_PATH = "docs/evidence/harness/S204_close_reference_calibration_prereg_2026-09-04.md"
PREREG_SEAL = "150DFC16B37055B741F65F4D332C3625FA41B6EE4CDA140B4E5D39A7D31C5178"
NBA_SOURCE = "pregame_last_tick_before_commence"
MLB_SOURCE = "pre_first_pitch_two_sided"
INPLAY_SOURCE = "first_inplay_tick"


def _path(name: str) -> Path:
    return ROOT / name


def _source(path: Path) -> dict[str, Any]:
    return {"path": path.as_posix(), "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _finite(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").map(np.isfinite)


def _calibrated(frame: pd.DataFrame) -> pd.DataFrame:
    """Apply the unchanged S05 OOF route before any close pairing."""
    usable = _finite(frame["y"]) & _finite(frame["p_base"])
    out = frame.copy()
    out["p_model"] = np.nan
    rows = out.loc[usable].to_dict("records")
    for row in rows:
        row["model_prob"] = row["p_base"]
    raw = [float(row["p_base"]) for row in rows]
    y = [float(row["y"]) for row in rows]
    out.loc[usable, "p_model"] = _oof_per_regime(raw, y, buckets(rows), min_n=200)
    return out


def _reasons(frame: pd.DataFrame, paired: pd.Series, source_ok: pd.Series,
             synthetic: bool = False) -> pd.DataFrame:
    source = frame.get("close_source", pd.Series("", index=frame.index)).astype(str)
    reason = np.where(~_finite(frame["y"]) | ~_finite(frame["p_base"]), "null_model_or_target",
             np.where(~_finite(frame["p_close"]), "null_price",
             np.where(source.eq(INPLAY_SOURCE), "inplay_close_source",
             np.where(~source_ok, "not_verified_pregame_source", "paired"))))
    if synthetic:
        reason = np.where(~_finite(frame["y"]) | ~_finite(frame["p_base"]), "null_model_or_target",
                 np.where(_finite(frame["p_close"]), "synthetic_vintage_no_pregame_proof", "null_price"))
    out = frame.loc[~paired, ["event_id"]].copy()
    out["reason"] = reason[~paired.to_numpy()]
    return out.sort_values("event_id", kind="stable").reset_index(drop=True)


def _metrics(p: Iterable[float], y: Iterable[float]) -> dict[str, Any]:
    probs, outcomes = list(p), list(y)
    return {"ece": ece(probs, outcomes, bins=10), "brier": brier(probs, outcomes),
            "log_loss": log_loss(probs, outcomes), "reliability_bins": _bin_table(probs, outcomes, 10)}


def _score(sport: str, frame: pd.DataFrame, source_ok: pd.Series,
           sources: list[dict[str, Any]], synthetic: bool = False) -> tuple[dict[str, Any], pd.DataFrame, pd.DataFrame]:
    valid = _finite(frame["y"]) & _finite(frame["p_base"]) & _finite(frame["p_model"])
    paired = valid & source_ok & _finite(frame["p_close"])
    excluded = _reasons(frame, paired, source_ok, synthetic=synthetic)
    pairs = frame.loc[paired, ["event_id", "corpus_unit", "event_date", "y", "p_model", "p_close"]].copy()
    pairs["loss_model"] = (pairs["p_model"] - pairs["y"]) ** 2
    pairs["loss_close"] = (pairs["p_close"] - pairs["y"]) ** 2
    pairs["brier_delta_close_minus_model"] = pairs["loss_close"] - pairs["loss_model"]
    pairs = pairs.sort_values("event_id", kind="stable").reset_index(drop=True)
    if len(pairs) != pairs["event_id"].nunique():
        raise ValueError("%s has duplicate paired event_id" % sport)
    report: dict[str, Any] = {
        "sport": sport, "input_rows": int(len(frame)), "paired_rows": int(len(pairs)),
        "dropped_after_pairing": 0, "exclusion_counts": excluded["reason"].value_counts().sort_index().to_dict(),
        "inplay_close_source_rows": int((frame.get("close_source") == INPLAY_SOURCE).sum()) if "close_source" in frame else 0,
        "sources": sources, "model_route": "S05 calibration_report._oof_per_regime before pairing",
        "bin_edge_rule": "np.linspace(0, 1, 11); [lo,hi) except final [lo,hi]",
        "comparison_status": "NOT SCORABLE", "reason": "no verified paired pregame rows" if not len(pairs) else None,
    }
    if not len(pairs):
        return report, pairs, excluded
    model, close, y = (pairs[key].to_numpy(float) for key in ("p_model", "p_close", "y"))
    delta = pairs["brier_delta_close_minus_model"].to_numpy(float)
    units = pairs["corpus_unit"].astype(str).to_numpy()
    report.update({"model": _metrics(model, y), "close": _metrics(close, y),
                   "brier_delta_close_minus_model": float(delta.mean()),
                   "n_eff": int(pd.Series(units).nunique())})
    if report["n_eff"] < 2:
        report["ci95"] = None
        report["reason"] = "fewer than 30 corpus_unit clusters; clustered CI needs at least two"
        return report, pairs, excluded
    dm = diebold_mariano(delta, units)
    report["ci95"] = [float(dm.ci95[0]), float(dm.ci95[1])]
    if dm.n_clusters >= 30:
        report["comparison_status"] = "MATCH" if dm.ci95[0] <= 0 <= dm.ci95[1] else "BEHIND"
        report["reason"] = None
    else:
        report["reason"] = "fewer than 30 corpus_unit clusters"
    return report, pairs, excluded


def _nba_mlb(sport: str) -> tuple[pd.DataFrame, pd.Series, list[dict[str, Any]]]:
    path = _path("data/cache/combo/gate_corpus_%s_close.parquet" % sport)
    frame = _calibrated(pd.read_parquet(path))
    expected = NBA_SOURCE if sport == "nba" else MLB_SOURCE
    return frame, frame["close_source"].eq(expected), [_source(path)]


def _soccer() -> tuple[pd.DataFrame, pd.Series, list[dict[str, Any]]]:
    corpus_path = _path("data/cache/combo/gate_corpus_soccer.parquet")
    frame = _calibrated(pd.read_parquet(corpus_path))
    odds_path = _path("data/domains/soccer/odds.parquet")
    odds_raw = pd.read_parquet(odds_path)
    spec = _spec("soccer")
    odds = odds_raw[["event_id"]].copy().assign(p_close=close_column(odds_raw, spec))
    if odds["event_id"].duplicated().any():
        raise ValueError("soccer odds event_id is not unique")
    joined = frame.merge(odds, on="event_id", how="left", validate="one_to_one")
    return joined, pd.Series(True, index=joined.index), [_source(corpus_path), _source(odds_path)]


def _tennis() -> tuple[pd.DataFrame, pd.Series, list[dict[str, Any]]]:
    corpus_path = _path("data/cache/combo/gate_corpus_tennis.parquet")
    frame = pd.read_parquet(corpus_path)
    odds_path = _path("data/domains/tennis/odds.parquet")
    odds_raw = pd.read_parquet(odds_path)
    spec = _spec("tennis")
    close = close_column(odds_raw, spec)
    odds = pd.DataFrame({"event_id": odds_raw["event_id"].astype(str), "p_close": close})
    odds = odds.loc[~odds["event_id"].duplicated(keep=False)]
    joined = frame.merge(odds, on="event_id", how="left", validate="one_to_one")
    joined["p_model"] = joined["p_base"]
    return joined, pd.Series(False, index=joined.index), [_source(corpus_path), _source(odds_path)]


def build() -> tuple[dict[str, Any], dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    """Build S204 evidence in fixed sport order, reading one parquet at a time."""
    inputs = {"nba": _nba_mlb("nba"), "mlb": _nba_mlb("mlb"), "soccer": _soccer(), "tennis": _tennis()}
    reports, pairs, excluded = {}, {}, {}
    for sport, (frame, source_ok, sources) in inputs.items():
        reports[sport], pairs[sport], excluded[sport] = _score(sport, frame, source_ok, sources, sport == "tennis")
    code_paths = [_path("scripts/platformkit/eval_gate/s204_close_reference.py"),
                  _path("scripts/platformkit/eval_gate/calibration_report.py")]
    return {"gap": "S204", "prereg_path": PREREG_PATH, "prereg_seal_sha256": PREREG_SEAL,
            "sports": reports, "code_identity": [_source(path) for path in code_paths]}, pairs, excluded


def write_artifacts(out_dir: Path = DEFAULT_OUT) -> dict[str, Any]:
    """Write the summary and all paired/exclusion series below docs/evidence only."""
    out_dir.mkdir(parents=True, exist_ok=True)
    report, pairs, excluded = build()
    for sport in report["sports"]:
        pairs[sport].to_csv(out_dir / ("S204_%s_paired_%s.csv" % (sport, DATE)), index=False)
        excluded[sport].to_csv(out_dir / ("S204_%s_exclusions_%s.csv" % (sport, DATE)), index=False)
    target = out_dir / ("S204_close_reference_calibration_%s.json" % DATE)
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="ascii")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="S204 close-reference calibration evidence")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    report = write_artifacts(args.out_dir)
    for sport, row in report["sports"].items():
        print("%s paired=%d n_eff=%s status=%s" % (sport, row["paired_rows"], row.get("n_eff"), row["comparison_status"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
