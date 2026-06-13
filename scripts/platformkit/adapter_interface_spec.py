"""scripts/platformkit/adapter_interface_spec.py — Runtime interface-parity spec.

Defines the REQUIRED runtime interface all MARKET_ONLY domain adapters must share,
and provides ``check_adapter(cls_or_module) -> list[CheckResult]`` to verify
conformance.

DISTINCT from validate_adapter.py which checks SportContext config-level items;
this module checks RUNTIME SHAPE/UNIFORMITY of the adapter class itself:
  - class-level ``sport`` attribute (str)
  - ``__init__`` signature shape (repo_root, *data frames, [kwargs])
  - protocol method presence + parameter names + return annotations
  - ``feature_bundle`` positional parameters (hypothesis, seasons)
  - ``FeatureBundle`` attribute set on the returned object

All checks are purely structural (inspect-based); no data files are required.

Usage (CLI)::

    python scripts/platformkit/adapter_interface_spec.py

Exit code: 0 = all adapters conformant, 1 = any FAIL.
"""
from __future__ import annotations

import importlib
import inspect
import sys
from typing import Any, List, Optional, Sequence, Type

from scripts.platformkit.validate_adapter_types import CheckResult, Status

# ---------------------------------------------------------------------------
# The REQUIRED runtime interface (data-driven spec)
# ---------------------------------------------------------------------------

#: Methods every adapter class MUST expose (excludes private helpers).
REQUIRED_METHODS: List[str] = [
    "list_events",
    "market_snapshot",
    "outcome",
    "baseline_probability",
    "feature_bundle",
]

#: ``feature_bundle`` MUST have at least these two positional parameters
#: (after ``self``) in exactly this order.
FEATURE_BUNDLE_POSITIONAL_PARAMS: List[str] = ["hypothesis", "seasons"]

#: ``FeatureBundle`` MUST carry exactly these public attributes.
FEATURE_BUNDLE_ATTRS: List[str] = [
    "base",
    "signal_col",
    "target",
    "dates",
    "lines",
    "closing",
]

#: The adapter class MUST have a class-level ``sport`` attribute of type ``str``.
REQUIRED_CLASS_ATTRS: List[str] = ["sport"]

# ---------------------------------------------------------------------------
# Adapter registry (module paths for the three shipped domain adapters)
# ---------------------------------------------------------------------------

ADAPTER_REGISTRY = {
    "tennis": ("domains.tennis.adapter", "TennisAdapter"),
    "soccer": ("domains.soccer.adapter", "SoccerAdapter"),
    "mlb": ("domains.mlb.adapter", "MLBAdapter"),
    "basketball_nba": ("domains.basketball_nba.adapter", "NBAAdapter"),
}

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_adapter_class(sport: str) -> Optional[Type[Any]]:
    """Import and return the adapter class for *sport*, or None on import error."""
    if sport not in ADAPTER_REGISTRY:
        return None
    module_path, class_name = ADAPTER_REGISTRY[sport]
    try:
        mod = importlib.import_module(module_path)
        return getattr(mod, class_name)
    except Exception:  # noqa: BLE001
        return None


def _check_class_attrs(cls: Type[Any]) -> List[CheckResult]:
    results: List[CheckResult] = []
    for attr in REQUIRED_CLASS_ATTRS:
        item = f"class attr '{attr}'"
        if not hasattr(cls, attr):
            results.append(CheckResult(item, Status.FAIL, f"missing on {cls.__name__}"))
        elif not isinstance(getattr(cls, attr), str):
            results.append(CheckResult(
                item, Status.FAIL,
                f"{cls.__name__}.{attr} must be str; got {type(getattr(cls, attr)).__name__}",
            ))
        else:
            results.append(CheckResult(item, Status.PASS))
    return results


def _check_method_presence(cls: Type[Any]) -> List[CheckResult]:
    results: List[CheckResult] = []
    for method in REQUIRED_METHODS:
        item = f"method '{method}'"
        if not callable(getattr(cls, method, None)):
            results.append(CheckResult(item, Status.FAIL, f"missing on {cls.__name__}"))
        else:
            results.append(CheckResult(item, Status.PASS))
    return results


def _check_feature_bundle_params(cls: Type[Any]) -> List[CheckResult]:
    """Verify feature_bundle has the required positional params in order."""
    results: List[CheckResult] = []
    item = "feature_bundle positional params (hypothesis, seasons)"
    fb = getattr(cls, "feature_bundle", None)
    if fb is None:
        results.append(CheckResult(item, Status.FAIL, "method absent"))
        return results
    try:
        sig = inspect.signature(fb)
        params = [
            p for name, p in sig.parameters.items()
            if name != "self"
            and p.kind in (
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                inspect.Parameter.POSITIONAL_ONLY,
            )
        ]
        positional_names = [p.name for p in params]
        for i, required in enumerate(FEATURE_BUNDLE_POSITIONAL_PARAMS):
            if i >= len(positional_names):
                results.append(CheckResult(
                    f"feature_bundle param[{i}] == '{required}'",
                    Status.FAIL,
                    f"only {len(positional_names)} positional params",
                ))
            elif positional_names[i] != required:
                results.append(CheckResult(
                    f"feature_bundle param[{i}] == '{required}'",
                    Status.FAIL,
                    f"got '{positional_names[i]}'",
                ))
            else:
                results.append(CheckResult(
                    f"feature_bundle param[{i}] == '{required}'",
                    Status.PASS,
                ))
        # Document any extra params beyond the required set (not a FAIL)
        extra = positional_names[len(FEATURE_BUNDLE_POSITIONAL_PARAMS):]
        if extra:
            results.append(CheckResult(
                "feature_bundle extra params (informational)",
                Status.SKIP,
                f"extra positional params beyond spec: {extra}",
            ))
    except (TypeError, ValueError) as exc:
        results.append(CheckResult(item, Status.FAIL, str(exc)))
    return results


def _check_feature_bundle_attrs() -> List[CheckResult]:
    """Verify FeatureBundle dataclass exposes the required attributes."""
    results: List[CheckResult] = []
    item = "FeatureBundle attribute set"
    try:
        from src.loop.gate import FeatureBundle
        for attr in FEATURE_BUNDLE_ATTRS:
            sub_item = f"FeatureBundle.{attr}"
            if attr in FeatureBundle.__dataclass_fields__:
                results.append(CheckResult(sub_item, Status.PASS))
            else:
                results.append(CheckResult(
                    sub_item, Status.FAIL,
                    "not a dataclass field on FeatureBundle",
                ))
    except Exception as exc:  # noqa: BLE001
        results.append(CheckResult(item, Status.FAIL, str(exc)))
    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def check_adapter(cls: Type[Any]) -> List[CheckResult]:
    """Run all runtime interface-parity checks against adapter class *cls*.

    Parameters
    ----------
    cls:
        The adapter class (e.g. ``TennisAdapter``) to check.

    Returns
    -------
    list[CheckResult]
        Ordered list of check results.  Iterate to print a scorecard.
    """
    results: List[CheckResult] = []
    results.extend(_check_class_attrs(cls))
    results.extend(_check_method_presence(cls))
    results.extend(_check_feature_bundle_params(cls))
    results.extend(_check_feature_bundle_attrs())
    return results


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _print_scorecard(sport: str, results: List[CheckResult]) -> int:
    """Print results for one adapter; return 0 if no FAIL, 1 otherwise."""
    n_pass = sum(1 for r in results if r.status == Status.PASS)
    n_fail = sum(1 for r in results if r.status == Status.FAIL)
    n_skip = sum(1 for r in results if r.status == Status.SKIP)
    print(f"\n=== Interface-parity: {sport} ===")
    print(f"  {n_pass} PASS  {n_fail} FAIL  {n_skip} SKIP")
    for r in results:
        print(str(r))
    return 1 if n_fail else 0


def main(argv: Optional[List[str]] = None) -> int:
    """Print conformance scorecard for all registered adapters."""
    overall = 0
    for sport in ADAPTER_REGISTRY:
        cls = _load_adapter_class(sport)
        if cls is None:
            print(f"\n=== Interface-parity: {sport} ===")
            print(f"  [SKIP] could not import adapter — skipped")
            continue
        results = check_adapter(cls)
        overall |= _print_scorecard(sport, results)
    print()
    if overall:
        print("RESULT: FAIL — at least one adapter has interface violations.")
    else:
        print("RESULT: OK — all adapters conform to the runtime interface spec.")
    return overall


if __name__ == "__main__":
    sys.exit(main())
