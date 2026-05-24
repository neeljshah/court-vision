#!/usr/bin/env python3
"""Post-hoc fix: populate empty team_abbrev in tracking_data.csv for games
where the original color→team mapping failed (scoreboard OCR couldn't read
score/period to anchor home/away).

Strategy: brute-force the 2 possible mappings (white=team_A/green=team_B vs
swapped). For each, count how many pbp_shot_context rows would have
shooter_team_matches_pbp=1. Pick the mapping with more matches.

For each fixed game:
  1. Pull PBP team abbrevs (LAL vs UTA, etc.)
  2. Read tracking_data.csv player_id → color
  3. Read pbp_shot_context.csv shooter_id + pbp_team
  4. For each candidate mapping {color_a: team_X, color_b: team_Y}:
     count shooters where pid_color (via mapping) == pbp_team
  5. Apply winning mapping: update tracking_data.csv team_abbrev column
  6. Re-extract pbp_shot_context for that game

Backs up tracking_data.csv to .bak_teamfix before writing.
Idempotent: skip games where team_abbrev is already populated.

Usage:
    python3 scripts/fix_team_abbrev_postscript.py --all
    python3 scripts/fix_team_abbrev_postscript.py --game-ids 0022500282
    python3 scripts/fix_team_abbrev_postscript.py --all --dry-run
"""
from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

TRACKING_ROOT = Path("/workspace/nba-ai-system/data/tracking")


def needs_fix(gid: str) -> bool:
    """Returns True if game's tracking_data has mostly-empty team_abbrev."""
    td = TRACKING_ROOT / gid / "tracking_data.csv"
    if not td.exists():
        return False
    n_total = n_empty = 0
    with open(td, encoding="utf-8", errors="replace") as f:
        for i, r in enumerate(csv.DictReader(f)):
            n_total += 1
            if not r.get("team_abbrev", "").strip():
                n_empty += 1
            if i > 2000:  # sample
                break
    return n_total > 0 and (n_empty / n_total) > 0.8


def gather_evidence(gid: str) -> dict:
    """Read tracking + pbp_shot_context; return per-player color and pbp shooter data."""
    d = TRACKING_ROOT / gid
    td = d / "tracking_data.csv"
    pbp = d / "pbp_shot_context.csv"

    # pid → most common color
    pid_color_votes: dict[str, Counter] = defaultdict(Counter)
    colors_seen: set[str] = set()
    with open(td, encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            pid = r.get("player_id", "").strip()
            color = r.get("team", "").strip()
            if pid and color:
                pid_color_votes[pid][color] += 1
                colors_seen.add(color)
    pid_color = {pid: votes.most_common(1)[0][0] for pid, votes in pid_color_votes.items()}

    # pbp_team → list of shooter_ids (with counts)
    pbp_shooter_pairs = []
    pbp_teams_seen: set[str] = set()
    with open(pbp, encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            sid = r.get("shooter_id", "").strip()
            pteam = r.get("pbp_team", "").strip()
            if sid and pteam:
                pbp_shooter_pairs.append((sid, pteam))
                pbp_teams_seen.add(pteam)

    return {
        "pid_color": pid_color,
        "colors": sorted(colors_seen),
        "pbp_pairs": pbp_shooter_pairs,
        "pbp_teams": sorted(pbp_teams_seen),
    }


def pick_mapping(evidence: dict) -> dict | None:
    """Try both color→team mappings; return the higher-match one or None if unclear."""
    colors = evidence["colors"]
    teams = evidence["pbp_teams"]
    if len(colors) != 2 or len(teams) != 2:
        return None  # only handle clean 2-color 2-team case

    pid_color = evidence["pid_color"]
    pairs = evidence["pbp_pairs"]
    if not pairs:
        return None

    candidates = [
        {colors[0]: teams[0], colors[1]: teams[1]},
        {colors[0]: teams[1], colors[1]: teams[0]},
    ]
    best = None
    best_score = -1
    for cand in candidates:
        n_match = 0
        for sid, pteam in pairs:
            pcolor = pid_color.get(sid)
            if pcolor and cand.get(pcolor) == pteam:
                n_match += 1
        if n_match > best_score:
            best_score = n_match
            best = cand
    return {
        "mapping": best,
        "matched": best_score,
        "total": len(pairs),
        "pct": 100 * best_score / len(pairs) if pairs else 0,
    }


def apply_mapping(gid: str, mapping: dict[str, str]) -> int:
    """Rewrite tracking_data.csv with team_abbrev populated. Returns rows updated."""
    d = TRACKING_ROOT / gid
    td = d / "tracking_data.csv"
    bak = td.with_suffix(".csv.bak_teamfix")
    if not bak.exists():
        shutil.copy2(td, bak)

    with open(td, encoding="utf-8", errors="replace") as f:
        rows = list(csv.DictReader(f))
        fields = (next(iter(csv.DictReader(open(td, encoding="utf-8", errors="replace"))), {})).keys() if rows else []
    # Re-read fields properly
    with open(td, encoding="utf-8", errors="replace") as f:
        r = csv.DictReader(f)
        fields = list(r.fieldnames or [])

    if "team_abbrev" not in fields:
        fields.append("team_abbrev")

    n_updated = 0
    for row in rows:
        color = row.get("team", "")
        if color in mapping and not row.get("team_abbrev", "").strip():
            row["team_abbrev"] = mapping[color]
            n_updated += 1

    with open(td, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    return n_updated


def reextract(gid: str) -> bool:
    """Re-run extract_pbp_shot_context.py for one game."""
    r = subprocess.run(
        ["python3", "scripts/extract_pbp_shot_context.py", "--game-ids", gid],
        cwd="/workspace/nba-ai-system",
        capture_output=True, text=True, check=False,
    )
    return r.returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-ids", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--min-confidence", type=float, default=70.0,
                    help="don't apply if winning mapping <X%% match rate")
    args = ap.parse_args()

    if args.all or not args.game_ids:
        gids = sorted(p.name for p in TRACKING_ROOT.iterdir()
                      if p.is_dir() and p.name.startswith("00")
                      and (p / "tracking_data.csv").exists())
    else:
        gids = args.game_ids

    needs = [g for g in gids if needs_fix(g)]
    print(f"Checking {len(gids)} games, {len(needs)} need team_abbrev fix"
          + (" [DRY RUN]" if args.dry_run else ""))

    n_fixed = 0
    for gid in needs:
        try:
            ev = gather_evidence(gid)
        except Exception as e:
            print(f"  {gid}: gather ERR {e}")
            continue
        result = pick_mapping(ev)
        if result is None:
            print(f"  {gid}: SKIP (need exactly 2 colors and 2 PBP teams, got {ev['colors']} / {ev['pbp_teams']})")
            continue
        pct = result["pct"]
        mapping = result["mapping"]
        tag = " [LOW CONFIDENCE]" if pct < args.min_confidence else ""
        print(f"  {gid}: {result['matched']}/{result['total']} ({pct:.1f}%) "
              f"-> {mapping}{tag}")
        if pct < args.min_confidence:
            continue
        if args.dry_run:
            continue
        n_updated = apply_mapping(gid, mapping)
        print(f"    updated {n_updated} tracking_data rows; re-extracting...")
        if reextract(gid):
            n_fixed += 1
            print(f"    OK")
        else:
            print(f"    re-extract FAILED")

    print(f"\nDone: {n_fixed} games fixed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
