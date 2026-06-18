"""recal_eval -- HONEST out-of-sample test of the isotonic prop-recalibrator.

THE QUESTION (calibration, NOT a $-edge): does fitting the per-stat isotonic map
on EARLY World Cup matches IMPROVE calibration on LATER, unseen matches -- or does
it only look good in-sample? Fitting isotonic on the same matches we then score is
in-sample and would look falsely good. So we do a proper TEMPORAL split.

DESIGN (leak-free, then a SECOND honesty layer on top):
  1. props_eval.backtest_pairs(with_dates=True) gives leak-free (p, outcome, date)
     triples per stat -- each p was built from data strictly BEFORE its match.
  2. TEMPORAL split on the sorted UNIQUE match dates: TRAIN = earliest train_frac,
     TEST = the rest. No match straddles (we split on whole dates).
  3. Fit isotonic recalibrators on TRAIN pairs ONLY (prop_recal._fit_one, MIN_N).
  4. Score TEST pairs BOTH ways: raw p vs recalibrate(stat, p, train_recal).
     Compare Brier / ECE / log_loss on TEST, overall + per-stat. recal-raw < 0 is
     an IMPROVEMENT (lower is better).
  5. Also fit-and-score on the SAME pairs (in-sample) to expose the in-sample-vs-OOS
     gap -- the overfitting tell.

With ~24 WC matches the TEST set is SMALL; "no measurable OOS improvement" or
"helps ECE but not Brier" are valid, honest answers. NOT a $-edge claim.

Public funcs never raise. ASCII only. <=300 LOC. Per-file test only:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/test_recal_eval.py -q
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional, Sequence, Tuple

from scripts.platformkit.props_eval import backtest_pairs, score_prop_predictions
from domains.soccer.prop_recal import _fit_one, recalibrate

logger = logging.getLogger(__name__)

_METRICS = ("brier", "ece", "log_loss")
_DEFAULT_PARQUET = "data/domains/soccer/espn_player_stats.parquet"


def _split_dates(dates: Sequence, train_frac: float) -> Tuple[set, set]:
    """Sorted UNIQUE match dates -> (train_dates, test_dates). Split on whole
    dates so no match straddles. At least 1 date each side when >=2 dates."""
    uniq = sorted({d for d in dates if d is not None})
    n = len(uniq)
    if n == 0:
        return set(), set()
    if n == 1:
        return set(uniq), set()
    k = int(round(n * train_frac))
    k = min(max(k, 1), n - 1)  # keep >=1 date in each side
    return set(uniq[:k]), set(uniq[k:])


def _score(pairs: Sequence[Tuple[float, int]]) -> dict:
    """Score a list of (p, outcome) via the shared prop scorer."""
    return score_prop_predictions(
        [{"p_over": p, "outcome": y} for p, y in pairs])


def _apply(stat: str, pairs: Sequence[Tuple[float, int]], recal: dict
           ) -> List[Tuple[float, int]]:
    """Map each p through the stat's recalibrator (identity if unfitted)."""
    return [(recalibrate(stat, p, recal), y) for p, y in pairs]


def _delta(raw: dict, rec: dict) -> Dict[str, Optional[float]]:
    """rec - raw per metric (negative = recal IMPROVES; None if either absent)."""
    out: Dict[str, Optional[float]] = {}
    for m in _METRICS:
        a, b = raw.get(m), rec.get(m)
        out[m] = round(b - a, 5) if (a is not None and b is not None) else None
    return out


def _fit_table(pairs_by_stat: Dict[str, list]) -> Dict[str, dict]:
    """Fit per-stat isotonic maps from {stat: [(p, y), ...]}; skip thin stats."""
    table: Dict[str, dict] = {}
    for stat, pairs in pairs_by_stat.items():
        try:
            fit = _fit_one(pairs)
        except Exception:  # noqa: BLE001
            fit = None
        if fit is not None:
            table[stat] = fit
    return table


def run_eval(df=None, train_frac: float = 0.65,
             stats: Optional[Sequence[str]] = None,
             club_priors: bool = False) -> dict:
    """Temporal OOS recalibration test. Returns a dict with split sizes, per-stat
    + overall TEST raw-vs-recal Brier/ECE/log_loss deltas, the in-sample numbers,
    and a verdict. Never raises -> {"status": "...", ...} on any failure.

    A stat is fitted ONLY if its TRAIN pairs reach MIN_N; otherwise it stays
    identity on TEST (recal == raw). recal-minus-raw < 0 means recal helps."""
    try:
        if df is None:
            import pandas as pd
            df = pd.read_parquet(_DEFAULT_PARQUET)
    except Exception as exc:  # noqa: BLE001
        return {"status": "no-data", "error": str(exc)}

    try:
        triples = backtest_pairs(df, stats=stats, club_priors=club_priors,
                                 with_dates=True)
    except Exception as exc:  # noqa: BLE001
        return {"status": "backtest-failed", "error": str(exc)}

    all_dates: List = []
    for lst in (triples or {}).values():
        all_dates.extend(d for _, _, d in lst)
    train_dates, test_dates = _split_dates(all_dates, train_frac)
    if not test_dates or not train_dates:
        return {"status": "insufficient-dates",
                "n_train_dates": len(train_dates), "n_test_dates": len(test_dates)}

    # Partition each stat's pairs by match date into TRAIN / TEST.
    train_by_stat: Dict[str, list] = {}
    test_by_stat: Dict[str, list] = {}
    for stat, lst in triples.items():
        train_by_stat[stat] = [(p, y) for p, y, d in lst if d in train_dates]
        test_by_stat[stat] = [(p, y) for p, y, d in lst if d in test_dates]

    n_train = sum(len(v) for v in train_by_stat.values())
    n_test = sum(len(v) for v in test_by_stat.values())

    # Fit on TRAIN only (the honest OOS recalibrator) and IN-SAMPLE on TEST
    # itself (the overfitting reference -- fit and score on the same pairs).
    train_recal = _fit_table(train_by_stat)
    insample_recal = _fit_table(test_by_stat)

    per_stat: Dict[str, dict] = {}
    oos_raw_all: List[Tuple[float, int]] = []
    oos_rec_all: List[Tuple[float, int]] = []
    is_raw_all: List[Tuple[float, int]] = []
    is_rec_all: List[Tuple[float, int]] = []

    for stat, test_pairs in test_by_stat.items():
        if not test_pairs:
            continue
        oos_rec = _apply(stat, test_pairs, train_recal)
        is_rec = _apply(stat, test_pairs, insample_recal)
        raw_s = _score(test_pairs)
        oos_rec_s = _score(oos_rec)
        is_rec_s = _score(is_rec)
        per_stat[stat] = {
            "n_test": len(test_pairs),
            "n_train": len(train_by_stat.get(stat, [])),
            "fitted_oos": stat in train_recal,
            "fitted_insample": stat in insample_recal,
            "raw": raw_s, "oos_recal": oos_rec_s, "insample_recal": is_rec_s,
            "oos_delta": _delta(raw_s, oos_rec_s),
            "insample_delta": _delta(raw_s, is_rec_s),
        }
        oos_raw_all.extend(test_pairs)
        oos_rec_all.extend(oos_rec)
        is_raw_all.extend(test_pairs)
        is_rec_all.extend(is_rec)

    overall_raw = _score(oos_raw_all)
    overall_oos = _score(oos_rec_all)
    overall_is = _score(is_rec_all)
    overall = {
        "raw": overall_raw, "oos_recal": overall_oos, "insample_recal": overall_is,
        "oos_delta": _delta(overall_raw, overall_oos),
        "insample_delta": _delta(overall_raw, overall_is),
    }
    return {
        "status": "ok", "train_frac": train_frac,
        "n_train_dates": len(train_dates), "n_test_dates": len(test_dates),
        "n_train_pairs": n_train, "n_test_pairs": n_test,
        "fitted_oos_stats": sorted(train_recal.keys()),
        "per_stat": per_stat, "overall": overall,
        "verdict": _verdict(overall, per_stat),
    }


def _verdict(overall: dict, per_stat: dict) -> str:
    """Honest one-line verdict from the OVERALL TEST deltas + the in-sample gap."""
    od = overall.get("oos_delta", {})
    idd = overall.get("insample_delta", {})
    db, de = od.get("brier"), od.get("ece")
    if db is None or de is None:
        return "INSUFFICIENT: no scorable TEST pairs."
    fitted = sum(1 for v in per_stat.values() if v.get("fitted_oos"))
    if fitted == 0:
        return ("DEFER: no stat reached MIN_N TRAIN pairs -- recal stayed identity "
                "on TEST (nothing fitted). Need more matches.")
    brier_better = db < -1e-5
    ece_better = de < -1e-5
    gap = ""
    if idd.get("brier") is not None and db is not None:
        gap = (" In-sample Brier delta=%+.5f vs OOS %+.5f (gap=%+.5f is the "
               "overfit tell)." % (idd["brier"], db, db - idd["brier"]))
    if brier_better and ece_better:
        head = ("INTEGRATE-CANDIDATE: recal improves BOTH OOS Brier (%+.5f) and "
                "ECE (%+.5f)." % (db, de))
    elif ece_better and not brier_better:
        head = ("MIXED: recal improves OOS ECE (%+.5f) but NOT Brier (%+.5f) -- "
                "defer; ECE-only gains are weak on a tiny TEST set." % (de, db))
    elif brier_better and not ece_better:
        head = ("MIXED: recal improves OOS Brier (%+.5f) but NOT ECE (%+.5f)."
                % (db, de))
    else:
        head = ("DEFER: recal does NOT improve OOS Brier (%+.5f) or ECE (%+.5f) "
                "-- in-sample-only gain; do not integrate yet." % (db, de))
    return head + gap


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _fmt(d: Optional[dict], keys=_METRICS) -> str:
    if not d:
        return "  -  "
    return "  ".join(
        "%s=%s" % (k, ("  -  " if d.get(k) is None else "%+0.5f" % d[k]))
        if isinstance(d.get(k), float) else "%s=%s" % (k, d.get(k))
        for k in keys)


def _print(res: dict) -> None:
    bar = "-" * 100
    print("=" * 100)
    print("ISOTONIC RECAL -- OUT-OF-SAMPLE TEMPORAL TEST (calibration, NOT a $-edge)")
    print(bar)
    if res.get("status") != "ok":
        print("status=%s  %s" % (res.get("status"), res))
        return
    print("train_frac=%.2f  TRAIN dates=%d pairs=%d  |  TEST dates=%d pairs=%d"
          % (res["train_frac"], res["n_train_dates"], res["n_train_pairs"],
             res["n_test_dates"], res["n_test_pairs"]))
    print("fitted OOS stats (>=MIN_N TRAIN): %s"
          % (", ".join(res["fitted_oos_stats"]) or "NONE"))
    print(bar)
    print("%-16s %-6s %-6s | TEST raw vs OOS-recal delta (rec-raw, <0=better)"
          % ("stat", "nTest", "fit"))
    for stat, v in res["per_stat"].items():
        print("%-16s %-6d %-6s | %s"
              % (stat, v["n_test"], "Y" if v["fitted_oos"] else ".",
                 _fmt(v["oos_delta"])))
    print(bar)
    ov = res["overall"]
    print("OVERALL raw          : %s" % _fmt(ov["raw"]))
    print("OVERALL OOS-recal    : %s" % _fmt(ov["oos_recal"]))
    print("OVERALL insample-rec : %s" % _fmt(ov["insample_recal"]))
    print("OVERALL OOS delta    : %s" % _fmt(ov["oos_delta"]))
    print("OVERALL insample dlt : %s" % _fmt(ov["insample_delta"]))
    print(bar)
    print("VERDICT: %s" % res["verdict"])
    print("=" * 100)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI: python -m scripts.platformkit.recal_eval [--train-frac F] [--data P]."""
    import argparse
    parser = argparse.ArgumentParser(description="Isotonic recal OOS temporal test.")
    parser.add_argument("--train-frac", type=float, default=0.65)
    parser.add_argument("--data", default=None)
    parser.add_argument("--club-priors", action="store_true")
    args = parser.parse_args(argv)
    df = None
    if args.data:
        try:
            import pandas as pd
            df = pd.read_parquet(args.data)
        except Exception as exc:  # noqa: BLE001
            print("Could not read %s: %s" % (args.data, exc))
            return 1
    _print(run_eval(df=df, train_frac=args.train_frac,
                    club_priors=args.club_priors))
    return 0


__all__ = ["run_eval", "main"]

if __name__ == "__main__":
    raise SystemExit(main())
