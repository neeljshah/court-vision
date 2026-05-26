"""L47_regression_detector.py — State Regression / Drift Detector for the execute-loop.

Purpose
-------
Reads ``scripts/execute_loop/state.json`` and the layers directory, then flags
regressions that indicate the loop has broken or silently degraded between
rounds.  Pure observability — never modifies any file.

Environment Variables
---------------------
    None.

Paper vs Live Mode
------------------
N/A — observability only; no money movement, no mode gating required.

What It Detects
---------------
1. **test_count_drop**
   For each layer with multiple ship entries, compare consecutive ships'
   ``tests`` strings (e.g. "12/12").  If the numerator *or* denominator falls,
   flag P0.  Increases are healthy and ignored.

2. **kpi_drop**
   If a layer's latest ship has a ``stability_score`` key and it is lower than
   an earlier ship's score, flag P1.  Also flags if any ship carries a
   ``kpi_score`` that decreases across consecutive ships.

3. **missing_module**
   For every layer whose status is "shipped", check that a corresponding
   ``L{N}_*.py`` file exists in the layers directory.  Gated layers (status
   "gated") are skipped.  Missing file → P0.

4. **missing_tests** (orphan tests inverse)
   For every shipped layer whose latest ship records tests > 0, check that at
   least one ``test_L{N}_*.py`` exists in ``tests/``.  Missing test file → P1.

5. **ship_without_round**
   Any ship entry that lacks a ``round`` field is a metadata gap → P2.

Public API
----------
    Regression          frozen dataclass
    RegressionReport    dataclass with to_markdown() / to_dict()
    RegressionDetector  main engine
    main(argv)          CLI entry point
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
_DEFAULT_STATE = _HERE / "state.json"
_DEFAULT_LAYERS_DIR = _HERE


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Regression:
    """A single detected regression or metadata issue."""

    layer: str
    category: str   # "test_count_drop" | "kpi_drop" | "missing_module" |
    #                  "missing_tests" | "ship_without_round"
    severity: str   # "P0" | "P1" | "P2"
    detail: str
    from_round: Optional[int]
    to_round: Optional[int]


@dataclass
class RegressionReport:
    """Aggregated output of a full regression scan."""

    regressions: list[Regression] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    generated_at: str = ""

    # ------------------------------------------------------------------
    def to_markdown(self) -> str:
        lines: list[str] = [
            "# L47 Regression Report",
            f"Generated: {self.generated_at}",
            "",
        ]
        # Summary table
        lines += [
            "## Summary",
            f"- Total regressions: {len(self.regressions)}",
        ]
        by_sev = self.summary.get("by_severity", {})
        for sev in ("P0", "P1", "P2"):
            count = by_sev.get(sev, 0)
            lines.append(f"  - {sev}: {count}")
        by_cat = self.summary.get("by_category", {})
        lines += ["", "### By category"]
        for cat, cnt in sorted(by_cat.items()):
            lines.append(f"  - {cat}: {cnt}")
        lines.append("")

        if not self.regressions:
            lines.append("**No regressions detected.**")
            return "\n".join(lines)

        lines.append("## Regressions")
        for r in self.regressions:
            rng = ""
            if r.from_round is not None or r.to_round is not None:
                rng = f" (round {r.from_round} → {r.to_round})"
            lines.append(
                f"- **[{r.severity}]** `{r.layer}` | {r.category}{rng}: {r.detail}"
            )
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return {
            "regressions": [asdict(r) for r in self.regressions],
            "summary": self.summary,
            "generated_at": self.generated_at,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_test_string(tests_str: str) -> tuple[Optional[int], Optional[int]]:
    """Parse "N/M" → (N, M).  Returns (None, None) on failure."""
    m = re.match(r"(\d+)\s*/\s*(\d+)", str(tests_str).strip())
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


def _layer_number(layer_key: str) -> Optional[int]:
    """Extract integer from 'L1', 'L29', etc.  Returns None on parse failure."""
    m = re.match(r"[Ll](\d+)", layer_key.strip())
    return int(m.group(1)) if m else None


def _layer_module_glob(layers_dir: Path, layer_num: int) -> list[Path]:
    """Return all L{N}_*.py files in layers_dir (not starting with 'test_').

    Tries both zero-padded (L01_*.py) and unpadded (L1_*.py) patterns so the
    detector works regardless of how files are named on disk.
    """
    candidates: set[Path] = set()
    for pattern in (f"L{layer_num}_*.py", f"L{layer_num:02d}_*.py"):
        for p in layers_dir.glob(pattern):
            if not p.name.startswith("test_") and p.parent == layers_dir:
                candidates.add(p)
    return list(candidates)


def _layer_test_glob(layers_dir: Path, layer_num: int) -> list[Path]:
    """Return all test_L{N}_*.py files under layers_dir/tests/.

    Tries both zero-padded (test_L01_*.py) and unpadded (test_L1_*.py) patterns.
    """
    tests_dir = layers_dir / "tests"
    if not tests_dir.is_dir():
        return []
    candidates: set[Path] = set()
    for pattern in (f"test_L{layer_num}_*.py", f"test_L{layer_num:02d}_*.py"):
        candidates.update(tests_dir.glob(pattern))
    return list(candidates)


# ---------------------------------------------------------------------------
# Detection methods (static-style — accept state_data as arg for testability)
# ---------------------------------------------------------------------------

def detect_test_count_drops(state_data: dict) -> list[Regression]:
    """Flag layers where a later ship has fewer passing or total tests than a prior ship."""
    regressions: list[Regression] = []
    layers = state_data.get("layers", {})

    for layer_key, layer_info in layers.items():
        if layer_info.get("status") != "shipped":
            continue
        ships = layer_info.get("ships", [])
        if len(ships) < 2:
            continue

        prev_ship = ships[0]
        for ship in ships[1:]:
            prev_num, prev_den = _parse_test_string(prev_ship.get("tests", ""))
            cur_num, cur_den = _parse_test_string(ship.get("tests", ""))

            prev_round = prev_ship.get("round")
            cur_round = ship.get("round")

            if None in (prev_num, prev_den, cur_num, cur_den):
                prev_ship = ship
                continue

            if cur_num < prev_num:
                regressions.append(Regression(
                    layer=layer_key,
                    category="test_count_drop",
                    severity="P0",
                    detail=(
                        f"Passing tests dropped from {prev_num}/{prev_den} "
                        f"to {cur_num}/{cur_den}"
                    ),
                    from_round=prev_round,
                    to_round=cur_round,
                ))
            elif cur_den < prev_den:
                regressions.append(Regression(
                    layer=layer_key,
                    category="test_count_drop",
                    severity="P0",
                    detail=(
                        f"Total test count dropped from {prev_num}/{prev_den} "
                        f"to {cur_num}/{cur_den}"
                    ),
                    from_round=prev_round,
                    to_round=cur_round,
                ))
            prev_ship = ship

    return regressions


def detect_kpi_drops(state_data: dict, current_kpis: Optional[dict] = None) -> list[Regression]:
    """Flag layers where stability_score or kpi_score declined across ships.

    Also cross-checks against an optional ``current_kpis`` dict
    (keyed by layer, value is current stability_score float).
    """
    regressions: list[Regression] = []
    layers = state_data.get("layers", {})
    current_kpis = current_kpis or {}

    for layer_key, layer_info in layers.items():
        if layer_info.get("status") != "shipped":
            continue
        ships = layer_info.get("ships", [])

        # Consecutive-ship kpi_score drops
        prev_ship = None
        for ship in ships:
            if prev_ship is not None:
                for score_key in ("kpi_score", "stability_score"):
                    prev_score = prev_ship.get(score_key)
                    cur_score = ship.get(score_key)
                    if prev_score is None or cur_score is None:
                        continue
                    if cur_score < prev_score:
                        regressions.append(Regression(
                            layer=layer_key,
                            category="kpi_drop",
                            severity="P1",
                            detail=(
                                f"{score_key} dropped from {prev_score} "
                                f"to {cur_score}"
                            ),
                            from_round=prev_ship.get("round"),
                            to_round=ship.get("round"),
                        ))
            prev_ship = ship

        # Cross-check against externally provided current KPIs
        if layer_key in current_kpis:
            # Try to find the highest historical stability_score in state
            historical_scores = [
                s.get("stability_score")
                for s in ships
                if s.get("stability_score") is not None
            ]
            if historical_scores:
                max_hist = max(historical_scores)
                cur = current_kpis[layer_key]
                if cur < max_hist:
                    regressions.append(Regression(
                        layer=layer_key,
                        category="kpi_drop",
                        severity="P1",
                        detail=(
                            f"Current stability_score {cur} is below "
                            f"historical peak {max_hist}"
                        ),
                        from_round=None,
                        to_round=None,
                    ))

    return regressions


def detect_missing_modules(state_data: dict, layers_dir: Path) -> list[Regression]:
    """Flag shipped layers that have no corresponding L{N}_*.py file."""
    regressions: list[Regression] = []
    layers = state_data.get("layers", {})

    for layer_key, layer_info in layers.items():
        # Only check shipped layers; skip gated/planned/etc.
        if layer_info.get("status") != "shipped":
            continue

        num = _layer_number(layer_key)
        if num is None:
            continue

        found = _layer_module_glob(layers_dir, num)
        if not found:
            regressions.append(Regression(
                layer=layer_key,
                category="missing_module",
                severity="P0",
                detail=f"No L{num}_*.py found in {layers_dir}",
                from_round=None,
                to_round=None,
            ))

    return regressions


def detect_orphan_tests(state_data: dict, layers_dir: Path) -> list[Regression]:
    """Flag shipped layers with tests > 0 that have no test_L{N}_*.py file."""
    regressions: list[Regression] = []
    layers = state_data.get("layers", {})

    for layer_key, layer_info in layers.items():
        if layer_info.get("status") != "shipped":
            continue

        ships = layer_info.get("ships", [])
        if not ships:
            continue

        # Use the latest ship's test count
        latest_ship = ships[-1]
        num_passing, _ = _parse_test_string(latest_ship.get("tests", ""))
        if num_passing is None or num_passing == 0:
            continue

        layer_num = _layer_number(layer_key)
        if layer_num is None:
            continue

        found = _layer_test_glob(layers_dir, layer_num)
        if not found:
            regressions.append(Regression(
                layer=layer_key,
                category="missing_tests",
                severity="P1",
                detail=(
                    f"Latest ship records {num_passing} passing tests "
                    f"but no test_L{layer_num}_*.py found in tests/"
                ),
                from_round=None,
                to_round=None,
            ))

    return regressions


def detect_ship_without_round(state_data: dict) -> list[Regression]:
    """Flag ship entries that are missing a 'round' field."""
    regressions: list[Regression] = []
    layers = state_data.get("layers", {})

    for layer_key, layer_info in layers.items():
        ships = layer_info.get("ships", [])
        for idx, ship in enumerate(ships):
            if "round" not in ship:
                regressions.append(Regression(
                    layer=layer_key,
                    category="ship_without_round",
                    severity="P2",
                    detail=f"Ship entry #{idx} has no 'round' field",
                    from_round=None,
                    to_round=None,
                ))

    return regressions


# ---------------------------------------------------------------------------
# Main detector class
# ---------------------------------------------------------------------------

class RegressionDetector:
    """Orchestrates all regression checks against state.json + layers dir."""

    def __init__(
        self,
        state_json_path: Path = _DEFAULT_STATE,
        layers_dir: Path = _DEFAULT_LAYERS_DIR,
    ) -> None:
        self.state_json_path = Path(state_json_path)
        self.layers_dir = Path(layers_dir)

    def _load_state(self) -> dict:
        with self.state_json_path.open(encoding="utf-8") as fh:
            return json.load(fh)

    def detect_all(self) -> RegressionReport:
        state_data = self._load_state()

        all_regressions: list[Regression] = []
        all_regressions += detect_test_count_drops(state_data)
        all_regressions += detect_kpi_drops(state_data)
        all_regressions += detect_missing_modules(state_data, self.layers_dir)
        all_regressions += detect_orphan_tests(state_data, self.layers_dir)
        all_regressions += detect_ship_without_round(state_data)

        # Build summary
        by_severity: dict[str, int] = {"P0": 0, "P1": 0, "P2": 0}
        by_category: dict[str, int] = {}
        for reg in all_regressions:
            by_severity[reg.severity] = by_severity.get(reg.severity, 0) + 1
            by_category[reg.category] = by_category.get(reg.category, 0) + 1

        summary = {"by_severity": by_severity, "by_category": by_category}

        return RegressionReport(
            regressions=all_regressions,
            summary=summary,
            generated_at=datetime.now(timezone.utc).isoformat(),
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="L47_regression_detector",
        description="Detect regressions in execute-loop state.json.",
    )
    sub = parser.add_subparsers(dest="command")

    detect_parser = sub.add_parser("detect", help="Run all regression checks.")
    detect_parser.add_argument(
        "--json",
        metavar="OUT",
        default=None,
        help="Write JSON report to this file (default: markdown to stdout).",
    )
    detect_parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit 1 if any P0 regression is found.",
    )
    detect_parser.add_argument(
        "--state",
        metavar="PATH",
        default=str(_DEFAULT_STATE),
        help="Path to state.json (default: scripts/execute_loop/state.json).",
    )
    detect_parser.add_argument(
        "--layers-dir",
        metavar="PATH",
        default=str(_DEFAULT_LAYERS_DIR),
        help="Directory containing L*.py modules (default: scripts/execute_loop/).",
    )

    args = parser.parse_args(argv)

    if args.command != "detect":
        parser.print_help()
        return 0

    detector = RegressionDetector(
        state_json_path=Path(args.state),
        layers_dir=Path(args.layers_dir),
    )
    report = detector.detect_all()

    if args.json:
        out = Path(args.json)
        out.write_text(
            json.dumps(report.to_dict(), indent=2), encoding="utf-8"
        )
        print(f"[L47] Report written to {out}")
    else:
        print(report.to_markdown())

    if args.strict:
        p0_count = report.summary.get("by_severity", {}).get("P0", 0)
        if p0_count > 0:
            print(
                f"\n[L47] STRICT mode: {p0_count} P0 regression(s) found → exit 1",
                file=sys.stderr,
            )
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
