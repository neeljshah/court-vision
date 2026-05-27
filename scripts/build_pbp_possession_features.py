"""
build_pbp_possession_features.py
=================================
Extract per-player, per-game possession/play-type features from PBP JSON cache.

PBP SCHEMA (per event):
  period         : int  (1-4 regular, 5+ OT)
  game_clock_sec : int  (elapsed seconds in period; 0=period start, 720=end of Q4)
  event_type     : int  (1=made FG, 2=missed FG, 3=FT, 4=rebound, 5=turnover, 6=foul,
                         8=substitution, 0/13=misc/start/end)
  event_desc     : str  (natural-language description; used for shot-type tagging)
  player_name    : str  (last name only, e.g. "Tatum", "Carter Jr.", "Caldwell-Pope")
  team_abbrev    : str  (3-letter team code)
  score          : str  ("HH-VV" or "")
  score_margin   : str  (signed int as string, or "")

PLAY-TYPE TAGGING STRATEGY:
  No explicit ISO/PnR/PostUp play-type codes exist in this PBP schema.
  We use shot-description keyword matching (NBA official nomenclature):
    iso-proxy      : "Pullup" OR "Step Back" OR "Fadeaway" OR "Turnaround" (unassisted)
    pnr_handler    : "Pullup" shot that IS assisted (assisted pullup = PnR ball-handler)
    pnr_screener   : assisted shot by a big-man-type shot (Dunk, Layup, Hook, short distance)
                     NOTE: cannot distinguish screener vs cutter from desc alone —
                     counted as "assisted close-range shot" (documented fallback).
    post_up        : "Hook", "Turnaround", or "Fadeaway" (classic post moves)
    transition     : "Running" dunk/layup OR "Fast Break" (no "Fast Break" found in this
                     schema so only "Running" shots used as transition proxy)
    late_clock     : any FG attempt with game_clock_sec mod 24 <= 4 (last 4s of shot clock).
                     NOTE: shot clock cannot be exactly reconstructed from PBP; using
                     inter-event gap as proxy. Documented limitation.
    clutch         : Q4 (period==4) or OT (period>=5), clock>=420 (last 5 min),
                     |score_margin| <= 5
    and1           : made FG immediately followed by a P.FOUL on the same player

OUTPUT:
  data/cache/pbp_possession_features.parquet   — per-game rows
  data/cache/pbp_possession_features_l5.parquet — per-(player, game_date) rolling L5 rows
"""

from __future__ import annotations
import json, glob, re, sys, os
from pathlib import Path
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT = Path("C:/Users/neelj/nba-ai-system")
PBP_GLOB = str(ROOT / "data/nba/pbp_*.json")
OUT_PERGAME = ROOT / "data/cache/pbp_possession_features.parquet"
OUT_L5 = ROOT / "data/cache/pbp_possession_features_l5.parquet"
PF_PATH = ROOT / "data/player_pf.parquet"
POS_PATH = ROOT / "data/player_positions.parquet"

# ---------------------------------------------------------------------------
# Shot-type keyword patterns
# ---------------------------------------------------------------------------
ISO_KEYS = re.compile(r"Pullup|Pull-Up|Step Back|Fadeaway|Turnaround", re.I)
POST_KEYS = re.compile(r"Hook|Turnaround Fadeaway|Fadeaway|Turnaround", re.I)
RUNNING_KEYS = re.compile(r"Running|Fast Break", re.I)
ASSISTED = re.compile(r"\d+ AST\)", re.I)        # "(Player N AST)" in made-FG desc
CLOSE_RANGE = re.compile(r"Layup|Dunk|Hook|Finger Roll|Tip", re.I)
AND1_FOUL = re.compile(r"S\.FOUL|P\.FOUL|Shooting Foul", re.I)

# ---------------------------------------------------------------------------
# Build player name -> player_id lookup
# ---------------------------------------------------------------------------

def build_name_lookup() -> dict[tuple[str, str, str], int]:
    """
    Returns {(last_name_pbp, team_abbrev, game_id): player_id}.
    Falls back to (last_name, game_id) if team_abbrev fails.

    Sources (merged so older seasons are covered):
      1. player_pf.parquet — has team_abbreviation; covers 2024-25
      2. player_adv_stats.parquet — no team_abbrev; covers 2022-23..2024-25
         → populates the 2-key fallback for older games
    """
    pos = pd.read_parquet(POS_PATH)

    def pbp_last(name: str) -> str:
        """Extract the last-name token as it appears in PBP (last name + suffix)."""
        if not name:
            return ""
        parts = name.strip().split()
        if not parts:
            return ""
        if parts[-1] in ("Jr.", "Sr.", "II", "III", "IV") and len(parts) >= 2:
            return " ".join(parts[-2:])   # e.g. "Carter Jr."
        return parts[-1]                  # e.g. "Tatum", "Caldwell-Pope"

    lookup: dict[tuple[str, str, str], int] = {}

    # --- Source 1: player_pf (has team_abbreviation) ---
    if PF_PATH.exists():
        pf = pd.read_parquet(PF_PATH)
        df = pf[["player_id", "game_id", "team_abbreviation"]].merge(
            pos[["player_id", "display_name"]], on="player_id", how="left"
        )
        df["display_name"] = df["display_name"].fillna("")
        df["last_name"] = df["display_name"].apply(pbp_last)
        for _, row in df.iterrows():
            key3 = (row["last_name"], row["team_abbreviation"], row["game_id"])
            key2 = (row["last_name"], row["game_id"])
            pid = int(row["player_id"])
            lookup.setdefault(key3, pid)
            lookup.setdefault(key2, pid)

    # --- Source 2: player_adv_stats (covers 2022-23..2024-25; no team_abbrev) ---
    # Only populate the 2-key fallback for games not already covered.
    ADV_PATH = ROOT / "data" / "player_adv_stats.parquet"
    if ADV_PATH.exists():
        adv = pd.read_parquet(ADV_PATH, columns=["player_id", "game_id"])
        adv = adv.merge(pos[["player_id", "display_name"]], on="player_id", how="left")
        adv["display_name"] = adv["display_name"].fillna("")
        adv["last_name"] = adv["display_name"].apply(pbp_last)
        for _, row in adv.iterrows():
            key2 = (row["last_name"], row["game_id"])
            pid = int(row["player_id"])
            lookup.setdefault(key2, pid)   # don't overwrite pf-sourced entries

    return lookup


# ---------------------------------------------------------------------------
# Parse one game's PBP file list -> list of event dicts with game_id
# ---------------------------------------------------------------------------

def parse_game_pbp(game_id: str, files: list[str]) -> list[dict]:
    events = []
    for fpath in sorted(files):  # p1, p2, p3, p4, p5
        try:
            with open(fpath, encoding="utf-8") as f:
                raw = json.load(f)
            for e in raw:
                e["game_id"] = game_id
                events.append(e)
        except Exception:
            pass
    return events


# ---------------------------------------------------------------------------
# Resolve player_name -> player_id using lookup
# ---------------------------------------------------------------------------

def resolve_pid(name: str, team: str, game_id: str, lookup: dict) -> int | None:
    if not name:
        return None
    key3 = (name, team, game_id)
    if key3 in lookup:
        return lookup[key3]
    key2 = (name, game_id)
    return lookup.get(key2, None)


# ---------------------------------------------------------------------------
# Extract per-player per-game counts from one game's events
# ---------------------------------------------------------------------------

def compute_game_features(
    game_id: str, events: list[dict], lookup: dict, game_date: str
) -> list[dict]:
    """
    Returns list of {player_id, game_id, game_date, pbp_*} dicts.
    """
    # Per-player accumulators
    from collections import defaultdict
    acc: dict[int, dict] = defaultdict(lambda: {
        "pbp_iso_poss_count": 0,
        "pbp_pnr_ball_handler": 0,
        "pbp_pnr_screener_proxy": 0,
        "pbp_post_up_count": 0,
        "pbp_transition_count": 0,
        "pbp_late_clock_shots": 0,
        "pbp_clutch_shots_attempted": 0,
        "pbp_clutch_pts_scored": 0,
        "pbp_and1_count": 0,
        "_fg_attempts": 0,     # internal — for avg seconds proxy
        "_total_clock": 0,
    })

    # Walk events; keep track of previous made-FG for and-1 detection
    prev_made_fg: dict | None = None  # last made-FG event

    for i, evt in enumerate(events):
        etype = evt.get("event_type", -1)
        desc = evt.get("event_desc", "")
        name = evt.get("player_name", "")
        team = evt.get("team_abbrev", "")
        period = int(evt.get("period", 0))
        clock = int(evt.get("game_clock_sec", 0))

        pid = resolve_pid(name, team, game_id, lookup)
        if pid is None:
            prev_made_fg = None if etype not in (1, 2) else prev_made_fg
            continue

        a = acc[pid]

        if etype == 1:  # made FG
            is_assisted = bool(ASSISTED.search(desc))
            a["_fg_attempts"] += 1
            a["_total_clock"] += clock

            # Play-type tagging
            if ISO_KEYS.search(desc) and not is_assisted:
                a["pbp_iso_poss_count"] += 1

            if ISO_KEYS.search(desc) and is_assisted:
                # Assisted pullup -> PnR ball handler
                a["pbp_pnr_ball_handler"] += 1

            if is_assisted and CLOSE_RANGE.search(desc):
                # Assisted close-range shot -> PnR screener / cutter proxy
                a["pbp_pnr_screener_proxy"] += 1

            if POST_KEYS.search(desc):
                a["pbp_post_up_count"] += 1

            if RUNNING_KEYS.search(desc):
                a["pbp_transition_count"] += 1

            # Clutch: Q4 or OT, last 5 min (clock >= 420), margin <= 5
            if (period == 4 or period >= 5) and clock >= 420:
                margin_str = str(evt.get("score_margin", "")).strip()
                try:
                    margin = abs(int(margin_str))
                    if margin <= 5:
                        a["pbp_clutch_shots_attempted"] += 1
                        # Extract pts from desc: "(N PTS)"
                        pts_m = re.search(r"\((\d+) PTS\)", desc)
                        if pts_m:
                            a["pbp_clutch_pts_scored"] += int(pts_m.group(1))
                except (ValueError, TypeError):
                    pass

            # Late clock: check if this is close to shot clock expiry
            # Heuristic: if clock gap from previous event < 4 seconds, flag
            # (We don't have explicit shot clock; use inter-event gap proxy)
            if i > 0:
                prev_clock = int(events[i - 1].get("game_clock_sec", clock))
                gap = clock - prev_clock
                if 0 < gap <= 4:
                    a["pbp_late_clock_shots"] += 1

            prev_made_fg = {"pid": pid, "idx": i, "period": period}

        elif etype == 2:  # missed FG
            a["_fg_attempts"] += 1
            a["_total_clock"] += clock

            if RUNNING_KEYS.search(desc):
                a["pbp_transition_count"] += 1

            # Clutch missed shot
            if (period == 4 or period >= 5) and clock >= 420:
                margin_str = str(evt.get("score_margin", "")).strip()
                try:
                    margin = abs(int(margin_str))
                    if margin <= 5:
                        a["pbp_clutch_shots_attempted"] += 1
                except (ValueError, TypeError):
                    pass

            if i > 0:
                prev_clock = int(events[i - 1].get("game_clock_sec", clock))
                gap = clock - prev_clock
                if 0 < gap <= 4:
                    a["pbp_late_clock_shots"] += 1

            prev_made_fg = None

        elif etype == 6:  # foul
            # And-1: shooting foul immediately after a made FG by same player
            if prev_made_fg is not None and AND1_FOUL.search(desc):
                # Check if fouled player matches prev FG scorer
                fouled_name = desc.split()[0] if desc else ""
                fouled_pid = resolve_pid(fouled_name, team, game_id, lookup)
                if fouled_pid == prev_made_fg["pid"] and i - prev_made_fg["idx"] <= 3:
                    acc[prev_made_fg["pid"]]["pbp_and1_count"] += 1
            prev_made_fg = None

        else:
            if etype not in (3, 4, 8, 0, 13):  # not FT/reb/sub/misc
                prev_made_fg = None

    # Build rows
    rows = []
    for pid, a in acc.items():
        fg = max(a["_fg_attempts"], 1)
        rows.append({
            "player_id": pid,
            "game_id": game_id,
            "game_date": game_date,
            "pbp_iso_poss_count": a["pbp_iso_poss_count"],
            "pbp_pnr_ball_handler": a["pbp_pnr_ball_handler"],
            "pbp_pnr_screener_proxy": a["pbp_pnr_screener_proxy"],
            "pbp_post_up_count": a["pbp_post_up_count"],
            "pbp_transition_count": a["pbp_transition_count"],
            "pbp_late_clock_shots": a["pbp_late_clock_shots"],
            "pbp_clutch_shots_attempted": a["pbp_clutch_shots_attempted"],
            "pbp_clutch_pts_scored": a["pbp_clutch_pts_scored"],
            "pbp_and1_count": a["pbp_and1_count"],
            "pbp_avg_seconds_per_touch": round(a["_total_clock"] / fg, 2),
        })
    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("[build_pbp_possession_features] Starting...")

    # Load name lookup
    lookup = build_name_lookup()
    print(f"  Name lookup entries: {len(lookup):,}")

    # Load game_date from player_pf + player_adv_stats (covers 2022-23..present)
    game_date_map: dict[str, str] = {}

    # Source 1: player_adv_stats — covers 2022-23, 2023-24, 2024-25
    ADV_PATH = ROOT / "data" / "player_adv_stats.parquet"
    if ADV_PATH.exists():
        adv_gd = pd.read_parquet(ADV_PATH, columns=["game_id", "game_date"])
        adv_gd = adv_gd.drop_duplicates("game_id").set_index("game_id")["game_date"].astype(str)
        game_date_map.update(adv_gd.to_dict())
        print(f"  game_date_map from player_adv_stats: {len(game_date_map):,} games")

    # Source 2: player_pf — overrides with most authoritative dates for 2024-25
    if PF_PATH.exists():
        pf = pd.read_parquet(PF_PATH)
        pf_gd = (
            pf.drop_duplicates("game_id")
            .set_index("game_id")["game_date"]
            .astype(str)
        )
        game_date_map.update(pf_gd.to_dict())
        print(f"  game_date_map after player_pf merge: {len(game_date_map):,} games")

    # Group PBP files by game_id
    all_files = sorted(glob.glob(PBP_GLOB))
    game_files: dict[str, list[str]] = {}
    for fpath in all_files:
        m = re.search(r"pbp_(\d+)_p(\d+)\.json$", fpath)
        if not m:
            continue
        gid = m.group(1)
        game_files.setdefault(gid, []).append(fpath)

    print(f"  PBP games found: {len(game_files)}")

    # Process each game
    all_rows: list[dict] = []
    skipped = 0
    for gid, files in sorted(game_files.items()):
        game_date = game_date_map.get(gid, "")
        events = parse_game_pbp(gid, files)
        if not events:
            skipped += 1
            continue
        rows = compute_game_features(gid, events, lookup, game_date)
        all_rows.extend(rows)

    print(f"  Games processed: {len(game_files) - skipped}, skipped: {skipped}")

    if not all_rows:
        print("  No rows produced — exiting.")
        sys.exit(0)

    # Build per-game DataFrame
    pg = pd.DataFrame(all_rows)
    pg["game_date"] = pd.to_datetime(pg["game_date"], errors="coerce")
    pg = pg.sort_values(["player_id", "game_date"]).reset_index(drop=True)

    # Remove rows with no FG attempts (all zeros except avg_seconds)
    count_cols = [c for c in pg.columns if c.startswith("pbp_") and c != "pbp_avg_seconds_per_touch"]
    pg = pg[pg[count_cols].sum(axis=1) > 0].copy()

    print(f"  Per-game rows (non-zero): {len(pg):,}")
    print(f"  Null rates per column:")
    for col in pg.columns:
        null_rate = pg[col].isna().mean()
        if null_rate > 0:
            print(f"    {col}: {null_rate:.3f}")

    # Write per-game parquet
    OUT_PERGAME.parent.mkdir(parents=True, exist_ok=True)
    pg.to_parquet(OUT_PERGAME, index=False)
    print(f"  Saved: {OUT_PERGAME}")

    # ---------------------------------------------------------------------------
    # Rolling L5 features
    # ---------------------------------------------------------------------------
    ROLL_COLS = [
        ("pbp_iso_poss_count", "pbp_iso_poss_l5_avg"),
        ("pbp_pnr_ball_handler", "pbp_pnr_handler_l5_avg"),
        ("pbp_clutch_shots_attempted", "pbp_clutch_shots_l5_avg"),
    ]

    pg_sorted = pg.sort_values(["player_id", "game_date"]).copy()
    for src_col, dst_col in ROLL_COLS:
        pg_sorted[dst_col] = (
            pg_sorted.groupby("player_id")[src_col]
            .transform(lambda s: s.shift(1).rolling(5, min_periods=2).mean())
        )

    l5_cols = ["player_id", "game_id", "game_date"] + [dst for _, dst in ROLL_COLS]
    l5 = pg_sorted[l5_cols].dropna(subset=[dst for _, dst in ROLL_COLS], how="all")

    print(f"  Rolling L5 rows: {len(l5):,}")
    l5.to_parquet(OUT_L5, index=False)
    print(f"  Saved: {OUT_L5}")

    # ---------------------------------------------------------------------------
    # Sample rows for Luka (1629029) and Trae Young (1629027)
    # ---------------------------------------------------------------------------
    for name_label, pid in [("Luka Doncic", 1629029), ("Trae Young", 1629027)]:
        sub = pg[pg["player_id"] == pid]
        if sub.empty:
            print(f"\n  {name_label} (pid={pid}): no rows in per-game output.")
        else:
            print(f"\n  {name_label} (pid={pid}) — {len(sub)} games:")
            print(sub.head(3).to_string(index=False))
        sub_l5 = l5[l5["player_id"] == pid]
        if not sub_l5.empty:
            print(f"  Rolling L5 sample:")
            print(sub_l5.dropna().head(3).to_string(index=False))

    print("\n[build_pbp_possession_features] Done.")


if __name__ == "__main__":
    main()
