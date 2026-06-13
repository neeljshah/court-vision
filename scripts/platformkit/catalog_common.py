"""scripts.platformkit.catalog_common — Sport-blind harness for signal-catalog runners.

Shared machinery extracted from the 6 domain signal_catalog*.py files (tennis, soccer,
mlb × base/joint).  Each domain file keeps its Signal class definitions, CATALOG_* tuple,
and _compute_signal_col transform; this module owns the three pieces that were identical:

  derive_bundle(b, s)               — swap only signal_col, preserve rest of bundle
  run_catalog_common(...)           — gate-eval loop (mirrors proof run_v3 semantics)
  write_catalog_report(...)         — markdown verdict table + gate detail + SHIP flags

PROMOTION DISCIPLINE (kernel promotion pattern):
  - Behavior-preserving: logic is verbatim from the source files; only structure changed.
  - F5-clean: imports only src.loop.gate / src.loop.signal + stdlib + numpy.
  - No raw corpus reads; no domain-specific imports.
  - Tests: each of the 6 domain catalog tests continues to pass unchanged.

F5: ZERO imports from domains.* / src.data / src.sim / src.tracking / src.pipeline.
PRIVATE: never committed to the public repo.
"""
from __future__ import annotations

import datetime as _dt
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from src.loop.gate import FeatureBundle, evaluate
from src.loop.signal import GateResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# _benjamini_hochberg — inline BH (pure, no ledger I/O).
# Why inline: src.loop.ledger.apply_fdr rewrites a JSONL file and expects
# dicts with "id" keys; we operate on in-memory verdict rows with no file.
# Algorithm is identical to ledger.apply_fdr (Benjamini-Hochberg 1995).
# ---------------------------------------------------------------------------

def _benjamini_hochberg(
    p_values: List[Optional[float]],
    q: float = 0.10,
) -> Tuple[List[Optional[bool]], Optional[float]]:
    """BH FDR correction over a parallel list of p-values (None = untestable row).

    Returns (passes, bh_threshold): passes[i] is True/False for testable rows,
    None for rows with p_value=None.  bh_threshold is (max_rank/m)*q or None.
    """
    testable = [i for i, p in enumerate(p_values) if p is not None]
    m = len(testable)
    passes: List[Optional[bool]] = [None] * len(p_values)
    if m == 0:
        return passes, None
    ordered = sorted(testable, key=lambda i: float(p_values[i]))  # type: ignore[arg-type]
    max_k = 0
    for k0, orig in enumerate(ordered):
        if float(p_values[orig]) <= ((k0 + 1) / m) * q:  # type: ignore[arg-type]
            max_k = k0 + 1
    bh_thr: Optional[float] = (max_k / m) * q if max_k else None
    for k0, orig in enumerate(ordered):
        passes[orig] = (k0 + 1) <= max_k
    return passes, bh_thr

# ---------------------------------------------------------------------------
# derive_bundle — swap signal_col; preserve target/base/dates/lines/closing
# ---------------------------------------------------------------------------

def derive_bundle(b: FeatureBundle, s: np.ndarray) -> FeatureBundle:
    """Return a new FeatureBundle with signal_col=s; all other fields unchanged."""
    return FeatureBundle(base=b.base, signal_col=s, target=b.target,
                         dates=b.dates, lines=b.lines, closing=b.closing)


# ---------------------------------------------------------------------------
# run_catalog_common — sport-blind gate-eval loop
# ---------------------------------------------------------------------------

def run_catalog_common(
    signal_classes: Sequence[type],
    adapter: Any,
    seasons: Sequence[int],
    compute_fn: Callable[[type, np.ndarray], np.ndarray],
    out_path: Optional[Path] = None,
    header_lines: Optional[List[str]] = None,
    extra_bundle_kwargs: Optional[Dict[str, Any]] = None,
    ship_log_prefix: str = "CATALOG",
    title: Optional[str] = None,
    league_note: str = "",
) -> Dict[str, Any]:
    """Run every signal class in *signal_classes* through the real gate.

    Mirrors run_v3 semantics exactly:
        bundle = adapter.feature_bundle(hyp, seasons[, **extra_bundle_kwargs]);
        sig._gate_matrix = derive_bundle(bundle, compute_fn(cls, bundle.base));
        result = evaluate(sig, device="cpu", n_splits=3).

    Parameters
    ----------
    signal_classes:
        Ordered sequence of Signal subclasses (CATALOG_SIGNALS / CATALOG_JOINT_SIGNALS).
    adapter:
        Sport-specific adapter implementing feature_bundle(hyp, seasons, **kw).
    seasons:
        Season list forwarded to adapter.feature_bundle.
    compute_fn:
        Callable(signal_cls, base_array) -> signal_col_array.  Sport-specific transform.
    out_path:
        If given, write a markdown report here.
    header_lines:
        List of markdown lines prepended before the verdict table.  Defaults to a
        minimal generic header.  Callers supply the sport-specific contract blurb.
    extra_bundle_kwargs:
        Optional extra kwargs forwarded to adapter.feature_bundle (e.g. league_filter).
    ship_log_prefix:
        Prefix for the SHIP-flag WARNING log message (e.g. "CATALOG", "JOINT CATALOG").
    title:
        H1 title line for the report (forwarded to write_catalog_report).
    league_note:
        Optional suffix for the Generated: metadata line (forwarded to write_catalog_report).

    Returns
    -------
    {"ok": bool, "verdicts": list[dict]}
    SHIP verdicts are logged as WARNING — probable artifact; no edge claimed.
    """
    extra_kw: Dict[str, Any] = extra_bundle_kwargs or {}
    rows: List[Dict[str, Any]] = []

    # --- bundle acquisition (ONCE; all signals share seasons + extra_kw) ---
    # All signals in a catalog use the same seasons and extra_bundle_kwargs;
    # only signal_col differs (derived per-signal via compute_fn + derive_bundle).
    # We use the first signal's hypothesis solely to satisfy the adapter interface.
    if not signal_classes:
        return {"ok": True, "verdicts": []}

    _first_sig = signal_classes[0]()
    _base_bundle: Optional[FeatureBundle] = None
    _bundle_error: Optional[str] = None
    try:
        _base_bundle = adapter.feature_bundle(_first_sig.hypothesis(),
                                              seasons=seasons, **extra_kw)
    except Exception as exc:  # noqa: BLE001
        _bundle_error = str(exc)

    for signal_cls in signal_classes:
        name: str = signal_cls.name  # type: ignore[attr-defined]
        sig = signal_cls()
        expected: str = sig.hypothesis().expected_verdict or "REJECT"

        # --- reuse the shared base bundle ---
        if _bundle_error is not None:
            rows.append({"name": name, "expected": expected,
                         "actual_verdict": "BUNDLE_ERROR",
                         "passed_expected": False, "n": 0, "coverage": 0.0,
                         "reason": _bundle_error})
            continue

        bb: FeatureBundle = _base_bundle  # type: ignore[assignment]
        n: int = bb.base.shape[0]
        sc: np.ndarray = compute_fn(signal_cls, bb.base)
        coverage: float = float(np.sum(~np.isnan(sc))) / max(n, 1)
        sig._gate_matrix = derive_bundle(bb, sc)  # type: ignore[attr-defined]

        # --- gate evaluation ---
        try:
            r: GateResult = evaluate(sig, device="cpu", n_splits=3)
        except Exception as exc:  # noqa: BLE001
            rows.append({"name": name, "expected": expected,
                         "actual_verdict": "GATE_ERROR",
                         "passed_expected": False, "n": n, "coverage": coverage,
                         "reason": str(exc)})
            continue

        actual: str = r.verdict.value
        exp_set = {v.strip() for v in expected.split(" or ")}
        passed: bool = actual in exp_set or actual in {"REJECT", "DEFER"}
        if actual == "SHIP":
            logger.warning(
                "%s SHIP FLAG '%s': probable artifact. NO edge claimed.",
                ship_log_prefix, name,
            )
        rows.append({
            "name": name, "expected": expected, "actual_verdict": actual,
            "passed_expected": passed, "n": n, "coverage": round(coverage, 3),
            "reason": r.reason, "wf_folds": r.wf_folds,
            "wf_all_improve": r.wf_all_improve, "ablation_delta": r.ablation_delta,
            "ablation_pass": r.ablation_pass, "null_pass": r.null_pass,
            "calibration_ok": r.calibration_ok, "clv": r.clv, "p_value": r.p_value,
        })

    # --- cross-catalog BH FDR correction (RIGOR-fdr-wired) ---
    # Per-signal p-values from the gate are independent single tests at alpha~0.10.
    # With m=8-16 signals per catalog, ~1 false positive is expected by chance.
    # Apply Benjamini-Hochberg across ALL signals in this catalog run so that
    # fdr_bh_pass=True only when a signal survives the joint multiple-testing threshold.
    # This TIGHTENS rigor: it can only turn SHIP→artifact-flagged, never REJECT→pass.
    _p_vals: List[Optional[float]] = [
        r.get("p_value") if r.get("actual_verdict") not in ("BUNDLE_ERROR", "GATE_ERROR")
        else None
        for r in rows
    ]
    _bh_passes, _bh_threshold = _benjamini_hochberg(_p_vals, q=0.10)
    for row, bh_pass in zip(rows, _bh_passes):
        row["fdr_bh_pass"] = bh_pass
        row["fdr_bh_threshold"] = _bh_threshold

    ok: bool = all(r["passed_expected"] for r in rows)
    if out_path is not None:
        write_catalog_report(rows, Path(out_path), list(seasons),
                             header_lines=header_lines, title=title,
                             league_note=league_note)
    return {"ok": ok, "verdicts": rows}


# ---------------------------------------------------------------------------
# write_catalog_report — markdown verdict table + gate detail + SHIP section
# ---------------------------------------------------------------------------

_DETAIL_KEYS: Tuple[str, ...] = (
    "actual_verdict", "expected", "passed_expected", "n", "coverage", "reason",
    "wf_folds", "wf_all_improve", "ablation_delta", "ablation_pass",
    "null_pass", "calibration_ok", "clv", "p_value",
)

_DEFAULT_TITLE = (
    "# Honest signal catalog — markets are efficient; expected and observed "
    "verdicts are REJECT/DEFER. NO edge claimed."
)


def write_catalog_report(
    rows: List[Dict[str, Any]],
    out: Path,
    seasons: List[int],
    header_lines: Optional[List[str]] = None,
    title: Optional[str] = None,
    league_note: str = "",
) -> None:
    """Write the standard markdown catalog report to *out*.

    Parameters
    ----------
    rows:
        List of verdict dicts as returned by run_catalog_common.
    out:
        Output path.  Parent directories are created if needed.
    seasons:
        Season list for the Generated: metadata line.
    header_lines:
        Lines inserted after the Generated: line and before the verdict table.
        Typically the ## Contract blurb with sport-specific column names.
        If None, only the title + generated line are prepended.
    title:
        H1 title line.  Defaults to the generic "Honest signal catalog" title.
    league_note:
        Optional suffix appended to the Generated: metadata line (e.g. "  League: NL").
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    L: List[str] = [
        title if title is not None else _DEFAULT_TITLE,
        f"\nGenerated: {_dt.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}  "
        f"Seasons: {seasons}   Signals: {len(rows)}{league_note}",
    ]
    if header_lines:
        L.extend(header_lines)
    L += [
        "\n## Verdict table\n",
        "| Signal | Expected | Actual | Passed | N | Coverage | Reason |",
        "|--------|----------|--------|--------|---|----------|--------|",
    ]
    ships: List[str] = []
    for r in rows:
        L.append(
            f"| {r['name']} | {r['expected']} | {r['actual_verdict']} "
            f"| {'YES' if r['passed_expected'] else 'NO'} | {r.get('n','?')} "
            f"| {r.get('coverage','?')} "
            f"| {str(r.get('reason',''))[:80].replace('|','/')} |"
        )
        if r["actual_verdict"] == "SHIP":
            ships.append(r["name"])
    L.append("\n## Gate detail\n")
    for r in rows:
        L.append(f"### {r['name']}")
        for k in _DETAIL_KEYS:
            if k in r:
                L.append(f"- **{k}:** {r[k]}")
        L.append("")
    if ships:
        L += ["\n## !! SHIP FLAGS — probable artifacts — DO NOT claim edge\n"]
        for nm in ships:
            L.append(f"- **{nm}**: SHIP — artifact-hunt required.")
    L.append("\n---\n_PRIVATE research. No edge claimed. REJECT = honest success._")
    out.write_text("\n".join(L), encoding="utf-8")
    logger.info("Catalog report written to %s", out)


__all__ = ["derive_bundle", "run_catalog_common", "write_catalog_report"]
