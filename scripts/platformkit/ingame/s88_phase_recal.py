"""scripts.platformkit.ingame.s88_phase_recal -- S88: per-phase recalibration of the
S06 e4-blend incumbent, scored OOF on the S06 47,104-tick / 158-game partition, with the
phase spec chosen strictly INSIDE the outer walk-forward folds (never on the fold it is
scored on) and clustered CIs restricted to S87 informative ticks.

Row S88 (docs/evidence/HARNESS_GAPS_2026-09-03.md): the one on-disk per-phase run
(mlb_bucket_recalibration.json) picks its winner spec at bucket_recalibration.py:213 by
the lowest Brier on the SAME eval set its CI then rules on -- in-sample. This module
fixes only that: outer expanding GAME-FIRST-DATE walk-forward (mirrors
eval_gate.stacker.outer_walk_forward); at each step the winner between BR.SPECS is
chosen on an INNER holdout carved from the outer-TRAIN dates only, then the chosen spec
is refit on the full outer-train before scoring the held-out date.

Reuse only, nothing reimplemented: bucket_recalibration (BR) for SPECS/_per_game_delta/
_verdict/BURN_IN_FRAC -- its fit/apply machinery is correct, only its winner-selection
was in-sample; state_bucket_benchmark (sb) for phase/margin parsing + the game-clustered
bootstrap; eval_gate.stacker for _first_dates + e4_gd_series (the S06 leak-free e4
incumbent and its exact 47,104/158 denominator); hedge_trial_arms.load_corpus for the
ticks; eval_gate.tick_informative.flag_ticks for the S87 is_informative mask;
ingame.gap_effective_n.effective_sample_size for n_eff.

No FWER charge (row S88 says "no charge"): descriptive only, no ledger write, no
prereg. edge_claimed always False; calibration language only.

INVARIANTS: scripts/platformkit/ only; <=300 LOC; ASCII; no network at import; never
writes data/registry/; never flips a flag; reads ingame_grade_joined READ-ONLY.

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest tests/platformkit/ingame/test_s88_phase_recal.py -q
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd

from scripts.platformkit import hedge_trial_arms as A
from scripts.platformkit.eval_gate.scoring import brier
from scripts.platformkit.eval_gate.stacker import _first_dates, e4_gd_series
from scripts.platformkit.eval_gate.tick_informative import flag_ticks
from scripts.platformkit.ingame import bucket_recalibration as BR
from scripts.platformkit.ingame import state_bucket_benchmark as sb
from scripts.platformkit.ingame.gap_effective_n import effective_sample_size
from scripts.platformkit.ingame_replay_scoreboard import discover_store

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CACHE_ROOT = _REPO_ROOT / "data" / "cache"
DEFAULT_CSV_PATH = _REPO_ROOT / "docs" / "evidence" / "harness" / "s88_phase_recal_2026-09-04.csv"
DEFAULT_JSON_PATH = _REPO_ROOT / "docs" / "evidence" / "harness" / "s88_phase_recal_2026-09-04.json"
INNER_VAL_FRAC = 0.2   # fraction of outer-TRAIN dates held inside the fold for spec selection


def _finite(v: Any) -> bool:
    return v is not None and math.isfinite(float(v))


def build_records(ticks: List[Dict[str, Any]], features: pd.DataFrame) -> List[Dict[str, Any]]:
    """The S06 47,104-tick / 158-game partition. Each record carries the leak-free e4
    incumbent under the key `model_prob` (so BR.SPECS' fit/apply functions -- which
    expect that key -- apply unmodified), the phase|margin bucket, and the GAME-FIRST
    date used for the outer fold (matches e4_gd_series' own leak-free variant)."""
    e4g = e4_gd_series(ticks, features)
    first = _first_dates(ticks)
    scored = [i for i, t in enumerate(ticks) if _finite(e4g[i]) and _finite(t.get("market_prob"))]
    assert (len(scored), len({str(ticks[i]["game"]) for i in scored})) == (47104, 158), \
        "S06 partition denominator drift"
    records: List[Dict[str, Any]] = []
    for i in scored:
        t = ticks[i]
        fields = sb._parse_state_summary(t["raw"].get("state_summary"))
        if "home_score" not in fields or "away_score" not in fields:
            continue
        phase = sb.phase_bucket(fields.get("inning"))
        margin_b = sb.margin_bucket(fields["home_score"], fields["away_score"])
        records.append({
            "game_id": str(t["game"]), "ts": str(t["timestamp"]), "date": first[str(t["game"])],
            "phase_bucket": "%s|%s" % (phase, margin_b), "phase": phase,
            "margin": fields["home_score"] - fields["away_score"],
            "model_prob": float(e4g[i]), "market_prob": float(t["market_prob"]),
            "outcome": float(t["outcome"]),
        })
    return records


def walk_forward_inner_selected(records: List[Dict[str, Any]], *,
                                burn_in_frac: float = BR.BURN_IN_FRAC,
                                inner_val_frac: float = INNER_VAL_FRAC
                                ) -> Tuple[List[Dict[str, Any]], List[str], List[Dict[str, Any]]]:
    """OUTER expanding GAME-FIRST-DATE walk-forward (train = dates < d, score date d); the
    phase spec is picked on an INNER holdout carved from the OUTER-TRAIN dates only (the
    last `inner_val_frac` of them), then the winner is refit on the FULL outer-train
    before applying to date d -- the winner is never selected on the fold it scores."""
    by_date: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in records:
        by_date[r["date"]].append(r)
    dates = sorted(by_date)
    n_burn = max(1, math.ceil(burn_in_frac * len(dates))) if dates else 0
    burn_dates = set(dates[:n_burn])
    out: List[Dict[str, Any]] = []
    train: List[Dict[str, Any]] = []
    fold_choices: List[Dict[str, Any]] = []
    for d in dates:
        day = by_date[d]
        if d in burn_dates:
            for r in day:
                rr = dict(r); rr["recal_prob"], rr["in_burn_in"] = float(r["model_prob"]), True
                out.append(rr)
        else:
            train_dates = sorted({x["date"] for x in train})
            n_inner = max(1, math.ceil(inner_val_frac * len(train_dates)))
            inner_val_dates = set(train_dates[-n_inner:]) if len(train_dates) > n_inner else set()
            inner_train = [x for x in train if x["date"] not in inner_val_dates]
            inner_val = [x for x in train if x["date"] in inner_val_dates]
            spec_name = "phase_platt"   # default when there is no inner holdout yet
            if inner_train and inner_val:
                losses = {}
                for name, (fit_fn, apply_fn) in BR.SPECS.items():
                    m = fit_fn(inner_train)
                    preds = [apply_fn(x, m) for x in inner_val]
                    losses[name] = brier(preds, [x["outcome"] for x in inner_val])
                spec_name = min(losses, key=losses.get)
            fit_fn, apply_fn = BR.SPECS[spec_name]
            model = fit_fn(train)      # refit the CHOSEN spec on the full outer-train
            for r in day:
                rr = dict(r); rr["recal_prob"], rr["in_burn_in"] = apply_fn(r, model), False
                out.append(rr)
            fold_choices.append({"date": d, "spec": spec_name, "n_train": len(train), "n_test": len(day)})
        train.extend(day)
    return out, sorted(burn_dates), fold_choices


def score_bucket(records: List[Dict[str, Any]], *, cluster_column: str = "game_id") -> Dict[str, Any]:
    """Incumbent(e4)/recal/market Brier + game-clustered CIs, INFORMATIVE ticks only."""
    if cluster_column != "game_id":
        records = [dict(r, game_id=str(r[cluster_column])) for r in records]
    n_games = len({r["game_id"] for r in records})
    informative = [r for r in records if r["is_informative"]]
    n_games_inf = len({r["game_id"] for r in informative})
    d_inc = BR._per_game_delta(informative, "model_prob", "recal_prob") if informative else []
    d_mkt = BR._per_game_delta(informative, "market_prob", "recal_prob") if informative else []
    ci_inc, ci_mkt = sb._cluster_bootstrap_ci(d_inc), sb._cluster_bootstrap_ci(d_mkt)
    n_eff = None
    if informative:
        df = pd.DataFrame(informative)
        df["loss_differential"] = (df["model_prob"] - df["outcome"]) ** 2 - (df["recal_prob"] - df["outcome"]) ** 2
        n_eff = float(effective_sample_size(df, game_column="game_id", loss_column="loss_differential")["n_eff"])
    def _b(key: str) -> Any:
        return brier([r[key] for r in informative], [r["outcome"] for r in informative]) if informative else None
    return {
        "n": len(records), "n_games": n_games,
        "n_informative": len(informative), "n_games_informative": n_games_inf, "n_eff": n_eff,
        "brier_incumbent": _b("model_prob"), "brier_recal": _b("recal_prob"), "brier_market": _b("market_prob"),
        "delta_vs_incumbent_mean": (sum(d_inc) / n_games_inf) if n_games_inf else 0.0,
        "delta_vs_incumbent_ci95": list(ci_inc),
        "verdict_vs_incumbent": BR._verdict(ci_inc, n_games_inf, sb.MIN_GAMES, sb.EPS_BRIER, "IMPROVED", "WORSE"),
        "delta_vs_market_mean": (sum(d_mkt) / n_games_inf) if n_games_inf else 0.0,
        "delta_vs_market_ci95": list(ci_mkt),
        "verdict_vs_market": BR._verdict(ci_mkt, n_games_inf, sb.MIN_GAMES, sb.EPS_BRIER, "MODEL_AHEAD", "MODEL_BEHIND"),
    }


def build_report(cache_root: Path = DEFAULT_CACHE_ROOT) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    store = discover_store(cache_root)
    if store is None:
        raise ValueError("no parseable MLB tick store under %s" % cache_root)
    ticks, features = A.load_corpus(store, "mlb")
    records = build_records(ticks, features)
    out, burn_dates, fold_choices = walk_forward_inner_selected(records)
    eval_records = [r for r in out if not r["in_burn_in"]]
    frame = pd.DataFrame(eval_records)
    flagged, inf_summary = flag_ticks(frame, game_col="game_id", ts_col="ts",
                                      market_col="market_prob", model_col="model_prob")
    inf_by_idx = dict(zip(flagged.index, flagged["is_informative"]))
    for i, r in enumerate(eval_records):
        r["is_informative"] = bool(inf_by_idx[i])
    buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in eval_records:
        buckets[r["phase_bucket"]].append(r)
    spec_counts: Dict[str, int] = defaultdict(int)
    for fc in fold_choices:
        spec_counts[fc["spec"]] += 1
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(), "sport": "mlb",
        "partition": "S06 e4-blend incumbent, game-first-date leak-free, 47104 ticks / 158 games",
        "spec_selection": "inner holdout = last %d pct of outer-train dates; never the scored fold" % int(INNER_VAL_FRAC * 100),
        "n_burn_in_dates": len(burn_dates), "n_eval_ticks": len(eval_records),
        "n_informative_ticks": int(inf_summary["n_informative"]),
        "spec_choice_counts": dict(spec_counts), "fold_choices": fold_choices,
        "pooled": score_bucket(eval_records),
        "per_phase_bucket": [dict(score_bucket(buckets[b]), phase_bucket=b) for b in sorted(buckets)],
        "edge_claimed": False, "charge": None,
    }
    return report, eval_records


def write_evidence(report: Dict[str, Any], eval_records: List[Dict[str, Any]],
                   csv_path: Path = DEFAULT_CSV_PATH, json_path: Path = DEFAULT_JSON_PATH) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=1, sort_keys=True, default=str), "ascii")
    cols = ["game_id", "ts", "phase_bucket", "is_informative", "outcome",
           "model_prob", "recal_prob", "market_prob"]
    pd.DataFrame(eval_records)[cols].to_csv(csv_path, index=False)


def main() -> int:
    report, eval_records = build_report()
    write_evidence(report, eval_records)
    pooled = report["pooled"]
    print("S88 pooled n_informative=%d verdict_vs_incumbent=%s verdict_vs_market=%s" % (
        pooled["n_informative"], pooled["verdict_vs_incumbent"], pooled["verdict_vs_market"]))
    for row in report["per_phase_bucket"]:
        print("  %s n=%d n_informative=%d verdict_vs_incumbent=%s delta=%.6f ci95=%s" % (
            row["phase_bucket"], row["n"], row["n_informative"], row["verdict_vs_incumbent"],
            row["delta_vs_incumbent_mean"], row["delta_vs_incumbent_ci95"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
