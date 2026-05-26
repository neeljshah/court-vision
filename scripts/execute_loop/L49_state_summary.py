"""L49_state_summary.py — Execute-Loop State-of-the-Loop Summary Generator.

Purpose
-------
Aggregates observability data from multiple execute-loop layers into a single,
board-room-friendly STATE_OF_LOOP.md document.  Pulls from:

  - state.json          round-by-round narrative + layer metadata
  - L42 ReadinessChecker  per-layer KPI health scores
  - L47 RegressionDetector  test-count drops, missing modules
  - L41 integration harness  end-to-end coverage count

No external services are called; all inputs are local files or in-process
Python APIs.  Safe to run at any time without side-effects on trading.

Environment Variables
---------------------
    None.

Paper vs Live Mode
------------------
N/A — observability only; no money movement or mode gating required.
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
_DEFAULT_STATE = _HERE / "state.json"
_DEFAULT_OUT = _HERE / "STATE_OF_LOOP.md"

# ---------------------------------------------------------------------------
# Soft-imports (L42, L47, L41)
# ---------------------------------------------------------------------------
_PROJECT_ROOT = _HERE.parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

try:
    from scripts.execute_loop.L42_production_readiness import (
        ReadinessChecker as _ReadinessChecker,
    )
    _L42_AVAILABLE = True
except Exception:  # pragma: no cover
    _ReadinessChecker = None  # type: ignore[assignment,misc]
    _L42_AVAILABLE = False

try:
    from scripts.execute_loop.L47_regression_detector import (
        RegressionDetector as _RegressionDetector,
    )
    _L47_AVAILABLE = True
except Exception:  # pragma: no cover
    _RegressionDetector = None  # type: ignore[assignment,misc]
    _L47_AVAILABLE = False


# ---------------------------------------------------------------------------
# Public dataclass
# ---------------------------------------------------------------------------

@dataclass
class LoopSnapshot:
    """Immutable snapshot of loop health at a point in time."""

    generated_at: str
    rounds_completed: int
    layers_shipped: int
    layers_gated: int
    cumulative_tests: str           # raw string from state.json totals
    l42_audit: dict                 # {pass, fail, skip, n_a} or empty
    l47_regressions: list           # list[dict] — serialisable Regression dicts
    l41_coverage: int               # number of layers e2e-tested (from state.json)
    top_layers: list                # top-5 stability from L42 KPI
    bottom_layers: list             # bottom-5 stability from L42 KPI
    rounds: list                    # round_summaries from state.json
    new_layers_by_round: dict       # {round_int: [layer_name, ...]}
    event_producers: dict           # {"L7": ["bet.settled"], "L8": ["drift.detected"], ...}
    event_subscribers: dict         # {"L22": ["incident.opened", "drift.detected", ...]}
    total_event_types: int          # distinct event names across all producers


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_test_num(s: str) -> Optional[int]:
    """Return the numerator from a 'N/M' string, or None."""
    import re
    m = re.match(r"(\d+)\s*/\s*(\d+)", str(s).strip())
    return int(m.group(1)) if m else None


def _l41_coverage_from_state(state: dict) -> int:
    """Read e2e coverage from the latest L41 ship note in state.json."""
    import re
    l41 = state.get("layers", {}).get("L41", {})
    ships = l41.get("ships", [])
    # The latest ship note contains e.g. "24 of 47 layers"
    for ship in reversed(ships):
        for key in ("notes", "delta"):
            text = ship.get(key, "")
            m = re.search(r"(\d+)\s+of\s+\d+\s+layer", text)
            if m:
                return int(m.group(1))
    return 0


def _new_layers_by_round(state: dict) -> dict:
    """Return {round_int: [layer_label, ...]} for first-ship entries only."""
    result: dict[int, list] = {}
    layers = state.get("layers", {})
    for layer_key, info in layers.items():
        ships = info.get("ships", [])
        if not ships:
            continue
        first_ship = ships[0]
        rnd = first_ship.get("round")
        if rnd is None:
            continue
        result.setdefault(rnd, []).append(f"{layer_key} — {info.get('name', layer_key)}")
    # Sort layers within each round
    for rnd in result:
        result[rnd].sort()
    return dict(sorted(result.items()))


def _collect_event_metadata(layers_dir: Path) -> tuple[dict, dict]:
    """AST-scan each L*.py in layers_dir for publish/subscribe calls.

    Returns
    -------
    producers : dict[str, list[str]]
        e.g. {"L7": ["bet.settled"], "L14": ["fill.received", "order.filled"]}
    subscribers : dict[str, list[str]]
        e.g. {"L22": ["incident.opened", "drift.detected", ...]}

    Detection strategy
    ------------------
    Producers  — any ``Call`` node where the callee ends in ``.publish`` and
                 the first positional arg is a string literal.  Handles both
                 ``_L46.publish(...)`` and ``_get_l46().publish(...)`` patterns.
    Subscribers — ``bus.subscribe("name", ...)`` or
                  ``register_alert_subscribers`` docstring pattern: we scan
                  for ``Call`` nodes where the callee ends in ``.subscribe``
                  and the first positional arg is a string literal, plus
                  any string literals passed directly to ``subscribe`` at
                  module level.
    Layer label is derived from the filename stem (e.g. "L07_pnl_ledger" → "L7").
    """
    import re

    def _stem_to_layer(stem: str) -> str:
        """'L07_pnl_ledger' -> 'L7', 'L14_order_manager' -> 'L14'."""
        m = re.match(r"L0*(\d+)", stem, re.IGNORECASE)
        return f"L{m.group(1)}" if m else stem

    def _first_str_arg(node: ast.Call) -> Optional[str]:
        """Return the first positional arg if it is a string constant."""
        if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            return node.args[0].value
        return None

    def _callee_ends_with(node: ast.Call, attr: str) -> bool:
        """Return True if the call's function chain ends with `attr`."""
        func = node.func
        if isinstance(func, ast.Attribute):
            return func.attr == attr
        return False

    producers: dict = {}
    subscribers: dict = {}

    for py_file in sorted(layers_dir.glob("L*.py")):
        # Skip L46 itself (it defines publish/subscribe, not uses them as a producer)
        if py_file.stem.startswith("L46"):
            continue
        try:
            source = py_file.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue

        layer = _stem_to_layer(py_file.stem)

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            if _callee_ends_with(node, "publish"):
                event_name = _first_str_arg(node)
                if event_name:
                    producers.setdefault(layer, [])
                    if event_name not in producers[layer]:
                        producers[layer].append(event_name)

            if _callee_ends_with(node, "subscribe"):
                event_name = _first_str_arg(node)
                if event_name:
                    subscribers.setdefault(layer, [])
                    if event_name not in subscribers[layer]:
                        subscribers[layer].append(event_name)

    return producers, subscribers


def _fetch_l42(state_json_path: Path, layers_dir: Path) -> tuple[dict, list]:
    """Run L42 audit and KPI; return (summary_dict, sorted_kpis_list)."""
    if not _L42_AVAILABLE or _ReadinessChecker is None:
        return {}, []
    try:
        checker = _ReadinessChecker(
            layers_dir=layers_dir,
            state_json_path=state_json_path,
        )
        report = checker.run_all_checks()
        kpis = report.compute_layer_kpis(state_json_path)
        # Exclude the pseudo 'global' layer from ranking
        ranked = sorted(
            [v for k, v in kpis.items() if k != "global"],
            key=lambda x: x.stability_score,
            reverse=True,
        )
        return report.summary, ranked
    except Exception:
        return {}, []


def _fetch_l47(state_json_path: Path, layers_dir: Path) -> list:
    """Run L47 regression scan; return list of regression dicts."""
    if not _L47_AVAILABLE or _RegressionDetector is None:
        return []
    try:
        detector = _RegressionDetector(
            state_json_path=state_json_path,
            layers_dir=layers_dir,
        )
        report = detector.detect_all()
        from dataclasses import asdict
        return [asdict(r) for r in report.regressions]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Markdown helpers
# ---------------------------------------------------------------------------

def _md_table(headers: list, rows: list) -> str:
    """Render a simple markdown table."""
    sep = "| " + " | ".join("---" for _ in headers) + " |"
    header_row = "| " + " | ".join(headers) + " |"
    body = "\n".join("| " + " | ".join(str(c) for c in row) + " |" for row in rows)
    return "\n".join([header_row, sep, body])


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------

class LoopSummarizer:
    """Aggregates loop observability data into a LoopSnapshot + markdown doc."""

    def __init__(self, state_json_path: Path, layers_dir: Path) -> None:
        self.state_json_path = Path(state_json_path)
        self.layers_dir = Path(layers_dir)

    # ------------------------------------------------------------------
    def snapshot(self) -> LoopSnapshot:
        """Build and return a LoopSnapshot from all available sources."""
        state = json.loads(self.state_json_path.read_text(encoding="utf-8"))
        totals = state.get("totals", {})

        generated_at = datetime.now(timezone.utc).isoformat()
        rounds_completed = state.get("rounds_completed", 0)
        layers_shipped = totals.get("layers_shipped", 0)
        layers_gated = totals.get("layers_gated", 0)
        cumulative_tests = totals.get("cumulative_tests", "")

        # L42 audit summary (live run)
        l42_summary, l42_ranked = _fetch_l42(self.state_json_path, self.layers_dir)

        # Fallback: parse l42_audit string from state.json totals
        if not l42_summary:
            import re
            raw = totals.get("l42_audit", "")
            # e.g. "PASS 75 / FAIL 0 / SKIP 1 / N/A 55"
            def _extract(label: str) -> int:
                m = re.search(rf"{label}\s+(\d+)", raw, re.IGNORECASE)
                return int(m.group(1)) if m else 0
            l42_audit: dict = {
                "pass": _extract("PASS"),
                "fail": _extract("FAIL"),
                "skip": _extract("SKIP"),
                "n_a": _extract(r"N/A"),
            }
        else:
            l42_audit = {
                "pass": l42_summary.get("pass", 0),
                "fail": l42_summary.get("fail", 0),
                "skip": l42_summary.get("skip", 0),
                "n_a": l42_summary.get("n_a", 0),
            }

        # L47 regressions
        l47_regressions = _fetch_l47(self.state_json_path, self.layers_dir)

        # L41 e2e coverage
        l41_coverage = _l41_coverage_from_state(state)

        # KPI top/bottom-5
        def _kpi_dict(kpi) -> dict:
            return {
                "layer": kpi.layer,
                "name": kpi.name,
                "stability_score": kpi.stability_score,
                "checks_pass": kpi.checks_pass,
                "checks_fail": kpi.checks_fail,
                "ships": kpi.ships,
            }

        top_layers = [_kpi_dict(k) for k in l42_ranked[:5]] if l42_ranked else []
        bottom_layers = [_kpi_dict(k) for k in l42_ranked[-5:][::-1]] if l42_ranked else []

        rounds = state.get("round_summaries", [])
        new_layers = _new_layers_by_round(state)

        # Event-driven architecture metadata
        event_producers, event_subscribers = _collect_event_metadata(self.layers_dir)
        all_event_names: set = set()
        for events in event_producers.values():
            all_event_names.update(events)
        total_event_types = len(all_event_names)

        return LoopSnapshot(
            generated_at=generated_at,
            rounds_completed=rounds_completed,
            layers_shipped=layers_shipped,
            layers_gated=layers_gated,
            cumulative_tests=cumulative_tests,
            l42_audit=l42_audit,
            l47_regressions=l47_regressions,
            l41_coverage=l41_coverage,
            top_layers=top_layers,
            bottom_layers=bottom_layers,
            rounds=rounds,
            new_layers_by_round=new_layers,
            event_producers=event_producers,
            event_subscribers=event_subscribers,
            total_event_types=total_event_types,
        )

    # ------------------------------------------------------------------
    def to_markdown(self, snap: LoopSnapshot) -> str:
        """Render a LoopSnapshot to a board-room-friendly markdown string."""
        lines: list[str] = []

        # Header
        lines += [
            "# Execute Loop — State of the Loop",
            f"_Generated {snap.generated_at}_",
            "",
        ]

        # --- Headline ---
        l42 = snap.l42_audit
        fail_count = l42.get("fail", 0)
        l42_status = "clean (0 FAILs)" if fail_count == 0 else f"{fail_count} FAIL(s) need attention"
        reg_count = len(snap.l47_regressions)
        reg_status = f"{reg_count} regressions across {snap.rounds_completed} rounds"
        if reg_count == 0:
            reg_status = f"0 regressions across {snap.rounds_completed} rounds"
        total_layers = snap.layers_shipped + snap.layers_gated
        gated_note = f"({snap.layers_gated} gated)" if snap.layers_gated else ""

        lines += [
            "## Headline",
            f"- {snap.layers_shipped} layers shipped {gated_note}, {snap.cumulative_tests} tests passing",
            f"- L42 audit: {l42_status}",
            f"- L47 regression scan: {reg_status}",
            f"- L41 e2e coverage: {snap.l41_coverage} of {snap.layers_shipped} layers "
            f"({snap.l41_coverage * 100 // snap.layers_shipped if snap.layers_shipped else 0}%)",
            "",
        ]

        # --- Round-by-Round Narrative ---
        lines += [
            "## Round-by-Round Narrative",
        ]
        round_rows = []
        for r in snap.rounds:
            rnd = r.get("round", "?")
            ships = r.get("ships", [])
            ships_str = ", ".join(ships) if isinstance(ships, list) else str(ships)
            tests = r.get("tests", "")
            notes = r.get("notes", "")
            # Truncate notes for table readability
            if notes and len(notes) > 80:
                notes = notes[:77] + "..."
            round_rows.append([f"R{rnd}", ships_str, tests, notes])

        lines.append(
            _md_table(
                ["Round", "Ships", "Tests", "Notes"],
                round_rows,
            )
        )
        lines.append("")

        # --- Top Layers ---
        lines += ["## Top Layers (highest stability)", ""]
        if snap.top_layers:
            top_rows = [
                [
                    k["layer"],
                    k["name"],
                    f"{k['stability_score']:.1f}%",
                    str(k["checks_pass"]),
                    str(k["checks_fail"]),
                    str(k["ships"]),
                ]
                for k in snap.top_layers
            ]
            lines.append(
                _md_table(
                    ["Layer", "Name", "Stability", "Pass", "Fail", "Ships"],
                    top_rows,
                )
            )
        else:
            lines.append("_(L42 not available — run L42 audit for live scores)_")
        lines.append("")

        # --- Bottom Layers ---
        lines += ["## Bottom Layers (most needing work)", ""]
        if snap.bottom_layers:
            bot_rows = [
                [
                    k["layer"],
                    k["name"],
                    f"{k['stability_score']:.1f}%",
                    str(k["checks_pass"]),
                    str(k["checks_fail"]),
                    str(k["ships"]),
                ]
                for k in snap.bottom_layers
            ]
            lines.append(
                _md_table(
                    ["Layer", "Name", "Stability", "Pass", "Fail", "Ships"],
                    bot_rows,
                )
            )
        else:
            lines.append("_(L42 not available)_")
        lines.append("")

        # --- New Layers Built ---
        lines += ["## New Layers Built (by round)", ""]
        if snap.new_layers_by_round:
            for rnd, layer_list in snap.new_layers_by_round.items():
                lines.append(f"### R{rnd}")
                for item in layer_list:
                    lines.append(f"- {item}")
                lines.append("")
        else:
            lines.append("_(no new layers detected)_")
            lines.append("")

        # --- L42 Production Readiness ---
        lines += ["## L42 Production Readiness", ""]
        lines += [
            f"- PASS: {l42.get('pass', 0)}",
            f"- FAIL: {l42.get('fail', 0)}",
            f"- SKIP: {l42.get('skip', 0)}",
            f"- N/A:  {l42.get('n_a', 0)}",
            "",
            f"**Status: {l42_status}**",
            "",
            "Run `python -m scripts.execute_loop.L42_production_readiness audit` "
            "for the full per-layer breakdown.",
            "",
        ]

        # --- L41 Integration Coverage ---
        lines += ["## L41 Integration Coverage", ""]
        pct = snap.l41_coverage * 100 // snap.layers_shipped if snap.layers_shipped else 0
        lines += [
            f"- {snap.l41_coverage} of {snap.layers_shipped} layers exercised end-to-end ({pct}%)",
            "",
            "Covered layers (from latest L41 v4 ship, round 10):",
            "L01 ingest, L02 fpts, L03 cash-opt, L04 gpp-opt, L05 submit, L07 ledger,",
            "L08 drift, L09 kalshi, L10 polymarket, L13 cross-ev, L14 orders, L15 market-making,",
            "L17 hedge, L18 kelly, L19 clv, L20 injury, L21 lineup, L25 shadow,",
            "L26 hygiene, L33 sell-to-close, L34 variance, L36 edge-erosion, L37 postmortem, L40 dispatcher.",
            "",
            "Run `python -m scripts.execute_loop.L41_integration_harness` to re-verify.",
            "",
        ]

        # --- L47 Regression Status ---
        lines += ["## L47 Regression Status", ""]
        if not snap.l47_regressions:
            lines += [
                "**Clean — 0 regressions detected across all 10 rounds.**",
                "",
                "Run `python -m scripts.execute_loop.L47_regression_detector detect` to re-verify.",
            ]
        else:
            lines.append(f"**{len(snap.l47_regressions)} regression(s) detected:**")
            lines.append("")
            for reg in snap.l47_regressions:
                sev = reg.get("severity", "??")
                layer = reg.get("layer", "??")
                cat = reg.get("category", "??")
                detail = reg.get("detail", "")
                lines.append(f"- **[{sev}]** `{layer}` | {cat}: {detail}")
        lines.append("")

        # --- Event-Driven Architecture ---
        lines += ["## Event-Driven Architecture", ""]

        # Producers table
        lines += ["### Event Producers", ""]
        if snap.event_producers:
            prod_rows = [
                [layer, ", ".join(events)]
                for layer, events in sorted(snap.event_producers.items())
            ]
            lines.append(_md_table(["Layer", "Event Names"], prod_rows))
        else:
            lines.append("_(no event producers detected)_")
        lines.append("")

        # Subscribers table
        lines += ["### Event Subscribers", ""]
        if snap.event_subscribers:
            sub_rows = [
                [layer, ", ".join(events)]
                for layer, events in sorted(snap.event_subscribers.items())
            ]
            lines.append(_md_table(["Layer", "Subscribes To"], sub_rows))
        else:
            lines.append("_(no event subscribers detected)_")
        lines.append("")

        lines.append(
            f"Total event types in system: **{snap.total_event_types}**"
        )
        lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    def write(self, snap: LoopSnapshot, path: Optional[Path] = None) -> Path:
        """Write STATE_OF_LOOP.md atomically via tempfile + os.replace.

        Returns the path that was written.
        """
        out = Path(path) if path is not None else _DEFAULT_OUT
        content = self.to_markdown(snap)

        # Atomic write: write to a temp file in the same directory, then replace
        tmp_fd, tmp_path_str = tempfile.mkstemp(
            dir=out.parent, suffix=".tmp", prefix=".state_summary_"
        )
        try:
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                fh.write(content)
            os.replace(tmp_path_str, str(out))
        except Exception:
            # Clean up tmp on failure
            try:
                os.unlink(tmp_path_str)
            except OSError:
                pass
            raise

        return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    """Entry point: generate STATE_OF_LOOP.md (or JSON snapshot)."""
    parser = argparse.ArgumentParser(
        prog="L49_state_summary",
        description="Generate the execute-loop State-of-the-Loop summary.",
    )
    parser.add_argument(
        "--out",
        metavar="PATH",
        default=None,
        help=f"Output path (default: {_DEFAULT_OUT})",
    )
    parser.add_argument(
        "--json",
        metavar="PATH",
        default=None,
        help="Also write a JSON snapshot to this path.",
    )
    parser.add_argument(
        "--state",
        metavar="PATH",
        default=str(_DEFAULT_STATE),
        help="Path to state.json (default: scripts/execute_loop/state.json)",
    )
    args = parser.parse_args(argv)

    state_path = Path(args.state)
    summarizer = LoopSummarizer(
        state_json_path=state_path,
        layers_dir=state_path.parent,
    )
    snap = summarizer.snapshot()
    out = summarizer.write(snap, Path(args.out) if args.out else None)
    print(f"[L49] STATE_OF_LOOP.md written → {out}")

    if args.json:
        import dataclasses
        json_out = Path(args.json)
        payload = dataclasses.asdict(snap)
        json_out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"[L49] JSON snapshot written → {json_out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
