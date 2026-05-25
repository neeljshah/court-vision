"""aggregate_dnp_rows.py — tier3-11 (loop 5) DNP-aware projection set infra.

Builds `data/dnp_rows.parquet` from the existing
`data/nba/boxscore_adv_*.json` cache. Each row represents a (game_id,
player_id) pair where the player was on the active roster but DID NOT
PLAY (zero minutes, with a DNP comment in the boxscore).

Why this exists
---------------
Cycles 90b + 92e tried T1-C (b2b veteran shrink) and both REJECTED. The
post-mortem (see scripts/_results/b2b_veteran_v2_real_b2b.md) traced the
failure to SELECTION BIAS: gamelog_*.json only contains games the player
ACTUALLY PLAYED. The landyourbets prior "veterans 33+ sit ~80% of b2b
second nights" is structurally invisible in that dataset — the 80% are
silent. The 20% that show up are by selection the vets in good health
and good form, exactly the wrong slice to shrink.

The fix is to materialise DNP rows from the boxscore_adv cache (which
DOES list every rostered player, including DNPs with status comments
like "DNP - Coach's Decision" / "DNP - Injury / Illness"). With those
rows the b2b vet probe (and future sit-rate probes) can validate
honestly: predict for every rostered vet on every b2b game and compare
against {0 if DNP, realised stat if played}.

Output schema (parquet)
-----------------------
- game_id (str)
- game_date (str ISO YYYY-MM-DD)
- season (str e.g. '2022-23')
- player_id (int)
- player (str — namei field, e.g. "L. James")
- team (str — teamtricode)
- dnp_reason (str — normalised: "coach_decision" | "injury" | "inactive" |
              "other" — full comment lives in dnp_comment)
- dnp_comment (str — raw comment from boxscore)
- expected_to_play (bool — currently always True because boxscore_adv
              ONLY lists active-roster players; G-Leaguers and inactives
              are filtered out by NBA-Stats already)

Usage
-----
    python scripts/aggregate_dnp_rows.py

This is a one-shot aggregation, safe to re-run; it walks every
boxscore_adv_*.json and overwrites the parquet.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from typing import Dict, List, Optional

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

_NBA_CACHE = os.path.join(PROJECT_DIR, "data", "nba")
_OUT_PATH = os.path.join(PROJECT_DIR, "data", "dnp_rows.parquet")


def _normalise_reason(comment: str) -> str:
    """Coarse classification of the DNP comment.

    NBA boxscore comments follow a small vocabulary. The classifier is
    intentionally lossy — the raw string is preserved in dnp_comment for
    consumers who need full fidelity.
    """
    c = (comment or "").lower().strip()
    if not c:
        return "other"
    if "coach" in c:
        return "coach_decision"
    if "injur" in c or "illness" in c or "soreness" in c or "sprain" in c \
            or "strain" in c or "rest" in c or "sick" in c \
            or "concussion" in c or "personal" in c or "fracture" in c \
            or "surger" in c or "contusion" in c or "spasm" in c:
        return "injury"
    if "inactive" in c or "g league" in c or "assignment" in c \
            or "not with team" in c or "suspension" in c \
            or "suspended" in c:
        return "inactive"
    if "did not play" in c or "dnp" in c:
        # DNP with no specific reason → bucket as coach_decision
        return "coach_decision"
    return "other"


def _load_game_date_lookup() -> Dict[str, tuple]:
    """game_id -> (game_date_iso, season) from season_games_*.json files."""
    out: Dict[str, tuple] = {}
    for path in sorted(glob.glob(os.path.join(_NBA_CACHE, "season_games_*.json"))):
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            continue
        rows = d.get("rows", []) if isinstance(d, dict) else []
        for r in rows:
            gid = str(r.get("game_id") or "").strip()
            gdate = str(r.get("game_date") or "").strip()
            season = str(r.get("season") or "").strip()
            if gid and gdate:
                out[gid] = (gdate, season)
    return out


def _is_dnp(player: dict) -> bool:
    """A player is DNP when minutes is empty AND comment indicates a DNP.

    Supports two boxscore schemas:
    - boxscore_adv_*.json: 'minutes' / 'personid' / 'namei' / 'teamtricode'
    - boxscore_*.json (cycle 93a/96b 2025-26 backfill): 'min' / 'player_id'
      / 'player_name' / 'team_abbreviation'
    """
    mins = str(player.get("minutes") or player.get("min") or "").strip()
    if mins and mins not in ("0", "00:00", "0:00"):
        return False
    comment = str(player.get("comment") or "").lower().strip()
    if not comment:
        return False  # empty minutes + empty comment → likely just a parse glitch
    # Filter out obvious non-DNP markers (a played game might have a comment
    # like "starter" — defensive even though we already checked minutes).
    if "did not play" in comment or "dnp" in comment or "inactive" in comment \
            or "injury" in comment or "illness" in comment \
            or "g league" in comment or "personal" in comment \
            or "suspension" in comment or "suspended" in comment:
        return True
    return False


def aggregate(out_path: Optional[str] = None) -> Dict[str, int]:
    """Walk boxscore_adv cache and write data/dnp_rows.parquet.

    Returns counts {n_games, n_dnp_rows, n_skipped_no_date}.
    """
    out_path = out_path or _OUT_PATH

    date_lookup = _load_game_date_lookup()
    print(f"Loaded {len(date_lookup)} game_id -> date entries from season_games_*.json",
          flush=True)

    # Walk both old (boxscore_adv_*) AND new (boxscore_*) schemas. The
    # 2025-26 backfill from cycles 93a/96b populated boxscore_*.json with a
    # lowercase schema (min, player_id, player_name, team_abbreviation).
    adv_paths = sorted(glob.glob(os.path.join(_NBA_CACHE, "boxscore_adv_*.json")))
    # Plain boxscore_*.json minus the boxscore_adv_*.json files (which would
    # also match boxscore_*).
    all_box_paths = sorted(glob.glob(os.path.join(_NBA_CACHE, "boxscore_*.json")))
    plain_paths = [p for p in all_box_paths if "boxscore_adv_" not in os.path.basename(p)]
    # Dedup: prefer adv (richer) when both exist for a game_id.
    adv_gids = {os.path.basename(p).replace("boxscore_adv_", "").replace(".json", "")
                for p in adv_paths}
    plain_paths = [p for p in plain_paths
                   if os.path.basename(p).replace("boxscore_", "").replace(".json", "")
                   not in adv_gids]
    paths = adv_paths + plain_paths
    print(f"Walking {len(adv_paths)} boxscore_adv + {len(plain_paths)} "
          f"plain boxscore files ({len(paths)} total)...", flush=True)

    rows: List[dict] = []
    n_games = 0
    n_skipped_no_date = 0
    n_dnp_rows = 0
    by_reason: Dict[str, int] = {}
    by_season: Dict[str, int] = {}
    games_by_season: Dict[str, set] = {}

    for path in paths:
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            continue
        n_games += 1
        gid = str(d.get("game_id") or "").strip()
        if not gid:
            n_skipped_no_date += 1
            continue
        date_season = date_lookup.get(gid)
        if not date_season:
            n_skipped_no_date += 1
            continue
        gdate, season = date_season
        games_by_season.setdefault(season, set()).add(gid)

        for p in d.get("players", []):
            if not _is_dnp(p):
                continue
            comment = str(p.get("comment") or "")
            reason = _normalise_reason(comment)
            try:
                pid = int(p.get("personid") or p.get("player_id") or 0)
            except Exception:
                pid = 0
            if pid == 0:
                continue
            rows.append({
                "game_id": gid,
                "game_date": gdate,
                "season": season,
                "player_id": pid,
                "player": str(p.get("namei") or p.get("player_name") or ""),
                "team": str(p.get("teamtricode") or p.get("team_abbreviation") or ""),
                "dnp_reason": reason,
                "dnp_comment": comment,
                "expected_to_play": True,
            })
            n_dnp_rows += 1
            by_reason[reason] = by_reason.get(reason, 0) + 1
            by_season[season] = by_season.get(season, 0) + 1

    # Persist as parquet (preferred) with CSV fallback for fresh checkouts
    # missing pyarrow.
    try:
        import pandas as pd  # noqa: PLC0415
        df = pd.DataFrame(rows)
        try:
            df.to_parquet(out_path, index=False)
            wrote = out_path
        except Exception as exc:
            csv_path = out_path.replace(".parquet", ".csv")
            df.to_csv(csv_path, index=False)
            wrote = csv_path
            print(f"  (parquet unavailable — wrote CSV fallback at {csv_path}: "
                  f"{type(exc).__name__})", flush=True)
    except Exception:
        # No pandas at all — should never hit in this repo but keep the
        # script runnable.
        wrote = out_path.replace(".parquet", ".jsonl")
        with open(wrote, "w", encoding="utf-8") as fp:
            for r in rows:
                fp.write(json.dumps(r) + "\n")

    print(f"\nWrote {wrote}", flush=True)
    print(f"\nSummary:", flush=True)
    print(f"  games scanned:           {n_games}", flush=True)
    print(f"  games missing date:      {n_skipped_no_date}", flush=True)
    print(f"  DNP rows:                {n_dnp_rows}", flush=True)
    print(f"\nDNP rows by reason:", flush=True)
    for k in sorted(by_reason, key=lambda x: -by_reason[x]):
        print(f"  {k:<20s} {by_reason[k]:>6d}", flush=True)
    print(f"\nDNP rate per season (rough — DNP rows / (games * 13 active players)):",
          flush=True)
    for s in sorted(by_season):
        gset = games_by_season.get(s, set())
        n_g = max(len(gset), 1)
        # NBA active list is typically 13/team => ~26 active per game; ~210
        # game-player rows after subtracting the ~16 who play.
        denom = n_g * 26
        rate = by_season[s] / denom if denom else 0.0
        print(f"  {s}: {by_season[s]:>5d} DNP rows / {n_g:>4d} games  "
              f"=> ~{rate*100:5.2f}% of active-roster slots", flush=True)

    return {
        "n_games": n_games,
        "n_dnp_rows": n_dnp_rows,
        "n_skipped_no_date": n_skipped_no_date,
        "by_reason": by_reason,
        "by_season": by_season,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=_OUT_PATH,
                    help="output parquet path (default data/dnp_rows.parquet)")
    args = ap.parse_args()
    aggregate(args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
