"""scripts.platformkit.models.registry -- champion/challenger book of record.

Per (sport, market) key: {"champion": SPEC, "challengers": [SPEC, ...]}.
SPEC = {model_id, model_class, impl, benchmark, oos_status, notes}.

model_class in {market_baseline, recalibrated_market, distribution_ladder,
                 gbm, mechanism_stacked, sim}
oos_status  in {BENCHMARKED, PENDING, PLANNED}

Seeded HONESTLY from the real benchmark artifacts and proof modules (2026-07-13
inventory). oos_status=BENCHMARKED is used ONLY where an artifact/module path
below exists on disk today -- see validate(). "Champion" here means the metric
this system's own benchmarks currently favor (usually the devigged market close
-- see docs/JOB_EVIDENCE_PACKET.md and .claude/rules/no-edge-claims.md). This
registry is a POINTER book: it does not wrap or reimplement any of these
modules, it just records where they live and what their last benchmark said.

This is a pure-data module + a thin loader. No classes, no plugin system.
"""

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]

_MODEL_CLASSES = {
    "market_baseline", "recalibrated_market", "distribution_ladder",
    "gbm", "mechanism_stacked", "sim",
}
_OOS_STATUSES = {"BENCHMARKED", "PENDING", "PLANNED"}

REGISTRY = {
    ("mlb", "total_runs"): {
        "champion": {
            "model_id": "mlb_total_runs_market_baseline",
            "model_class": "market_baseline",
            "impl": "scripts.platformkit.benchmarks.crps_market.market_dist",
            "benchmark": "scripts/platformkit/benchmarks/crps_market/last_run_mlb.json",
            "oos_status": "BENCHMARKED",
            "notes": "devigged market Gaussian beats pitch_engine ensemble: model "
                     "CRPS 2.9331 vs market 2.8808, paired delta -0.0523 "
                     "CI[-0.1657,0.0482] n=300 -- CI crosses 0, market wins/ties.",
        },
        "challengers": [
            {
                "model_id": "mlb_total_runs_pitch_engine_ensemble",
                "model_class": "distribution_ladder",
                "impl": "domains.mlb.pitch_engine.game_sim",
                "benchmark": "scripts/platformkit/benchmarks/crps_market/last_run_mlb.json",
                "oos_status": "BENCHMARKED",
                "notes": "trails market_baseline on this benchmark (see champion notes); "
                         "not a proven edge.",
            },
            {
                "model_id": "mlb_total_runs_mechanism_stack",
                "model_class": "mechanism_stacked",
                "impl": "scripts.platformkit.models.mechanism_stack_mlb",
                "benchmark": "data/domains/mlb/mechanism_stack_benchmark.json",
                "oos_status": "BENCHMARKED",
                "notes": "market-implied Gaussian(mu,sigma) + bounded pregame mu-shift (+0.2729 "
                         "runs, capped 0.5) from the 1 ledger mechanism that both clears the "
                         "REPLICATED/CONFIRMED_LOCAL(2corpora)/CONFIRMED(n>=1000) filter and has a "
                         "pregame-knowable trigger (staff-wide day-after fatigue, CONFIRMED_LOCAL, "
                         "2 corpora); 14 other qualifying mechanisms skipped as universal in-game "
                         "dynamics or missing numeric effect. crps_stack 2.8604 vs crps_market 2.8549, "
                         "paired delta -0.0054 CI[-0.0151,0.0036] n=392 -- CI crosses 0, UNDERPOWERED "
                         "(not yet a proven edge; see data/domains/mlb/mechanism_stack_benchmark.json).",
            },
            {
                "model_id": "mlb_total_runs_gbm",
                "model_class": "gbm",
                "impl": "PLANNED",
                "benchmark": "PENDING",
                "oos_status": "PLANNED",
                "notes": "Phase 3 lane to fill in.",
            },
        ],
    },
    ("mlb", "ingame_margin"): {
        "champion": {
            "model_id": "mlb_ingame_margin_market_baseline",
            "model_class": "market_baseline",
            "impl": "scripts.platformkit.benchmarks.crps_market.shape_control",
            "benchmark": "scripts/platformkit/benchmarks/crps_market/last_run_ingame_mlb.json",
            "oos_status": "BENCHMARKED",
            "notes": "shape-matched in-game market baseline; stays champion because every "
                     "checkpoint verdict below is UNDERPOWERED (not yet a proven edge).",
        },
        "challengers": [
            {
                "model_id": "mlb_ingame_margin_pitch_engine_conditional",
                "model_class": "distribution_ladder",
                "impl": "domains.mlb.pitch_engine.game_sim",
                "benchmark": "scripts/platformkit/benchmarks/crps_market/last_run_ingame_mlb.json",
                "oos_status": "BENCHMARKED",
                "notes": "PROVISIONAL: positive CRPS delta at every end_inning_N checkpoint "
                         "(+0.45 .. +1.79, n=20-26/checkpoint) but verdict=UNDERPOWERED "
                         "throughout; memory ingame_crps_provisional_2026_07_11 has the "
                         "n=55 aggregate CI[.41,1.08]. Never quote as a proven edge.",
            },
            {
                "model_id": "mlb_ingame_margin_gbm",
                "model_class": "gbm",
                "impl": "PLANNED",
                "benchmark": "PENDING",
                "oos_status": "PLANNED",
                "notes": "Phase 3 lane to fill in.",
            },
        ],
    },
    ("nba", "ml"): {
        "champion": {
            "model_id": "nba_ml_market_baseline",
            "model_class": "market_baseline",
            "impl": "scripts.platformkit.proof_nba.ml_accuracy",
            "benchmark": "scripts/platformkit/proof_nba/ml_accuracy.py",
            "oos_status": "BENCHMARKED",
            "notes": "devigged close; full-season leak-free WF Brier 0.198 (close) vs "
                     "0.208 (model) -- model MATCHES within noise, does not beat. "
                     "docs/JOB_EVIDENCE_PACKET.md L161-163.",
        },
        "challengers": [
            {
                "model_id": "nba_ml_movelo",
                "model_class": "mechanism_stacked",
                "impl": "domains.basketball_nba.predictor",
                "benchmark": "scripts/platformkit/proof_nba/ml_accuracy.py",
                "oos_status": "BENCHMARKED",
                "notes": "leak-free box-based MOV-aware Elo win-prob; MATCHES devigged "
                         "close within noise (proof_nba.ml_accuracy).",
            },
            {
                "model_id": "nba_ml_gbm",
                "model_class": "gbm",
                "impl": "scripts.platformkit.models.gbm_nba_ml",
                "benchmark": "data/domains/nba/gbm_ml_benchmark.json",
                "oos_status": "BENCHMARKED",
                "notes": "xgboost (device=cuda) on 15 leak-free pregame features (walk-forward "
                         "elo/pace/off-def-ppp/rest/b2b/L10-form; no market inputs); 4 "
                         "chronological expanding-window folds within the single NBA season "
                         "the odds corpus covers (2025-26; 2024-25 box has no market close, "
                         "so the >=2-held-out-season ask isn't supported by this corpus -- "
                         "documented as season_coverage_note in the artifact). Brier: GBM "
                         "0.2375 vs close 0.1836 vs existing elo 0.2067, n=743 -- TRAILS the "
                         "close outside noise (paired delta 0.0539 CI[0.037,0.0707], CI does "
                         "not cross 0). Expected/honest: pregame GBM on a small box corpus "
                         "does not beat the market. Not a proven edge.",
            },
        ],
    },
    ("soccer", "ml"): {
        "champion": {
            "model_id": "soccer_ml_market_baseline",
            "model_class": "market_baseline",
            "impl": "scripts.platformkit.proof_soccer.beat_the_close_1x2",
            "benchmark": "scripts/platformkit/proof_soccer/beat_the_close_1x2.py",
            "oos_status": "BENCHMARKED",
            "notes": "devigged 3-way close; multiclass Brier comparison "
                     "(proof_soccer.beat_the_close_1x2, club-soccer domain).",
        },
        "challengers": [
            {
                "model_id": "soccer_ml_dixon_coles",
                "model_class": "mechanism_stacked",
                "impl": "domains.soccer.scoreline_engine",
                "benchmark": "scripts/platformkit/proof_soccer/beat_the_close_1x2.py",
                "oos_status": "BENCHMARKED",
                "notes": "EW-Poisson attack/defense ratings (domains.soccer.ratings) + "
                         "walk-forward DC rho (domains.soccer.rho_fit) -> bivariate-Poisson "
                         "scoreline matrix -> 1X2. Scored vs devigged 3-way close.",
            },
            {
                "model_id": "soccer_ml_gbm",
                "model_class": "gbm",
                "impl": "PLANNED",
                "benchmark": "PENDING",
                "oos_status": "PLANNED",
                "notes": "Phase 3 lane to fill in.",
            },
        ],
    },
    ("tennis", "match"): {
        "champion": {
            "model_id": "tennis_match_market_baseline",
            "model_class": "market_baseline",
            "impl": "scripts.platformkit.proof_tennis.beat_the_close_ml",
            "benchmark": "scripts/platformkit/proof_tennis/beat_the_close_ml.py",
            "oos_status": "BENCHMARKED",
            "notes": "devigged Pinnacle close (ATP arm); WTA arm in "
                     "proof_tennis/beat_the_close_ml_wta.py.",
        },
        "challengers": [
            {
                "model_id": "tennis_match_elo_platt",
                "model_class": "mechanism_stacked",
                "impl": "domains.tennis.elo_tune",
                "benchmark": "scripts/platformkit/proof_tennis/beat_the_close_ml.py",
                "oos_status": "BENCHMARKED",
                "notes": "leak-free walk-forward surface-blended Elo + leak-free Platt "
                         "recalibration; MATCHES devigged close within noise.",
            },
            {
                "model_id": "tennis_match_gbm",
                "model_class": "gbm",
                "impl": "PLANNED",
                "benchmark": "PENDING",
                "oos_status": "PLANNED",
                "notes": "Phase 3 lane to fill in.",
            },
        ],
    },
}


def get_spec(sport: str, market: str) -> dict:
    """Return {"champion": SPEC, "challengers": [SPEC, ...]} for one (sport, market)."""
    return REGISTRY[(sport, market)]


def all_markets() -> list:
    """Return the sorted list of (sport, market) keys in the registry."""
    return sorted(REGISTRY.keys())


def _module_importable(dotted: str) -> bool:
    try:
        return importlib.util.find_spec(dotted) is not None
    except (ModuleNotFoundError, ImportError, ValueError):
        return False


def _path_exists(rel_path: str) -> bool:
    return (_ROOT / rel_path).is_file()


def _check_impl(spec: dict, issues: list) -> None:
    impl = spec["impl"]
    if impl == "PLANNED":
        return
    if not _module_importable(impl):
        issues.append(f"{spec['model_id']}: impl not importable: {impl}")


def _check_benchmark(spec: dict, issues: list) -> None:
    bench, status = spec["benchmark"], spec["oos_status"]
    if status != "BENCHMARKED":
        return
    if not _path_exists(bench):
        issues.append(f"{spec['model_id']}: oos_status=BENCHMARKED but benchmark "
                       f"missing on disk: {bench}")


def validate() -> list:
    """Return a list of problem strings; empty list means the registry is valid."""
    issues = []
    seen_ids = set()
    for (sport, market), entry in REGISTRY.items():
        champion = entry.get("champion")
        challengers = entry.get("challengers") or []
        if champion is None:
            issues.append(f"{sport}/{market}: missing champion")
        if not challengers:
            issues.append(f"{sport}/{market}: needs >=1 challenger")
        for spec in ([champion] if champion else []) + challengers:
            model_id = spec.get("model_id")
            if model_id in seen_ids:
                issues.append(f"duplicate model_id: {model_id}")
            seen_ids.add(model_id)
            if spec.get("model_class") not in _MODEL_CLASSES:
                issues.append(f"{model_id}: bad model_class {spec.get('model_class')!r}")
            if spec.get("oos_status") not in _OOS_STATUSES:
                issues.append(f"{model_id}: bad oos_status {spec.get('oos_status')!r}")
            _check_impl(spec, issues)
            _check_benchmark(spec, issues)
    return issues


def _fmt_spec(spec: dict) -> str:
    return f"{spec['model_id']}({spec['model_class']},{spec['oos_status']})"


if __name__ == "__main__":
    problems = validate()
    for sport, market in all_markets():
        entry = REGISTRY[(sport, market)]
        challengers = ", ".join(_fmt_spec(c) for c in entry["challengers"])
        print(f"{sport}/{market}: champion={_fmt_spec(entry['champion'])} "
              f"vs challengers=[{challengers}]")
    if problems:
        print(f"\nvalidate(): {len(problems)} issue(s):")
        for p in problems:
            print(f"  - {p}")
    else:
        print("\nvalidate(): OK")
