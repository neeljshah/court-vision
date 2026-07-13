"""scripts.platformkit.reports.weekly_scoreboard -- weekly one-page scoreboard.

Renders docs/research/scoreboard/YYYY-Www.md from ON-DISK artifacts only:
DATA_COVERAGE_MAP.md, interaction_factory_ledger.jsonl, false_discovery_ledger.jsonl,
scripts.platformkit.models.registry, and PROVEN_EDGE_ROADMAP.md milestones. Each
section degrades to an honest "source missing" line rather than crashing.

Calibration / coverage / count language only -- no $/ROI/bankroll/pnl/edge claims,
see .claude/rules/no-edge-claims.md. Labels (verdicts, model_ids) are printed verbatim.

CLI: python -m scripts.platformkit.reports.weekly_scoreboard [--week YYYY-Www]
"""

import argparse
import json
import re
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3]

COVERAGE_MAP = _ROOT / "docs/research/DATA_COVERAGE_MAP.md"
INTERACTION_LEDGER = _ROOT / "data/cache/intel_claims/interaction_factory_ledger.jsonl"
FALSE_DISCOVERY_LEDGER = _ROOT / "data/cache/intel_claims/false_discovery_ledger.jsonl"
ROADMAP = _ROOT / ".planning/PROVEN_EDGE_ROADMAP.md"
OUTPUT_DIR = _ROOT / "docs/research/scoreboard"

SURVIVOR_VERDICTS = {"SURVIVES_PREREG_PROVISIONAL", "REPLICATED", "CONFIRMED_LOCAL", "CONFIRMED"}

# ponytail: no milestone writer emits these numbers yet -- hardcoded per rail
# instruction, tagged [manual]. Swap to a live artifact read once one lands.
SOURCES = {
    "m_a_accrual": "49/55 frozen until MLB resumes ~Fri 07-17 (all-star break) [manual]",
    "rung8_accrual": "~108/125, same freeze [manual]",
}


def week_bounds(year: int, week: int) -> tuple:
    """Return (monday, sunday) dates for an ISO (year, week)."""
    return date.fromisocalendar(year, week, 1), date.fromisocalendar(year, week, 7)


def parse_week_arg(week_str: str) -> tuple:
    m = re.match(r"^(\d{4})-W(\d{2})$", week_str)
    if not m:
        raise ValueError(f"bad --week format (want YYYY-Www): {week_str}")
    return int(m.group(1)), int(m.group(2))


def current_week(now: datetime = None) -> tuple:
    now = now or datetime.now(timezone.utc)
    iso = now.isocalendar()
    return iso.year, iso.week, f"{iso.year}-W{iso.week:02d}"


def _read_jsonl(path: Path):
    """Return list of dicts, or None if the file is missing."""
    if not path.is_file():
        return None
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _in_week(d: date, start: date, end: date) -> bool:
    return start <= d <= end


def render_coverage() -> list:
    lines = ["## 1. Coverage", ""]
    if not COVERAGE_MAP.is_file():
        return lines + ["source missing: docs/research/DATA_COVERAGE_MAP.md", ""]
    text = COVERAGE_MAP.read_text(encoding="utf-8")
    m = re.search(r"Coverage = ([\d.]+)%\*\* \((\d+) of (\d+)", text)
    if m:
        lines.append(f"**{m.group(1)}%** ({m.group(2)} of {m.group(3)} non-scratch families).")
    else:
        lines.append("coverage header not found in source")
    lines.append("")
    lines.append("Top-3 gaps:")
    for num, family, status in re.findall(r"^\| ([123]) \| ([^|]+) \| (\w+) \|", text, re.MULTILINE):
        lines.append(f"- #{num} {family.strip()} ({status})")
    lines.append("")
    return lines


def render_gate_throughput(start: date, end: date) -> tuple:
    """Returns (lines, week_rows). week_rows is None if the ledger is missing."""
    lines = ["## 2. Gate throughput", ""]
    rows = _read_jsonl(INTERACTION_LEDGER)
    if rows is None:
        return lines + ["source missing: data/cache/intel_claims/interaction_factory_ledger.jsonl", ""], None
    week_rows = [
        r for r in rows
        if r.get("computed_at") and _in_week(date.fromisoformat(r["computed_at"][:10]), start, end)
    ]
    lines.append(f"Candidates tested: {len(week_rows)}")
    lines.append("")
    lines.append("Verdict histogram:")
    for verdict, n in sorted(Counter(r.get("verdict", "UNKNOWN") for r in week_rows).items()):
        lines.append(f"- {verdict}: {n}")
    lines.append("")
    survivors = [r for r in week_rows if r.get("verdict") in SURVIVOR_VERDICTS]
    lines.append(f"Survivors ({len(survivors)}):")
    for r in survivors:
        lines.append(f"- {r.get('candidate_id')} [{r.get('verdict')}]")
    lines.append("")
    return lines, week_rows


def render_replications(week_rows) -> list:
    lines = ["## 3. Replications", ""]
    if week_rows is None:
        return lines + ["source missing: data/cache/intel_claims/interaction_factory_ledger.jsonl", ""]
    repl_rows = [r for r in week_rows if r.get("replication_of")]
    lines.append(f"Rows with replication_of this week: {len(repl_rows)}")
    for verdict, n in sorted(Counter(r.get("verdict", "UNKNOWN") for r in repl_rows).items()):
        lines.append(f"- {verdict}: {n}")
    lines.append("")
    return lines


def render_false_discovery(start: date, end: date) -> list:
    lines = ["## 4. False-discovery", ""]
    rows = _read_jsonl(FALSE_DISCOVERY_LEDGER)
    if rows is None:
        return lines + ["source missing: data/cache/intel_claims/false_discovery_ledger.jsonl", ""]
    week_rows = [
        r for r in rows
        if r.get("date") and _in_week(date.fromisoformat(r["date"]), start, end)
    ]
    if not week_rows:
        lines.append("0 rows this week.")
        lines.append("")
        return lines
    for r in week_rows:
        lines.append(
            f"- {r['date']}: n_tested={r['n_tested']}, "
            f"expected_false_survivors={r['expected_false_survivors']:.3f}, "
            f"observed_survivors={r['observed_survivors']}, "
            f"within_noise_floor={r['within_noise_floor']}"
        )
    lines.append("")
    return lines


def render_model_fleet() -> list:
    lines = ["## 5. Model fleet", ""]
    try:
        from scripts.platformkit.models import registry
    except ImportError:
        return lines + ["source missing: scripts.platformkit.models.registry", ""]
    for sport, market in registry.all_markets():
        entry = registry.get_spec(sport, market)
        champ = entry["champion"]
        lines.append(f"- {sport}/{market}: champion={champ['model_id']} ({champ['oos_status']})")
        for c in entry["challengers"]:
            lines.append(f"  - challenger={c['model_id']} ({c['oos_status']})")
            if c["oos_status"] == "BENCHMARKED" and str(c["benchmark"]).endswith(".json"):
                bpath = _ROOT / c["benchmark"]
                if bpath.is_file():
                    try:
                        verdict = json.loads(bpath.read_text(encoding="utf-8")).get("verdict")
                    except (json.JSONDecodeError, OSError):
                        verdict = None
                    if verdict:
                        lines.append(f"    verdict={verdict} (source: {c['benchmark']})")
    lines.append("")
    return lines


def _milestone_line(text: str, tag: str) -> str:
    """Header + any wrapped continuation lines, stopping at a RULE: detail
    block, the next M-tag, or a blank line -- collapsed to one line."""
    m = re.search(
        rf"^{re.escape(tag)} .*?(?=\n\n|\n  RULE:|\nM-[A-D] \(|\Z)",
        text, re.MULTILINE | re.DOTALL,
    )
    return re.sub(r"\s+", " ", m.group(0)).strip() if m else None


def render_proof_milestones() -> list:
    lines = ["## 6. Proof milestones", ""]
    if not ROADMAP.is_file():
        return lines + ["source missing: .planning/PROVEN_EDGE_ROADMAP.md", ""]
    text = ROADMAP.read_text(encoding="utf-8")
    for tag in ("M-A", "M-B", "M-C"):
        line = _milestone_line(text, tag)
        lines.append(f"- {line}" if line else f"- {tag}: not found in roadmap")
    lines.append("")
    lines.append(f"M-A accrual: {SOURCES['m_a_accrual']}")
    lines.append(f"rung8 accrual: {SOURCES['rung8_accrual']}")
    lines.append("")
    return lines


def render_footer(sources_used: list) -> list:
    lines = ["## 7. Footer", ""]
    lines.append(f"Generated at: {datetime.now(timezone.utc).isoformat()}")
    lines.append("Sources:")
    for s in sources_used:
        lines.append(f"- {s}")
    lines.append("")
    lines.append(
        "Honest note: calibration/coverage/count language only, not a dollar edge "
        "claim (.claude/rules/no-edge-claims.md)."
    )
    lines.append("")
    return lines


def render_week(year: int, week: int) -> str:
    start, end = week_bounds(year, week)
    label = f"{year}-W{week:02d}"
    lines = [f"# Weekly Scoreboard -- {label}", "", f"Window: {start.isoformat()} .. {end.isoformat()}", ""]
    lines += render_coverage()
    gate_lines, week_rows = render_gate_throughput(start, end)
    lines += gate_lines
    lines += render_replications(week_rows)
    lines += render_false_discovery(start, end)
    lines += render_model_fleet()
    lines += render_proof_milestones()
    lines += render_footer([
        str(COVERAGE_MAP.relative_to(_ROOT)),
        str(INTERACTION_LEDGER.relative_to(_ROOT)),
        str(FALSE_DISCOVERY_LEDGER.relative_to(_ROOT)),
        str(ROADMAP.relative_to(_ROOT)),
    ])
    return "\n".join(lines) + "\n"


def write_week(year: int, week: int) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / f"{year}-W{week:02d}.md"
    out_path.write_text(render_week(year, week), encoding="utf-8")
    return out_path


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Render the weekly one-page scoreboard.")
    parser.add_argument("--week", default=None, help="ISO week, e.g. 2026-W29 (default: current week)")
    args = parser.parse_args(argv)
    year, week = parse_week_arg(args.week) if args.week else current_week()[:2]
    out_path = write_week(year, week)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
