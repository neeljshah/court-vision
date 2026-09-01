"""One foundry row per declared mechanism, one charged trial per column-wired row.

Every mechanism in ``mechanism_wiring.WIRING_BY_SPORT[sport]`` becomes a row. A row with a
trigger column runs a close-free logistic trial over the frozen corpus and is
charged to the cumulative-K ledger by ``run_backtest`` BEFORE any result is
read; a row without one is emitted NOT_TESTABLE with its data reason. Verdicts
are calibration language only (MATCH / BEHIND / INSUFFICIENT / NOT_TESTABLE) --
no edge or ROI claim. ``--dry-run`` (``build(run_trials=False)``) queues the
trigger rows as PENDING and charges the shared cumulative-K ledger nothing.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

import numpy as np

from scripts.platformkit.analytics_showcase import mechanism_wiring as wiring
from scripts.platformkit.signals.foundry_run import _fit_logistic, _sigmoid

REPO = wiring.REPO_ROOT
OUT_DIR = Path(__file__).parent / "out"
OUT_JSON = OUT_DIR / "mechanism_wiring.json"
PREREG_JSON = OUT_DIR / "mechanism_wiring_prereg.json"
LEDGER_PATH = REPO / "data" / "cache" / "eval_gate" / "backtest_fwer.jsonl"
SPORT = "basketball_nba"
MODULE = "scripts.platformkit.analytics_showcase.mechanism_foundry"
_MIN_FIT_ROWS = 30


def out_paths(sport: str) -> tuple[Path, Path]:
    """Sport-scoped artifact paths so one sport's run never clobbers another's."""
    if sport == SPORT:
        return PREREG_JSON, OUT_JSON
    return (OUT_DIR / ("mechanism_wiring_prereg_%s.json" % sport),
            OUT_DIR / ("mechanism_wiring_%s.json" % sport))


def _predict(slug: str, train: Sequence[dict], test: dict) -> float:
    """Close-free baseline shifted by the standardized trigger via a logistic link.

    Leak contract: the test view must be redacted (no outcome / no close), and
    the fit uses only the walk-forward train rows handed to this call.
    """
    if "outcome" in test or "devig_close_prob" in test:
        raise AssertionError("LEAK: predictor handed an unredacted test view")
    table = wiring.value_table(slug)
    pairs = [(table.get(row["game_id"]), row["outcome"]) for row in train]
    base = float(np.mean([y for _v, y in pairs])) if pairs else 0.5
    fit = [(v, y) for v, y in pairs if v is not None and math.isfinite(v)]
    if len(fit) < _MIN_FIT_ROWS:
        return min(max(base, 1e-4), 1.0 - 1e-4)
    values = np.array([v for v, _y in fit], float)
    mean, sd = float(values.mean()), float(values.std())
    if sd < 1e-9:
        return min(max(base, 1e-4), 1.0 - 1e-4)
    b0, b1 = _fit_logistic((values - mean) / sd, np.array([float(y) for _v, y in fit], float))
    raw = table.get(test["game_id"])
    z = (raw - mean) / sd if raw is not None and math.isfinite(raw) else 0.0
    return float(np.clip(_sigmoid(np.array(b0 + b1 * float(np.clip(z, -4.0, 4.0)))), 1e-4, 1 - 1e-4))


def _make(slug: str):
    def trial(train: Sequence[dict], test: dict, select_inside: bool) -> float:
        return _predict(slug, train, test)
    trial.__doc__ = "Foundry trial predictor for mechanism " + slug
    return trial


# Generated once at import so backtest_runner's "module:callable" spec resolves.
PREDICTORS = {}
for _i, _slug in enumerate(wiring.TESTABLE):
    _name = "trial_%02d" % _i
    globals()[_name] = _make(_slug)
    PREDICTORS[_slug] = _name


def prereg_rows(sport: str = SPORT) -> list[dict]:
    """Declare every mechanism row and its trigger BEFORE any result is read."""
    rows = []
    for slug, spec in wiring.WIRING_BY_SPORT[sport].items():
        row = {"mechanism_id": slug, "trigger": spec["expr"],
               "source_artifact": spec["source"] or "(none)"}
        if spec["expr"]:
            cover = wiring.coverage(slug)
            row.update({"threshold": spec["threshold"], "as_of": cover["as_of"],
                        "n_corpus": cover["n_corpus"], "n_covered": cover["n_covered"],
                        "coverage_share": cover["share"],
                        "planned": "trial" if cover["share"] >= wiring.MIN_COVERAGE else "NOT_TESTABLE",
                        "predictor": MODULE + ":" + PREDICTORS[slug]})
        else:
            row.update({"planned": "NOT_TESTABLE", "reason": spec["reason"], "as_of": None})
        rows.append(row)
    return rows


def _trial(row: dict, sport: str = SPORT) -> dict:
    from scripts.platformkit.eval_gate.backtest_runner import run_backtest
    report = run_backtest(row["predictor"], sport, wiring.CORPUS_START, wiring.CORPUS_END,
                          ledger_path=LEDGER_PATH)
    scores, dm, fwer = report["scores"], report["dm_vs_close"], report["fwer"]
    return {**row, "verdict": report["verdict"], "n": report["n_games"],
            "model_brier": scores["model_brier"], "close_brier": scores["close_brier"],
            "dm_p": dm["p_value"], "k_cum": fwer["k_cumulative"], "dm_alpha": fwer["dm_alpha"]}


def build(rows: list[dict] | None = None, run_trials: bool = True,
          sport: str = SPORT) -> dict:
    """Turn prereg rows into result rows; idempotent given the same corpus.

    ``run_trials=False`` is the dry run: every trigger row is emitted PENDING and
    NOTHING is charged to the shared cumulative-K ledger.
    """
    rows = rows if rows is not None else prereg_rows(sport)
    out = []
    for row in rows:
        if row["planned"] != "trial":
            reason = row.get("reason") or (
                "trigger column covers only %d of %d frozen-corpus games (below the declared "
                "%.0f%% bar)" % (row.get("n_covered", 0), row.get("n_corpus", 0),
                                 100 * wiring.MIN_COVERAGE))
            out.append({**row, "verdict": "NOT_TESTABLE", "n": row.get("n_covered", 0),
                        "reason": reason})
        elif run_trials:
            out.append(_trial(row, sport))
        else:
            out.append({**row, "verdict": "PENDING", "n": row.get("n_covered", 0)})
    verdicts: dict[str, int] = {}
    for row in out:
        verdicts[row["verdict"]] = verdicts.get(row["verdict"], 0) + 1
    return {"label": "DESCRIPTIVE_ONLY", "edge_claimed": False,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "as_of": max([r["as_of"] for r in out if r.get("as_of")], default=None),
            "corpus": {"sport": sport, "start": wiring.CORPUS_START, "end": wiring.CORPUS_END},
            "counts": {"mechanisms": len(out), "wired": len(out),
                       "with_trigger": sum(1 for r in out if r.get("trigger")),
                       "not_testable": sum(1 for r in out if r["verdict"] == "NOT_TESTABLE"),
                       "queued_for_charged_run": sum(1 for r in out if r["verdict"] == "PENDING"),
                       "by_verdict": verdicts},
            "rows": out}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="mechanism wiring foundry (per sport)")
    parser.add_argument("--sport", default=SPORT, choices=sorted(wiring.WIRING_BY_SPORT))
    parser.add_argument("--dry-run", action="store_true",
                        help="declare and queue rows without charging any ledger trial")
    args = parser.parse_args(argv)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    prereg_path, out_path = out_paths(args.sport)
    # ponytail: a dry run must never erase results someone already paid trials
    # for; the charged marker is the per-row k_cum the ledger charge wrote.
    if args.dry_run and out_path.exists() and '"k_cum"' in out_path.read_text(encoding="ascii"):
        raise SystemExit("refusing to overwrite charged results with a dry run: %s" % out_path)
    rows = prereg_rows(args.sport)
    prereg_path.write_text(json.dumps(rows, indent=2, ensure_ascii=True), encoding="ascii")
    print("prereg written before any trial:", prereg_path)
    result = build(rows, run_trials=not args.dry_run, sport=args.sport)
    out_path.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="ascii")
    for row in result["rows"]:
        if row["verdict"] == "NOT_TESTABLE":
            print("%-46s NOT_TESTABLE  %s" % (row["mechanism_id"][:46], row["reason"][:70]))
        elif row["verdict"] == "PENDING":
            print("%-46s PENDING       queued, no ledger trial charged" % row["mechanism_id"][:46])
        else:
            print("%-46s %-12s n=%d brier=%.6f close=%.6f dm_p=%.6f k=%d" % (
                row["mechanism_id"][:46], row["verdict"], row["n"], row["model_brier"],
                row["close_brier"], row["dm_p"], row["k_cum"]))
    print("counts", json.dumps(result["counts"]))
    print("wrote", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
