"""domains.basketball_nba.tools_payton_clean -- quarantine the Elfrid-Payton
(player_id 203901) contamination in the 2024-25 corpus and rebuild the
pbp-derived lineup chain from clean sources.

ROOT CAUSE (already guarded forward in ingest_espn_player_box.parse_summary_players
+ backfill_pbp_espn.convert_game_actions): ESPN's 2024-25 feed labels a set of
real NOP/CHA guards' box AND pbp records as "Elfrid Payton" (retired 2021-22),
so a name-join resolved them to NBA id 203901. The stat lines are REAL but the
IDENTITY is wrong; there is no true id in the pbp either (it repeats the same
mislabel), so the honest treatment is to SEVER the false 203901 identity into
the repo's negative-placeholder convention (synthetic_id, stable per name) in
BOTH the box parquet and the pbp cache, then rebuild stints/on-off/gravity/
spacing/matchups (all pbp-derived) so the placeholder -- not 203901 -- flows
through.

Rows are identified by the audited bad id (203901) UNION anything the forward
guard (is_stale_resolution) would flag on the current parquet. HONEST: the box
parquet only spans 2024-25 + 2025-26, so the guard has no prior-season history
to self-detect Payton and flags 0 additional here; the 24 rows are caught by
the bad-id + no-other-season signature. As the parquet accrues seasons the
guard catches this class at ingest time without a manual pass.

Backs up before mutating: player_boxscores.parquet -> .bak_payton; each touched
pbp file -> <name>.json.bak_payton. NETWORK: zero. Local data only; never
git-added.

CLI:  python -m domains.basketball_nba.tools_payton_clean            # full run
      python -m domains.basketball_nba.tools_payton_clean --dry-run  # report only
Per-file test: python -m pytest domains/basketball_nba/test_tools_payton_clean.py -q
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

import pandas as pd

from domains.basketball_nba.ingest_espn_player_box import (
    is_stale_resolution,
    load_activity_windows,
)
from domains.basketball_nba.repair_pbp_sub_ids import synthetic_id

REPO_ROOT = Path(__file__).resolve().parents[2]
_BOX = REPO_ROOT / "data" / "domains" / "basketball_nba" / "player_boxscores.parquet"
_QBOX = REPO_ROOT / "data" / "cache" / "quarter_box"
_PBP_2425 = REPO_ROOT / "data" / "cache" / "team_system" / "pbp_2024_25"
_LINEUPS = REPO_ROOT / "data" / "cache" / "team_system" / "lineups"

BAD_ID = 203901
BAD_NAME = "Elfrid Payton"
SEASON = "2024-25"
PLACEHOLDER = synthetic_id(BAD_NAME)  # stable negative id shared by box + pbp


# --------------------------------------------------------------------------- #
# Pure helpers (covered by the per-file test)
# --------------------------------------------------------------------------- #

def flagged_box_ids(box_df: pd.DataFrame, activity: Dict[int, set],
                    season: str = SEASON, bad_id: int = BAD_ID) -> Tuple[Set[int], int]:
    """Return (ids_to_quarantine, n_guard_flagged) for *season*.

    Quarantine = the audited bad id present in *season* UNION any id whose
    (id, season) the forward guard flags on this parquet. n_guard_flagged is the
    guard-only count (reported to show whether the corpus is deep enough for the
    guard to self-detect the class -- 0 on the 2-season parquet)."""
    s = box_df[box_df["season"] == season]
    ids: Set[int] = set()
    if (s["player_id"] == bad_id).any():
        ids.add(bad_id)
    guarded = {int(pid) for pid in s["player_id"].unique()
               if is_stale_resolution(int(pid), season, activity)}
    return ids | guarded, len(guarded)


def repair_box(box_df: pd.DataFrame, ids: Set[int], placeholder: int = PLACEHOLDER,
               season: str = SEASON) -> pd.DataFrame:
    """Reassign quarantined ids -> negative placeholder within *season* only."""
    out = box_df.copy()
    mask = out["season"].eq(season) & out["player_id"].isin(ids)
    out.loc[mask, "player_id"] = placeholder
    return out


def scrub_actions(actions: List[dict], bad_id: int = BAD_ID,
                  placeholder: int = PLACEHOLDER) -> int:
    """Replace personId==bad_id -> placeholder in a pbp actions list (in place).
    Returns count replaced. Preserves lineup STRUCTURE (a real player was on the
    floor; only the false NBA identity is severed)."""
    n = 0
    for a in actions:
        if a.get("personId") == bad_id:
            a["personId"] = placeholder
            n += 1
    return n


# --------------------------------------------------------------------------- #
# I/O + orchestration
# --------------------------------------------------------------------------- #

def scrub_quarter_box(qbox_dir: Path, game_ids: Set[str], bad_id: int = BAD_ID,
                      placeholder: int = PLACEHOLDER) -> dict:
    """Scrub player_id==bad_id -> placeholder in the q1-q4 SOURCE cache for the
    contaminated games, so a rebuild via ingest_boxscores reproduces the clean
    parquet (the box parquet edit alone would be undone by the next re-ingest)."""
    c = {"files_changed": 0, "records_scrubbed": 0}
    for gid in sorted(game_ids):
        for fp in sorted(qbox_dir.glob(f"{gid}_q*.json")):
            d = json.loads(fp.read_text(encoding="utf-8"))
            n = sum(1 for p in d.get("players", []) if p.get("player_id") == bad_id)
            if not n:
                continue
            for p in d["players"]:
                if p.get("player_id") == bad_id:
                    p["player_id"] = placeholder
            bak = fp.with_suffix(".json.bak_payton")
            if not bak.exists():
                shutil.copy2(fp, bak)
            fp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            c["files_changed"] += 1
            c["records_scrubbed"] += n
    return c


def scrub_pbp_dir(pbp_dir: Path, bad_id: int = BAD_ID,
                  placeholder: int = PLACEHOLDER) -> dict:
    c = {"files_changed": 0, "actions_scrubbed": 0}
    for fp in sorted(pbp_dir.glob("*.json")):
        d = json.loads(fp.read_text(encoding="utf-8"))
        n = scrub_actions(d["game"]["actions"], bad_id, placeholder)
        if n:
            bak = fp.with_suffix(".json.bak_payton")
            if not bak.exists():
                shutil.copy2(fp, bak)
            fp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            c["files_changed"] += 1
            c["actions_scrubbed"] += n
    return c


def _run(mod: str, *args: str) -> None:
    cmd = [sys.executable, "-m", mod, *args]
    print("  $", " ".join(["python", "-m", mod, *args]))
    r = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    tail = (r.stdout or "").strip().splitlines()[-2:] + (r.stderr or "").strip().splitlines()[-2:]
    for line in tail:
        print("   ", line)
    if r.returncode != 0:
        raise SystemExit(f"rebuild step failed: {mod} (rc={r.returncode})")


def rebuild_chain() -> None:
    L = _LINEUPS
    pbp = str(_PBP_2425)
    stints = str(L / "stints_2024_25.parquet")
    onoff = str(L / "on_off_2024_25.parquet")
    _run("domains.basketball_nba.lineups.pbp_lineups", "--pbp-dir", pbp, "--out", stints)
    _run("domains.basketball_nba.lineups.on_off", "--stints", stints, "--pbp-dir", pbp, "--out", onoff)
    _run("domains.basketball_nba.lineups.gravity_spacing", "--stints", stints, "--on-off", onoff,
         "--pbp-dir", pbp, "--gravity-out", str(L / "gravity_proxy_2024_25.parquet"),
         "--spacing-out", str(L / "lineup_spacing_2024_25.parquet"))
    _run("domains.basketball_nba.lineups.lineup_matchups", "--stints", stints,
         "--out", str(L / "lineup_matchups_2024_25.parquet"))
    _run("domains.basketball_nba.interactions.lineup_synergy", "--stints", stints,
         "--on-off", onoff, "--out", str(L / "lineup_synergy_2024_25.parquet"))


def _artifact_stats() -> Dict[str, int]:
    out: Dict[str, int] = {}
    for p in [_BOX] + sorted(_LINEUPS.glob("*_2024_25.parquet")):
        try:
            out[p.name] = len(pd.read_parquet(p))
        except Exception:  # noqa: BLE001
            out[p.name] = -1
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="quarantine Elfrid-Payton (203901) 2024-25 contamination + rebuild")
    ap.add_argument("--dry-run", action="store_true", help="report contaminated rows only; mutate nothing")
    args = ap.parse_args()

    box = pd.read_parquet(_BOX)
    activity = load_activity_windows()
    ids, n_guard = flagged_box_ids(box, activity)
    contaminated = box[(box["season"] == SEASON) & (box["player_id"].isin(ids))]
    print(f"[report] 2024-25 quarantine ids={sorted(ids)}  box rows={len(contaminated)}  "
          f"guard-only-flagged={n_guard} (0 expected: 2-season parquet lacks prior history)")
    print(contaminated[["game_id", "team", "player_name", "min", "pts", "ast"]].to_string())
    if args.dry_run:
        return 0

    print("[before]", _artifact_stats())

    bak = _BOX.with_suffix(".parquet.bak_payton")
    if not bak.exists():
        shutil.copy2(_BOX, bak)
        print(f"[backup] {bak.name}")
    repair_box(box, ids).to_parquet(_BOX, index=False)
    print(f"[box] reassigned {len(contaminated)} rows -> placeholder {PLACEHOLDER}")

    game_ids = set(contaminated["game_id"].astype(str))
    print("[qbox]", scrub_quarter_box(_QBOX, game_ids))
    print("[pbp]", scrub_pbp_dir(_PBP_2425))
    print("[rebuild] pbp-derived 2024-25 chain:")
    rebuild_chain()
    print("[after]", _artifact_stats())
    return 0


if __name__ == "__main__":
    sys.exit(main())
