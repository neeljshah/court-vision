"""drift_report_render.py — Vault note rendering for drift_report.

Extracted from drift_report.py (N-OBS-003).  Contains:

    * _render_stat_table  — renders a markdown table from per-stat dicts
    * render_vault_note   — renders the full Markdown vault note from a report dict
    * write_vault_note    — atomically writes/updates the vault note (idempotent)

Python 3.9 compatible.  No torch / GPU imports.
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# Vault note anchor — used to detect and overwrite an existing note idempotently
_BANNER: str = "<!-- N-OBS-003 drift-report -->"

# Thresholds displayed in the vault note — keep in sync with drift_report.py
COVERAGE_TARGET: float = 0.80
COVERAGE_TOLERANCE: float = 0.03
ROLLING_WINDOW_DAYS: int = 30


# ---------------------------------------------------------------------------
# Vault note renderer
# ---------------------------------------------------------------------------


def _render_stat_table(per_stat: Dict[str, Any], columns: List[Tuple[str, str]]) -> str:
    """Render a markdown table from per-stat dicts.

    Args:
        per_stat: Mapping stat → metric dict.
        columns:  List of (key_in_dict, column_header) pairs.

    Returns:
        Markdown table string (no trailing newline).
    """
    if not per_stat:
        return "_No data available._"

    headers = ["stat"] + [col[1] for col in columns]
    header_row = "| " + " | ".join(headers) + " |"
    sep_row = "|" + "|".join(["---"] * len(headers)) + "|"

    rows = [header_row, sep_row]
    for stat in sorted(per_stat.keys()):
        vals = per_stat[stat]
        row_cells = [stat]
        for key, _ in columns:
            v = vals.get(key)
            if v is None:
                row_cells.append("—")
            elif isinstance(v, float):
                row_cells.append(f"{v:.4f}" if v == v else "nan")
            else:
                row_cells.append(str(v))
        rows.append("| " + " | ".join(row_cells) + " |")

    return "\n".join(rows)


def render_vault_note(report: Dict[str, Any]) -> str:
    """Render the drift report dict as a Markdown vault note.

    Args:
        report: Output of build_report().

    Returns:
        Markdown string suitable for writing to vault/Models/Drift Report.md.
    """
    ts = report.get("generated_at", "unknown")
    today_str = ts[:10] if len(ts) >= 10 else str(date.today())

    pm = report.get("point_metrics", {})
    cm = report.get("coverage_metrics", {})
    dm = report.get("drift_metrics", {})
    all_flags = report.get("all_flags", [])
    sources = report.get("data_sources", {})

    window = pm.get("window_days", ROLLING_WINDOW_DAYS)
    as_of = pm.get("as_of_date", "unknown")
    n_total = pm.get("n_total", 0)

    # Flag summary badge
    flag_count = len(all_flags)
    flag_badge = f"🔴 {flag_count} flag(s)" if flag_count else "🟢 No flags"

    lines = [
        _BANNER,
        f"# Drift Report — {today_str}",
        "",
        f"> Generated: {ts}  ",
        f"> Rolling window: {window} days (as of {as_of})  ",
        f"> Rows in window: {n_total}  ",
        f"> Status: {flag_badge}  ",
        "",
        "---",
        "",
        "## Data Sources",
        "",
        "| source | status |",
        "|--------|--------|",
    ]
    for src, status in sources.items():
        lines.append(f"| `{src}` | {status} |")

    lines += [
        "",
        "---",
        "",
        "## Point Calibration Metrics",
        f"_(rolling {window}d — bias, RMSE, PIT)_",
        "",
    ]

    pm_per_stat = pm.get("per_stat", {})
    if pm_per_stat:
        lines.append("### Bias and RMSE")
        lines.append("")
        lines.append(_render_stat_table(pm_per_stat, [
            ("n", "n"),
            ("bias", "bias"),
            ("rmse", "RMSE"),
            ("mse", "MSE"),
        ]))
        lines += ["", "### PIT Uniformity", ""]
        pit_per_stat: Dict[str, Any] = {}
        for stat, v in pm_per_stat.items():
            pit = v.get("pit", {})
            pit_per_stat[stat] = {
                "n": pit.get("n", 0),
                "mean": pit.get("mean"),
                "std": pit.get("std"),
                "skew": pit.get("skew"),
                "p_value": pit.get("p_value"),
                "flag": pit.get("flag", "—"),
            }
        lines.append(_render_stat_table(pit_per_stat, [
            ("n", "n"),
            ("mean", "mean_resid"),
            ("std", "std_resid"),
            ("skew", "skew"),
            ("p_value", "p_value"),
            ("flag", "flag"),
        ]))
    else:
        lines.append("_No point calibration data available._")

    lines += [
        "",
        "---",
        "",
        "## Interval Coverage",
        f"_(nominal target: {COVERAGE_TARGET:.0%}, tolerance: ±{COVERAGE_TOLERANCE:.0%})_",
        "",
    ]
    cm_per_stat = cm.get("per_stat", {})
    if cm_per_stat:
        lines.append(_render_stat_table(cm_per_stat, [
            ("n", "n"),
            ("coverage", "coverage"),
            ("nominal", "nominal"),
            ("gap", "gap"),
            ("status", "status"),
        ]))
    else:
        lines.append("_No coverage data available._")

    lines += [
        "",
        "---",
        "",
        "## Feature Drift",
        "",
        f"Models in log: {dm.get('model_count', 0)}  ",
        f"Models with drift flags: {dm.get('n_flagged', 0)}  ",
        "",
    ]
    flagged = dm.get("flagged_models", [])
    if flagged:
        lines.append("**Flagged models:**")
        lines.append("")
        for m in flagged:
            lines.append(f"- `{m}`")
    else:
        lines.append("_No feature drift flags._")

    if all_flags:
        lines += [
            "",
            "---",
            "",
            "## All Flags",
            "",
        ]
        for f in all_flags:
            lines.append(f"- {f}")
    else:
        lines += ["", "---", "", "_No flags raised in this report._"]

    lines += [
        "",
        "---",
        "",
        "_Descriptive report — no auto-action, no edge claims. "
        "Generated by scripts/platformkit/obs/drift_report.py._",
    ]

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Vault write — idempotent (overwrites existing note by banner match)
# ---------------------------------------------------------------------------


def write_vault_note(report: Dict[str, Any], out_path: Optional[Path] = None,
                     _vault_note_default: Optional[Path] = None) -> Path:
    """Atomically write/update the vault note.

    Idempotent: reruns overwrite the same file.  The banner comment at the
    top of the file (_BANNER) is the identity anchor.

    Args:
        report:              Output of build_report().
        out_path:            Override for the output path (default: _vault_note_default).
        _vault_note_default: Fallback path when out_path is None (injected by drift_report.py).

    Returns:
        Path where the note was written.
    """
    target = Path(out_path) if out_path is not None else _vault_note_default
    if target is None:
        raise ValueError("No output path provided and no default configured")
    target.parent.mkdir(parents=True, exist_ok=True)

    content = render_vault_note(report)

    # Atomic write via a temp file then rename (idempotent on rerun)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(target)  # atomic on same filesystem

    log.info("Drift report written to %s", target)
    return target
