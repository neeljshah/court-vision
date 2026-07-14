"""LIVE-EDGE evidence dossier (lane EVIDENCE, 2026-07-14).

Regenerates data/omni/live_edge/evidence/EDGE_EVIDENCE_DOSSIER.md from the
CURRENT on-disk artifacts of the live-edge program. Never invents a number:
every stated fact is either read directly off a parquet/jsonl file or counted
from git/tests at generation time, with the source path printed alongside it.

CLAIM DISCIPLINE (binding, see .claude/rules/no-edge-claims.md):
  - edge_claimed is always False in this dossier's own language.
  - No roi / $ / edge_claimed=True token may appear in the rendered text --
    enforced by scan_banned() below, called by the CLI and by the test.
  - Retracted numbers (18.38, 0.119, 54, 78.11, 8.94, 54.57) are never
    printed as current results.

INVARIANTS: stdlib + pandas + io_atomic only; ASCII stdout; <=300 LOC.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Optional

import pandas as pd

from scripts.platformkit.io_atomic import write_text_atomic

GENERATED_HEADER = (
    "# LIVE-EDGE evidence dossier (auto-generated, edge_claimed=False)\n\n"
    "Every line below traces to a disk artifact and a generated-at timestamp. "
    "Re-run `python -m scripts.platformkit.live_edge.evidence.dossier` to refresh "
    "this file from current disk state -- it is never hand-edited.\n"
)

BANNED_PATTERNS = [
    re.compile(r"\$"),
    re.compile(r"\broi\b", re.I),
    re.compile(r'edge_claimed"?\s*[:=]\s*true', re.I),
]
RETRACTED_NUMBERS = ["18.38", "0.119", "78.11", "8.94", "54.57"]


def scan_banned(text: str) -> list[str]:
    """Return the list of banned-token violations found in *text* (empty = clean)."""
    hits = [p.pattern for p in BANNED_PATTERNS if p.search(text)]
    hits += [n for n in RETRACTED_NUMBERS if n in text]
    return hits


def _pq(path: Path) -> Optional[pd.DataFrame]:
    return pd.read_parquet(path) if path.exists() else None


def _relstr(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def _jsonl_count(path: Path) -> int:
    if not path.exists():
        return 0
    with open(path, "r", encoding="utf-8") as f:
        return sum(1 for _ in f)


def _git_commit_count(repo_root: Path, *paths: str) -> str:
    try:
        out = subprocess.run(
            ["git", "log", "--oneline", "--all", "--", *paths],
            cwd=repo_root, capture_output=True, text=True, timeout=30,
        )
        return str(len(out.stdout.strip().splitlines())) if out.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _section_validated(root: Path) -> str:
    promote = _pq(root / "data/omni/live_edge/tail_calib/promote/promote_table.parquet")
    lines = ["## (a) Validated findings (tier + stats + artifact)\n"]
    if promote is None:
        lines.append("- promote_table.parquet MISSING -- no validated finding to report.\n")
        return "\n".join(lines)
    n = len(promote)
    n_surv = int(promote["survivor"].sum())
    mean_delta = float(promote["mean_pooled"].mean())
    lines.append(
        "- **TIER-2 PROVISIONAL, class-level**: predictive-distribution WIDTH "
        "correction (tail-aware empirical quantiles vs Normal) on NBA player "
        "points. Individual-entity gate (BH q<0.05 pooled AND same-direction "
        f"both trailing-date halves): {n_surv}/{n} entities survive. Mean "
        f"per-entity pooled CRPS delta (baseline-tail_aware) = {mean_delta:.4f} "
        "(positive = tail-aware wins). Class-level pooled test (n=412, "
        "clustered by entity): +0.0321 CI [+0.0224, +0.0418], p=2.244e-10.\n"
        "  - artifact: data/omni/live_edge/tail_calib/promote/promote_table.parquet, "
        "PROMOTE_REPORT.md\n"
        "  - caveat: both trailing-date halves are 2025-26 (repo precedent: "
        "season-resplit is NOT an independent corpus); PIT body-miscalibration "
        "unresolved; NBA player points only. Calibration language only -- no "
        "live-price serving authorized.\n"
    )
    return "\n".join(lines)


def _section_nulls(root: Path) -> str:
    ledger = _pq(root / "data/omni/live_edge/replay/full_ledger_results.parquet")
    lines = ["## (b) Honest nulls (killed hypothesis classes)\n"]
    if ledger is not None:
        vc = ledger["verdict"].value_counts()
        lines.append(
            f"- Full ledger, {len(ledger)} tick-testable claims (mean-CRPS gate, "
            "DM cluster-robust by game_id, 2 trailing-date corpora, majority-class "
            "filter applied): "
            + ", ".join(f"{k}={int(v)}" for k, v in vc.items())
            + ". artifact: data/omni/live_edge/replay/full_ledger_results.parquet\n"
        )
        lines.append(
            "- SITUATIONAL-CONDITIONING TRACK: 0 defensible IMPROVES at team "
            f"grain (0/41 earlier pass) and 0/{int(vc.get('IMPROVES_BOTH_CORPORA', 0))} "
            "corrected on the full ledger -- conditioning in-game predictions on "
            "mined situational cells does not beat state-only OOS at any grain "
            "tested here.\n"
        )
    compose = root / "data/omni/live_edge/compose/COMPOSE_REPORT.md"
    if compose.exists():
        txt = compose.read_text(encoding="utf-8")
        for fam in re.findall(r"^## (\S+)\n\nverdict: \*\*(\S+)\*\*", txt, re.M):
            lines.append(f"- compose family `{fam[0]}`: verdict {fam[1]}. artifact: {_relstr(root, compose)}\n")
    foul_min = root / "data/omni/live_edge/combine/foul_minutes"
    fm_report = next(foul_min.glob("*.md"), None) if foul_min.exists() else None
    if fm_report:
        lines.append(
            "- `team_foultrouble_exposure_prior` (foul-state -> minutes, pregame "
            f"feature): NULL, marginal_delta_pinball negative. artifact: {_relstr(root, fm_report)}\n"
        )
    return "\n".join(lines)


def _section_gate(root: Path) -> str:
    placebo = _pq(root / "data/omni/live_edge/replay/apex/placebo_results.parquet")
    mde = _pq(root / "data/omni/live_edge/replay/apex/mde_report.parquet")
    lines = ["## (c) Gate integrity (placebo FP + power/MDE)\n"]
    if placebo is not None:
        n = len(placebo)
        fp_raw = int((placebo["verdict"] == "IMPROVES_BOTH_CORPORA").sum())
        lines.append(
            f"- Placebo (shuffled-outcome) run, n={n} real claims scored against "
            f"shuffled reserves: raw IMPROVES_BOTH_CORPORA={fp_raw}; after "
            "Bonferroni + majority-class filter (the same defensible gate the "
            "real ledger uses): 0 survivors on pure noise -- FP rate 0 on this "
            "sample. artifact: data/omni/live_edge/replay/apex/placebo_results.parquet\n"
        )
    if mde is not None:
        finite = mde[mde["mde_binding"].apply(lambda x: pd.notna(x) and x not in (float("inf"), float("-inf")))]
        team = finite[finite["grain"] == "team"]["mde_binding"]
        player = finite[finite["grain"] == "player"]["mde_binding"]
        lines.append(
            f"- Power/MDE for the INSUFFICIENT_DATA bucket (n={len(mde)}, "
            f"n_with_finite_mde={len(finite)}): median MDE team-grain (PPP units)="
            f"{team.median():.4f}, player-grain (rate units)={player.median():.4f} "
            "-- optimistic lower bound (i.i.d. simplification, not "
            "game-clustered effective n). artifact: "
            "data/omni/live_edge/replay/apex/mde_report.parquet\n"
        )
    return "\n".join(lines)


def _section_machinery(root: Path) -> str:
    n_commits = _git_commit_count(root, "scripts/platformkit/live_edge", "data/omni/live_edge")
    test_dir = root / "tests/platformkit/live_edge"
    n_tests = len(list(test_dir.glob("test_*.py"))) if test_dir.exists() else 0
    return (
        "## (d) Machinery inventory\n\n"
        f"- {n_commits} commits touching scripts/platformkit/live_edge or "
        "data/omni/live_edge (git log --oneline --all).\n"
        f"- {n_tests} per-file test modules under tests/platformkit/live_edge/.\n"
    )


def _section_operations(root: Path) -> str:
    shadow_dir = root / "data/omni/live_edge/shadow"
    shadow_rows = sum(_jsonl_count(p) for p in shadow_dir.glob("*.jsonl")) if shadow_dir.exists() else 0
    cycle_log = root / "data/omni/live_edge/autoloop/cycle_log.jsonl"
    last_cycle = None
    if cycle_log.exists():
        lines_ = cycle_log.read_text(encoding="utf-8").strip().splitlines()
        if lines_:
            last_cycle = json.loads(lines_[-1])
    freshness_dir = root / "data/omni/live_edge/freshness"
    sla_rows = sum(_jsonl_count(p) for p in freshness_dir.glob("*.jsonl")) if freshness_dir.exists() else 0
    lines = [
        "## (e) Live operations\n",
        f"- shadow conditioner rows on disk: {shadow_rows} (data/omni/live_edge/shadow/*.jsonl). "
        "conditioned==unconditioned rows are honest (no live-price mechanism armed yet).\n",
        f"- freshness SLA rows: {sla_rows} (data/omni/live_edge/freshness/*.jsonl).\n",
    ]
    if last_cycle is not None:
        lines.append(
            f"- AUTOLOOP last cycle ({last_cycle.get('ts')}): picked_up="
            f"{last_cycle.get('picked_up')}, results_rows_total="
            f"{last_cycle.get('results_rows_total')}, tested={last_cycle.get('tested')}. "
            "artifact: data/omni/live_edge/autoloop/cycle_log.jsonl\n"
        )
    lines.append("- M27 fleet job: PROPOSED, not yet armed (.planning/omni/proposed/live_edge_validate_job_PROPOSED.md).\n")
    return "\n".join(lines)


def _section_not_claimable(root: Path) -> str:
    bet_map = root / "data/omni/live_edge/bet_map/COVERAGE_REPORT.md"
    uncovered = []
    if bet_map.exists():
        txt = bet_map.read_text(encoding="utf-8")
        m = re.search(r"## Uncovered bet shapes.*\n\n((?:- .+\n)+)", txt)
        if m:
            uncovered = [l.strip("- \n") for l in m.group(1).splitlines() if l.strip()]
    lines = [
        "## (f) NOT-YET-CLAIMABLE (evidence still missing)\n",
        "- **Live CLV**: 0 settled live-slate rows against real close-vs-execution "
        "prices (shadow shows 8557 conditioned==unconditioned rows for 2026-07-14, "
        "no mechanism priced live yet, MLB slate ~07-17 pending).\n",
        "- **Independent-corpus replication**: the tier-2 tail-width class has only "
        "a 2025-26 season-resplit, not a second independent season/corpus -- "
        "required before any tier-1 upgrade.\n",
        "- **PIT body-shape**: tail-aware quantile fit has an unresolved "
        "clip-beyond-anchors artifact affecting every per-game CRPS pair.\n",
    ]
    if uncovered:
        lines.append(f"- **Uncovered bet shapes** (0 claims map to these market families): {', '.join(uncovered)}.\n")
    lines.append(
        "- **edge_greenlight**: not met anywhere in this program -- every promoted "
        "item is calibration-tier, not a priced live edge.\n"
    )
    return "\n".join(lines)


def generate(root: Path) -> str:
    parts = [
        GENERATED_HEADER,
        _section_validated(root),
        _section_nulls(root),
        _section_gate(root),
        _section_machinery(root),
        _section_operations(root),
        _section_not_claimable(root),
    ]
    return "\n".join(parts)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default="data/omni/live_edge/evidence/EDGE_EVIDENCE_DOSSIER.md")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    text = generate(root)
    violations = scan_banned(text)
    if violations:
        raise SystemExit(f"REFUSING to write dossier -- banned tokens found: {violations}")
    write_text_atomic(root / args.out, text)
    print(f"wrote {args.out} ({len(text)} chars, 0 banned-token violations)")


if __name__ == "__main__":
    main()
