"""domains.basketball_nba.repair_pbp_sub_ids -- fill unmapped substitution
personIds in an ESPN-derived pbp cache dir, IN PLACE, from the sub's own
description text ("X enters the game for Y").

WHY: backfill_pbp_espn resolves sub names via ingest_espn_player_box.
load_player_map, which only knows players present in player_boxscores.parquet
(2024-25 + 2025-26). Players who left the league before 2024-25 resolve to
personId=None (9,245 sub records across the 2023-24 fetch), and pbp_lineups
cannot track a None through the lineup walk -- n_on_court==5 coverage fell to
78% vs 99.97% on 2024-25. Lineup reconstruction only needs stable IDENTITY,
not a real NBA id: any name the player_map misses gets a deterministic
synthetic negative id, -crc32(normalized name) (stable across runs, cannot
collide with real positive personIds; lineup_key already comma-joins so
negative ids are safe -- see pbp_lineups._make_stint).

ponytail: subs only -- non-sub actions' personId does not drive the lineup
walk. The same fallback belongs in backfill_pbp_espn._convert_play for future
season fetches (2022-23); this module repairs the already-fetched corpus
without a 1230-game refetch.

NETWORK: zero. CLI: python -m domains.basketball_nba.repair_pbp_sub_ids --pbp-dir <dir>
Per-file test: python -m pytest domains/basketball_nba/test_repair_pbp_sub_ids.py -q
"""
from __future__ import annotations

import argparse
import json
import zlib
from pathlib import Path
from typing import Dict

from domains.basketball_nba.backfill_pbp_espn import _SUB_RE
from domains.basketball_nba.ingest_espn_player_box import _norm_name, load_player_map


def synthetic_id(name: str) -> int:
    """Deterministic negative id for a name the player map misses."""
    return -int(zlib.crc32(_norm_name(name).encode("utf-8")))


def repair_actions(actions: list, player_map: Dict[str, int]) -> int:
    """Fill personId on unmapped substitution actions in place; returns count filled."""
    filled = 0
    for a in actions:
        if a.get("actionType") != "substitution" or a.get("personId") is not None:
            continue
        m = _SUB_RE.match(a.get("description") or "")
        if not m:
            continue
        name = (m.group(1) if a.get("subType") == "in" else m.group(2)).strip()
        if not name:
            continue
        a["personId"] = player_map.get(_norm_name(name), synthetic_id(name))
        filled += 1
    return filled


def repair_dir(pbp_dir: Path) -> dict:
    player_map = load_player_map()
    c = {"files": 0, "files_changed": 0, "subs_filled": 0}
    for fp in sorted(pbp_dir.glob("*.json")):
        c["files"] += 1
        d = json.loads(fp.read_text(encoding="utf-8"))
        n = repair_actions(d["game"]["actions"], player_map)
        if n:
            fp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
            c["files_changed"] += 1
            c["subs_filled"] += n
    return c


def main() -> int:
    ap = argparse.ArgumentParser(description="fill unmapped sub personIds in an ESPN pbp cache dir")
    ap.add_argument("--pbp-dir", required=True)
    args = ap.parse_args()
    c = repair_dir(Path(args.pbp_dir))
    print(f"RESULT {c}")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
