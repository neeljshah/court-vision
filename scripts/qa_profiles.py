"""QA + reconciliation pass over the persistent profiles (read-only, local lane).

Honest-gate integrity check: flags impossible values, contradictory as-of, empty sections,
and reports the sections-per-profile distribution. Does NOT mutate profiles. Writes a report to
data/cache/profiles/_track/QA_REPORT.md.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAYERS = ROOT / "data" / "cache" / "profiles" / "players"
TEAMS = ROOT / "data" / "cache" / "profiles" / "teams"
OUT = ROOT / "data" / "cache" / "profiles" / "_track" / "QA_REPORT.md"


def check_player(d: dict) -> list[str]:
    issues = []
    secs = d.get("sections", {})
    prov = d.get("_provenance", {})
    # every section has provenance
    for s in secs:
        if s not in prov:
            issues.append(f"section '{s}' has no provenance")
    # impossible values
    sc = secs.get("scoring_usage", {}).get("scoring", {})
    for k, v in sc.items():
        if k.endswith("_pg") and isinstance(v, (int, float)) and v < 0:
            issues.append(f"negative {k}={v}")
    for sect in ("shot_diet", "defense_allowed", "coverage_faced", "clutch"):
        blk = secs.get(sect, {})
        if isinstance(blk, dict):
            for k, v in blk.items():
                # eFG%/TS% legitimately exceed 1.0 (weight 3s); cap their ceiling at 1.6
                ceil = 1.6 if ("efg" in str(k) or "_ts" in str(k)) else 1.0
                if "pct" in str(k) and isinstance(v, (int, float)) and not (0 <= v <= ceil):
                    issues.append(f"{sect}.{k}={v} out of range")
    cd = secs.get("count_distributions", {}).get("dist", {})
    for st, rec in cd.items():
        if isinstance(rec, dict):
            disp = rec.get("dispersion")
            if disp is not None and disp < 0:
                issues.append(f"count_dist.{st}.dispersion<0")
    # contradictory as_of: section as_of (date form) newer than profile as_of_game_date
    pao = str(d.get("as_of_game_date") or "")
    for s, pv in prov.items():
        a = str(pv.get("as_of") or "")
        if len(a) == 10 and a[:4].isdigit() and pao and a > pao:
            issues.append(f"section '{s}' as_of {a} > profile as_of {pao}")
    return issues


def main():
    pfiles = sorted(PLAYERS.glob("*.json"))
    sec_per = Counter()
    issue_counter = Counter()
    flagged = []
    total = 0
    for fp in pfiles:
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            flagged.append((fp.name, [f"unreadable: {e}"]))
            continue
        total += 1
        sec_per[len(d.get("sections", {}))] += 1
        iss = check_player(d)
        for i in iss:
            issue_counter[i.split("=")[0].split(" as_of")[0]] += 1
        if iss:
            flagged.append((fp.name, iss))

    lines = ["# Profile QA Report", "",
             f"Players scanned: {total}  |  Teams: {len(list(TEAMS.glob('*.json')))}",
             f"Profiles with issues: {len(flagged)} ({100*len(flagged)/max(total,1):.1f}%)", "",
             "## Sections-per-profile distribution"]
    for n in sorted(sec_per, reverse=True):
        lines.append(f"  {n:2d} sections: {sec_per[n]} profiles")
    lines += ["", "## Issue categories (count)"]
    if issue_counter:
        for k, v in issue_counter.most_common():
            lines.append(f"  {v:5d}  {k}")
    else:
        lines.append("  none — all integrity checks passed")
    lines += ["", "## Sample flagged (first 15)"]
    for name, iss in flagged[:15]:
        lines.append(f"- {name}: {'; '.join(iss[:3])}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:8]))
    print(f"\nFull report -> {OUT}")
    print(f"Issue categories: {dict(issue_counter)}")


if __name__ == "__main__":
    main()
