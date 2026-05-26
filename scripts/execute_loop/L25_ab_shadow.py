"""L25_ab_shadow.py — A/B Shadow Harness (execute_loop layer 25).

Storage:
    data/shadow/_registry.json          — active variant registry
    data/shadow/<variant_name>/
        predictions.parquet             — (game_id, player, stat, predicted_q50, ts)
        summary.json                    — written only when settled

All disk writes use atomic tmp → replace so a crash never leaves a partial file.

Environment Variables:
    L25_SHADOW_ROOT   Override shadow storage directory (default: data/shadow/).
    L25_LEDGER_DIR    Override ledger directory (default: data/ledger/).

Paper vs Live Mode:
    This module is data-only — it writes shadow predictions and reads the L07
    ledger for settlement.  It does NOT place bets.  No paper/live distinction
    is needed; all shadow runs are inherently paper (observation only).

CLI:
    python L25_ab_shadow.py status                   # list_active_shadows table
    python L25_ab_shadow.py settle --variant <name>
    python L25_ab_shadow.py compare --variant <name>
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_PROJECT_DIR = Path(__file__).resolve().parents[3]
_SHADOW_ROOT = str(_PROJECT_DIR / "data" / "shadow")
_REGISTRY_FILE = Path(_SHADOW_ROOT) / "_registry.json"
_LEDGER_DIR = _PROJECT_DIR / "data" / "ledger"
_BETS_FILE = _LEDGER_DIR / "bets.parquet"
_BETS_CSV = _LEDGER_DIR / "bets.csv"

_STAT_RE = re.compile(r"player_prop_(\w+)")
_UNSTABLE_ERROR_THRESHOLD = 5

# ---------------------------------------------------------------------------
# Parquet / CSV helpers
# ---------------------------------------------------------------------------
try:
    import pyarrow  # noqa: F401
    _HAS_PARQUET = True
except ImportError:
    _HAS_PARQUET = False


def _read_df(path_parquet: Path, path_csv: Path) -> pd.DataFrame:
    if _HAS_PARQUET and path_parquet.exists():
        return pd.read_parquet(path_parquet)
    if path_csv.exists():
        return pd.read_csv(path_csv, dtype=str)
    return pd.DataFrame()


def _write_df(df: pd.DataFrame, path_parquet: Path, path_csv: Path) -> None:
    path_parquet.parent.mkdir(parents=True, exist_ok=True)
    if _HAS_PARQUET:
        tmp = path_parquet.with_suffix(".tmp.parquet")
        df.to_parquet(tmp, index=False)
        tmp.replace(path_parquet)
    else:
        tmp = path_csv.with_suffix(".tmp.csv")
        df.to_csv(tmp, index=False)
        tmp.replace(path_csv)


def _predictions_paths(variant_name: str) -> tuple[Path, Path]:
    base = Path(_SHADOW_ROOT) / variant_name
    return base / "predictions.parquet", base / "predictions.csv"


def _load_predictions(variant_name: str) -> pd.DataFrame:
    pq, csv = _predictions_paths(variant_name)
    return _read_df(pq, csv)


def _save_predictions(variant_name: str, df: pd.DataFrame) -> None:
    pq, csv = _predictions_paths(variant_name)
    _write_df(df, pq, csv)


def _load_bets() -> pd.DataFrame:
    return _read_df(_BETS_FILE, _BETS_CSV)


# ---------------------------------------------------------------------------
# Registry helpers
# ---------------------------------------------------------------------------
def _load_registry() -> dict:
    if _REGISTRY_FILE.exists():
        try:
            return json.loads(_REGISTRY_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            log.warning("registry file unreadable — returning empty")
    return {}


def _save_registry(registry: dict) -> None:
    Path(_SHADOW_ROOT).mkdir(parents=True, exist_ok=True)
    tmp = _REGISTRY_FILE.with_suffix(".tmp.json")
    tmp.write_text(json.dumps(registry, indent=2), encoding="utf-8")
    tmp.replace(_REGISTRY_FILE)


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------
@dataclass
class ShadowRun:
    variant_name: str
    started_at: str          # ISO-8601
    n_games_target: int
    n_games_actual: int
    predictor_repr: str


@dataclass
class ShadowSummary:
    variant_name: str
    n_predictions: int
    mae_per_stat: dict
    vs_production_mae_delta: dict
    promotion_recommendation: str   # "PROMOTE" | "REJECT" | "INCONCLUSIVE"


@dataclass
class ComparisonResult:
    variant_name: str
    per_stat: dict   # {stat: {variant_mae, prod_mae, delta, n}}
    verdict: str
    reason: str


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def start_shadow(
    variant_name: str,
    predictor_callable: Callable,
    n_games: int = 50,
) -> ShadowRun:
    """Register a new shadow variant.

    Raises ValueError if variant_name already exists in the registry.
    The predictor_callable is NOT invoked here — it is stored as repr only.
    """
    registry = _load_registry()
    if variant_name in registry:
        raise ValueError(
            f"Shadow variant {variant_name!r} already exists "
            f"(status={registry[variant_name].get('status')}). "
            "Use a different name or remove the existing entry first."
        )

    shadow_dir = Path(_SHADOW_ROOT) / variant_name
    shadow_dir.mkdir(parents=True, exist_ok=True)

    started_at = datetime.now(timezone.utc).isoformat()
    registry[variant_name] = {
        "started_at": started_at,
        "n_games_target": n_games,
        "predictor_repr": repr(predictor_callable),
        "error_count": 0,
        "status": "active",
    }
    _save_registry(registry)

    log.info("start_shadow: registered variant=%s n_games=%d", variant_name, n_games)
    return ShadowRun(
        variant_name=variant_name,
        started_at=started_at,
        n_games_target=n_games,
        n_games_actual=0,
        predictor_repr=repr(predictor_callable),
    )


def record_prediction(
    variant_name: str,
    game_id: str,
    player: str,
    stat: str,
    predicted_q50: Optional[float],
) -> None:
    """Append one prediction row to the variant's predictions file.

    predicted_q50=None records a predictor failure.
    After _UNSTABLE_ERROR_THRESHOLD None values the variant is marked unstable.
    ISOLATION: always writes inside _SHADOW_ROOT — enforced via assert.
    """
    pq, csv = _predictions_paths(variant_name)
    out_path = pq if _HAS_PARQUET else csv
    assert str(out_path).startswith(_SHADOW_ROOT), (
        f"ISOLATION VIOLATION: {out_path} is not inside {_SHADOW_ROOT}"
    )

    is_error = predicted_q50 is None or (
        isinstance(predicted_q50, float) and math.isnan(predicted_q50)
    )

    ts = datetime.now(timezone.utc).isoformat()
    new_row = pd.DataFrame([{
        "game_id": str(game_id),
        "player": str(player),
        "stat": str(stat),
        "predicted_q50": float("nan") if is_error else float(predicted_q50),
        "ts": ts,
    }])

    existing = _load_predictions(variant_name)
    combined = (
        pd.concat([existing, new_row], ignore_index=True)
        if not existing.empty
        else new_row
    )
    _save_predictions(variant_name, combined)

    if is_error:
        registry = _load_registry()
        if variant_name in registry:
            registry[variant_name]["error_count"] = (
                registry[variant_name].get("error_count", 0) + 1
            )
            if registry[variant_name]["error_count"] >= _UNSTABLE_ERROR_THRESHOLD:
                registry[variant_name]["status"] = "unstable"
                log.warning(
                    "record_prediction: variant=%s marked unstable after %d errors",
                    variant_name,
                    registry[variant_name]["error_count"],
                )
            _save_registry(registry)

    log.debug(
        "record_prediction: variant=%s game=%s player=%s stat=%s q50=%s",
        variant_name, game_id, player, stat,
        "NULL" if is_error else f"{predicted_q50:.3f}",
    )


def settle_shadow(variant_name: str) -> ShadowSummary:
    """Compute MAE by comparing shadow predictions against the L07 ledger.

    - Joins shadow predictions with settled ledger rows on (game_id, player, stat).
    - Drops rows where predicted_q50 IS NULL or prod_q50 IS NULL.
    - Returns INCONCLUSIVE (without writing summary.json) if n_games_actual < n_games_target.
    - Otherwise writes summary.json and marks registry status='settled'.
    """
    registry = _load_registry()
    entry = registry.get(variant_name, {})
    n_games_target = int(entry.get("n_games_target", 50))

    # Load shadow predictions
    shadow_df = _load_predictions(variant_name)
    if shadow_df.empty:
        return ShadowSummary(
            variant_name=variant_name,
            n_predictions=0,
            mae_per_stat={},
            vs_production_mae_delta={},
            promotion_recommendation="INCONCLUSIVE",
        )

    # Coerce predicted_q50 to numeric
    shadow_df["predicted_q50"] = pd.to_numeric(shadow_df["predicted_q50"], errors="coerce")
    shadow_df = shadow_df.dropna(subset=["predicted_q50"])

    # Load ledger
    bets_df = _load_bets()
    if bets_df.empty:
        return ShadowSummary(
            variant_name=variant_name,
            n_predictions=len(shadow_df),
            mae_per_stat={},
            vs_production_mae_delta={},
            promotion_recommendation="INCONCLUSIVE",
        )

    # Filter settled bets
    settled_statuses = {"WON", "LOST", "PUSH"}
    bets_df = bets_df[
        bets_df["status"].str.upper().isin(settled_statuses)
    ].copy()

    # Extract stat from market column if stat column absent / empty
    if "stat" not in bets_df.columns or bets_df["stat"].astype(str).str.strip().eq("").all():
        bets_df["stat"] = (
            bets_df.get("market", pd.Series(dtype=str))
            .astype(str)
            .str.extract(_STAT_RE, expand=False)
        )

    # Keep only cols needed
    keep_cols = ["game_id", "player", "stat", "actual_value", "model_q50"]
    for col in keep_cols:
        if col not in bets_df.columns:
            bets_df[col] = None

    bets_df = bets_df[keep_cols].copy()
    bets_df["actual_value"] = pd.to_numeric(bets_df["actual_value"], errors="coerce")
    bets_df["model_q50"] = pd.to_numeric(bets_df["model_q50"], errors="coerce")
    bets_df = bets_df.dropna(subset=["actual_value", "model_q50"])

    # Normalise join keys
    for df_ref in [shadow_df, bets_df]:
        for col in ["game_id", "player", "stat"]:
            if col in df_ref.columns:
                df_ref[col] = df_ref[col].astype(str).str.strip().str.lower()

    # Inner join
    joined = shadow_df.merge(
        bets_df,
        on=["game_id", "player", "stat"],
        how="inner",
    )

    if joined.empty:
        return ShadowSummary(
            variant_name=variant_name,
            n_predictions=len(shadow_df),
            mae_per_stat={},
            vs_production_mae_delta={"_reason": "no_overlap_with_prod"},
            promotion_recommendation="INCONCLUSIVE",
        )

    n_games_actual = joined["game_id"].nunique()

    # Compute MAE per stat
    joined["abs_err_shadow"] = (joined["predicted_q50"] - joined["actual_value"]).abs()
    joined["abs_err_prod"] = (joined["model_q50"] - joined["actual_value"]).abs()

    mae_per_stat: dict[str, float] = {}
    vs_prod_delta: dict[str, float] = {}

    for stat, grp in joined.groupby("stat"):
        mae_per_stat[stat] = float(grp["abs_err_shadow"].mean())
        prod_mae = float(grp["abs_err_prod"].mean())
        vs_prod_delta[stat] = round(mae_per_stat[stat] - prod_mae, 6)

    if n_games_actual < n_games_target:
        log.info(
            "settle_shadow: variant=%s only %d/%d games — INCONCLUSIVE",
            variant_name, n_games_actual, n_games_target,
        )
        return ShadowSummary(
            variant_name=variant_name,
            n_predictions=len(shadow_df),
            mae_per_stat=mae_per_stat,
            vs_production_mae_delta=vs_prod_delta,
            promotion_recommendation="INCONCLUSIVE",
        )

    # Determine promotion recommendation
    rec = _promotion_recommendation(joined)

    summary = ShadowSummary(
        variant_name=variant_name,
        n_predictions=len(shadow_df),
        mae_per_stat={k: round(v, 6) for k, v in mae_per_stat.items()},
        vs_production_mae_delta={k: round(v, 6) for k, v in vs_prod_delta.items()},
        promotion_recommendation=rec,
    )

    # Persist summary.json
    summary_path = Path(_SHADOW_ROOT) / variant_name / "summary.json"
    summary_path.write_text(json.dumps(asdict(summary), indent=2), encoding="utf-8")

    # Update registry
    if variant_name in registry:
        registry[variant_name]["status"] = "settled"
        _save_registry(registry)

    log.info(
        "settle_shadow: variant=%s n_games=%d recommendation=%s",
        variant_name, n_games_actual, rec,
    )
    return summary


def compare_to_prod(variant_name: str) -> ComparisonResult:
    """Build per-stat comparison table and emit a PROMOTE/REJECT/INCONCLUSIVE verdict."""
    shadow_df = _load_predictions(variant_name)
    if shadow_df.empty:
        return ComparisonResult(
            variant_name=variant_name,
            per_stat={},
            verdict="INCONCLUSIVE",
            reason="no_shadow_predictions",
        )

    shadow_df["predicted_q50"] = pd.to_numeric(shadow_df["predicted_q50"], errors="coerce")
    shadow_df = shadow_df.dropna(subset=["predicted_q50"])

    bets_df = _load_bets()
    if bets_df.empty:
        return ComparisonResult(
            variant_name=variant_name,
            per_stat={},
            verdict="INCONCLUSIVE",
            reason="no_prod_bets",
        )

    settled_statuses = {"WON", "LOST", "PUSH"}
    bets_df = bets_df[bets_df["status"].str.upper().isin(settled_statuses)].copy()

    if "stat" not in bets_df.columns or bets_df["stat"].astype(str).str.strip().eq("").all():
        bets_df["stat"] = (
            bets_df.get("market", pd.Series(dtype=str))
            .astype(str)
            .str.extract(_STAT_RE, expand=False)
        )

    keep_cols = ["game_id", "player", "stat", "actual_value", "model_q50"]
    for col in keep_cols:
        if col not in bets_df.columns:
            bets_df[col] = None
    bets_df = bets_df[keep_cols].copy()
    bets_df["actual_value"] = pd.to_numeric(bets_df["actual_value"], errors="coerce")
    bets_df["model_q50"] = pd.to_numeric(bets_df["model_q50"], errors="coerce")
    bets_df = bets_df.dropna(subset=["actual_value", "model_q50"])

    for df_ref in [shadow_df, bets_df]:
        for col in ["game_id", "player", "stat"]:
            if col in df_ref.columns:
                df_ref[col] = df_ref[col].astype(str).str.strip().str.lower()

    joined = shadow_df.merge(bets_df, on=["game_id", "player", "stat"], how="inner")

    if joined.empty:
        return ComparisonResult(
            variant_name=variant_name,
            per_stat={},
            verdict="INCONCLUSIVE",
            reason="no_overlap_with_prod",
        )

    joined["abs_err_shadow"] = (joined["predicted_q50"] - joined["actual_value"]).abs()
    joined["abs_err_prod"] = (joined["model_q50"] - joined["actual_value"]).abs()

    per_stat: dict[str, dict] = {}
    for stat, grp in joined.groupby("stat"):
        variant_mae = float(grp["abs_err_shadow"].mean())
        prod_mae = float(grp["abs_err_prod"].mean())
        per_stat[stat] = {
            "variant_mae": round(variant_mae, 6),
            "prod_mae": round(prod_mae, 6),
            "delta": round(variant_mae - prod_mae, 6),
            "n": len(grp),
        }

    verdict, reason = _compute_verdict(per_stat)
    return ComparisonResult(
        variant_name=variant_name,
        per_stat=per_stat,
        verdict=verdict,
        reason=reason,
    )


def list_active_shadows() -> list[ShadowRun]:
    """Return all shadow variants from the registry."""
    registry = _load_registry()
    out: list[ShadowRun] = []
    for name, entry in registry.items():
        shadow_df = _load_predictions(name)
        n_actual = int(shadow_df["game_id"].nunique()) if not shadow_df.empty else 0
        out.append(ShadowRun(
            variant_name=name,
            started_at=entry.get("started_at", ""),
            n_games_target=int(entry.get("n_games_target", 0)),
            n_games_actual=n_actual,
            predictor_repr=entry.get("predictor_repr", ""),
        ))
    return out


# ---------------------------------------------------------------------------
# L41 integration
# ---------------------------------------------------------------------------
def shadow_compare_from_l41(harness_report: dict) -> dict:
    """Run a shadow comparison driven by an L41 IntegrationHarness report.

    Takes a harness_report dict as produced by L41.IntegrationHarness and
    extracts champion / challenger variant names, then calls compare_to_prod
    on the challenger (if present) and settle_shadow on both variants.

    Expected harness_report structure (all keys optional — function degrades
    gracefully if keys are absent)::

        {
            "champion_variant": "model_v3",       # name in shadow registry
            "challenger_variant": "model_v4",     # name to compare
            "game_ids": ["00225..."],             # unused here, for context
            ...
        }

    Returns
    -------
    dict with keys:
        champion_variant   : str | None
        challenger_variant : str | None
        champion_summary   : ShadowSummary as dict | None
        challenger_compare : ComparisonResult as dict | None
        verdict            : "PROMOTE" | "REJECT" | "INCONCLUSIVE" | "NO_CHALLENGER"
        reason             : str
    """
    from dataclasses import asdict

    champion_variant: Optional[str] = harness_report.get("champion_variant")
    challenger_variant: Optional[str] = harness_report.get("challenger_variant")

    result: dict = {
        "champion_variant": champion_variant,
        "challenger_variant": challenger_variant,
        "champion_summary": None,
        "challenger_compare": None,
        "verdict": "NO_CHALLENGER",
        "reason": "no_challenger_in_harness_report",
    }

    if not challenger_variant:
        log.info(
            "shadow_compare_from_l41: no challenger_variant in report — skipping"
        )
        return result

    # Settle champion if present
    if champion_variant:
        registry = _load_registry()
        if champion_variant in registry:
            champ_summary = settle_shadow(champion_variant)
            result["champion_summary"] = asdict(champ_summary)
        else:
            log.info(
                "shadow_compare_from_l41: champion=%s not in shadow registry",
                champion_variant,
            )

    # Compare challenger
    registry = _load_registry()
    if challenger_variant not in registry:
        result["verdict"] = "INCONCLUSIVE"
        result["reason"] = f"challenger {challenger_variant!r} not in shadow registry"
        log.warning(
            "shadow_compare_from_l41: challenger=%s not in registry", challenger_variant
        )
        return result

    comp = compare_to_prod(challenger_variant)
    result["challenger_compare"] = {
        "variant_name": comp.variant_name,
        "per_stat": comp.per_stat,
        "verdict": comp.verdict,
        "reason": comp.reason,
    }
    result["verdict"] = comp.verdict
    result["reason"] = comp.reason

    log.info(
        "shadow_compare_from_l41: challenger=%s verdict=%s reason=%s",
        challenger_variant,
        comp.verdict,
        comp.reason,
    )
    return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _promotion_recommendation(joined: pd.DataFrame) -> str:
    """Derive PROMOTE/REJECT/INCONCLUSIVE from a joined DataFrame."""
    per_stat: dict[str, dict] = {}
    joined["abs_err_shadow"] = (joined["predicted_q50"] - joined["actual_value"]).abs()
    joined["abs_err_prod"] = (joined["model_q50"] - joined["actual_value"]).abs()
    for stat, grp in joined.groupby("stat"):
        per_stat[stat] = {
            "variant_mae": float(grp["abs_err_shadow"].mean()),
            "prod_mae": float(grp["abs_err_prod"].mean()),
            "delta": float(grp["abs_err_shadow"].mean() - grp["abs_err_prod"].mean()),
            "n": len(grp),
        }
    verdict, _ = _compute_verdict(per_stat)
    return verdict


def _compute_verdict(per_stat: dict) -> tuple[str, str]:
    """PROMOTE / REJECT / INCONCLUSIVE logic.

    PROMOTE : every stat delta < 0 AND every stat n >= 30
    REJECT  : any stat delta > 0 with n >= 30
    INCONCLUSIVE: mixed signs or small n
    """
    if not per_stat:
        return "INCONCLUSIVE", "no_stats"

    confident_stats = {s: v for s, v in per_stat.items() if v["n"] >= 30}
    all_negative = all(v["delta"] < 0 for v in confident_stats.values()) if confident_stats else False
    covers_all = len(confident_stats) == len(per_stat)

    if all_negative and covers_all:
        return "PROMOTE", "all_stats_improved_n>=30"

    any_positive_confident = any(
        v["delta"] > 0 for v in confident_stats.values()
    )
    if any_positive_confident:
        culprits = [s for s, v in confident_stats.items() if v["delta"] > 0]
        return "REJECT", f"stat(s)_regressed_n>=30: {','.join(culprits)}"

    return "INCONCLUSIVE", "mixed_signs_or_small_n"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _cli_status(args) -> None:  # noqa: ARG001
    shadows = list_active_shadows()
    registry = _load_registry()
    if not shadows:
        print("[L25] no shadow variants registered")
        return
    hdr = f"  {'variant':<30}  {'status':>10}  {'started':>25}  {'target':>7}  {'actual':>7}  {'errors':>7}"
    print("[L25] active shadow variants")
    print(hdr)
    for s in shadows:
        entry = registry.get(s.variant_name, {})
        status = entry.get("status", "?")
        errors = entry.get("error_count", 0)
        print(
            f"  {s.variant_name:<30}  {status:>10}  {s.started_at[:19]:>25}  "
            f"{s.n_games_target:>7}  {s.n_games_actual:>7}  {errors:>7}"
        )


def _cli_settle(args) -> None:
    summary = settle_shadow(args.variant)
    print(f"[L25] settle variant={args.variant}")
    print(f"  recommendation : {summary.promotion_recommendation}")
    print(f"  n_predictions  : {summary.n_predictions}")
    for stat, mae in sorted(summary.mae_per_stat.items()):
        delta = summary.vs_production_mae_delta.get(stat, float("nan"))
        print(f"  {stat:<8} mae={mae:.4f}  vs_prod={delta:+.4f}")


def _cli_compare(args) -> None:
    result = compare_to_prod(args.variant)
    print(f"[L25] compare variant={args.variant}  verdict={result.verdict}  reason={result.reason}")
    hdr = f"  {'stat':<8}  {'variant_mae':>12}  {'prod_mae':>10}  {'delta':>10}  {'n':>6}"
    print(hdr)
    for stat, row in sorted(result.per_stat.items()):
        print(
            f"  {stat:<8}  {row['variant_mae']:>12.4f}  {row['prod_mae']:>10.4f}  "
            f"  {row['delta']:>+9.4f}  {row['n']:>6}"
        )


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    p = argparse.ArgumentParser(prog="L25_ab_shadow")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="List all shadow variants").set_defaults(func=_cli_status)

    p_settle = sub.add_parser("settle", help="Settle a shadow variant")
    p_settle.add_argument("--variant", required=True)
    p_settle.set_defaults(func=_cli_settle)

    p_compare = sub.add_parser("compare", help="Compare variant to production")
    p_compare.add_argument("--variant", required=True)
    p_compare.set_defaults(func=_cli_compare)

    args = p.parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
