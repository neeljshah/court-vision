"""
cv_fix_inplay_fetch.py — Build a large multi-team in-game win-probability corpus.

Step 1: pull 2025-26 game_ids (Regular Season + Playoffs) via leaguegamelog,
        determine home team + final winner from MATCHUP/WL/PTS. Save id list.
Step 2: for each game, fetch playbyplayv3, reconstruct per-event game state
        (time_remaining, period, scores, margin) and label home_win.
        Cache per-game rows to data/cache/cv_fix/inplay_rows/<gid>.json.

CV / tracking OUT OF SCOPE. Pure NBA API + PBP.

stats.nba.com requires the headers patch imported BEFORE any nba_api endpoint.
"""

import re
import json
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data import nba_api_headers_patch  # noqa: F401,E402  (MUST be first)
from nba_api.stats.endpoints import leaguegamelog, playbyplayv3
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data/cache/cv_fix"
ROWS_DIR = CACHE / "inplay_rows"
ROWS_DIR.mkdir(parents=True, exist_ok=True)
IDS_PATH = CACHE / "inplay_game_ids.json"

SEASON = "2025-26"
PERIOD_SEC = 720          # 12 min regulation period
OT_SEC = 300              # 5 min OT period
REGULATION_SECONDS = 2880  # 4 * 720

RATE_LIMIT = 0.6  # seconds between stats.nba.com calls


def _parse_clock(clock_str: str) -> float:
    """Parse 'PT11M47.00S' -> seconds. Returns 0 on failure."""
    if not isinstance(clock_str, str):
        return 0.0
    m = re.match(r"PT(\d+)M([\d.]+)S", clock_str)
    if not m:
        return 0.0
    return int(m.group(1)) * 60 + float(m.group(2))


def time_remaining_game(period: int, clock_secs: float) -> float:
    """
    Seconds remaining in the GAME (0 at final buzzer).
    Regulation start = 2880. OT periods extend beyond regulation; we report
    seconds remaining within the *current* span so that 0 == game end is only
    known at the true final period. For modeling we use:
      - regulation periods 1-4: (4-period)*720 + clock  (max 2880, min 0)
      - OT periods (5+): clock_secs only (time left in this OT)
    We keep a separate flag for OT.
    """
    if period <= 4:
        return max(0.0, (4 - period) * PERIOD_SEC + clock_secs)
    # OT: time remaining in current OT period (game could still extend)
    return max(0.0, clock_secs)


def build_game_index() -> dict:
    """Return {game_id: {home_win, home_tricode, away_tricode}} for 2025-26."""
    frames = []
    for stype in ("Regular Season", "Playoffs"):
        try:
            df = leaguegamelog.LeagueGameLog(
                season=SEASON, season_type_all_star=stype
            ).get_data_frames()[0]
            df["_stype"] = stype
            frames.append(df)
            print(f"  {stype}: {df['GAME_ID'].nunique()} games")
        except Exception as e:  # noqa
            print(f"  {stype}: FAILED ({e})")
        time.sleep(RATE_LIMIT)

    full = pd.concat(frames, ignore_index=True)
    index = {}
    for gid, grp in full.groupby("GAME_ID"):
        # Home team row has 'vs.' in MATCHUP; away has '@'
        home_rows = grp[grp["MATCHUP"].str.contains("vs.", regex=False)]
        away_rows = grp[grp["MATCHUP"].str.contains("@", regex=False)]
        if len(home_rows) != 1 or len(away_rows) != 1:
            continue
        hr = home_rows.iloc[0]
        ar = away_rows.iloc[0]
        home_win = 1 if hr["WL"] == "W" else 0
        # sanity: scores must agree with WL
        if hr["PTS"] == ar["PTS"]:
            continue  # cannot happen, skip
        index[gid] = {
            "home_win": int(home_win),
            "home_tricode": hr["TEAM_ABBREVIATION"],
            "away_tricode": ar["TEAM_ABBREVIATION"],
            "home_pts": int(hr["PTS"]),
            "away_pts": int(ar["PTS"]),
            "season_type": hr["_stype"],
        }
    return index


def reconstruct_rows(gid: str, meta: dict) -> list:
    """
    Fetch PBP, build one row per event with score state.
    Each row: dict with feature primitives + home_win label.
    """
    df = playbyplayv3.PlayByPlayV3(game_id=gid).get_data_frames()[0]
    home_win = meta["home_win"]
    home_tri = meta["home_tricode"]

    rows = []
    prev_sh, prev_sa = 0, 0
    max_period = int(df["period"].max()) if len(df) else 4
    is_ot_game = max_period > 4

    # track recent scoring for "run" feature: list of (game_time_elapsed, margin)
    score_history = []  # (elapsed_sec_in_game, margin)

    for _, ev in df.iterrows():
        period = int(ev["period"])
        clock_secs = _parse_clock(ev["clock"])

        # parse scores (carry forward when blank)
        try:
            sh = int(ev["scoreHome"]) if str(ev["scoreHome"]).strip() else prev_sh
        except (ValueError, TypeError):
            sh = prev_sh
        try:
            sa = int(ev["scoreAway"]) if str(ev["scoreAway"]).strip() else prev_sa
        except (ValueError, TypeError):
            sa = prev_sa
        prev_sh, prev_sa = sh, sa

        secs_rem = time_remaining_game(period, clock_secs)

        # skip the literal pre-tip 0-0 / 2880 row (no information)
        if sh == 0 and sa == 0 and period == 1 and clock_secs >= 720:
            continue

        margin = sh - sa
        total = sh + sa

        # elapsed game seconds (regulation frame; OT counted as full reg + OT elapsed)
        if period <= 4:
            elapsed = REGULATION_SECONDS - secs_rem
        else:
            ot_idx = period - 4
            # full regulation + previous OTs fully elapsed + this OT progress
            elapsed = REGULATION_SECONDS + (ot_idx - 1) * OT_SEC + (OT_SEC - secs_rem)

        # recent run: margin change over last ~120s of game time
        score_history.append((elapsed, margin))
        run_margin = 0.0
        for e_t, m_t in reversed(score_history):
            if elapsed - e_t >= 120:
                run_margin = margin - m_t
                break
        else:
            if score_history:
                run_margin = margin - score_history[0][1]

        # possession indicator: +1 if last acting team is home, -1 away, 0 none
        tri = str(ev["teamTricode"]).strip() if ev["teamTricode"] is not None else ""
        if tri == home_tri:
            poss = 1
        elif tri and tri != home_tri:
            poss = -1
        else:
            poss = 0

        rows.append({
            "period": period,
            "secs_rem": round(secs_rem, 1),
            "score_home": sh,
            "score_away": sa,
            "margin": margin,
            "total": total,
            "run_margin": round(run_margin, 1),
            "poss": poss,
            "is_ot": 1 if period > 4 else 0,
            "home_win": home_win,
        })
    return rows


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 250
    time_budget = float(sys.argv[2]) if len(sys.argv) > 2 else 1700.0  # ~28 min

    # ---- game index ----
    if IDS_PATH.exists():
        print(f"Loading cached game index from {IDS_PATH}")
        index = json.loads(IDS_PATH.read_text())
    else:
        print("Building game index from leaguegamelog...")
        index = build_game_index()
        IDS_PATH.write_text(json.dumps(index, indent=2))
        print(f"Saved {len(index)} games to {IDS_PATH}")

    all_gids = list(index.keys())
    # Mix regular season + playoffs; spread across the list (every Nth)
    # to span many teams/dates rather than the first N chronological.
    playoff_gids = [g for g in all_gids if index[g]["season_type"] == "Playoffs"]
    reg_gids = [g for g in all_gids if index[g]["season_type"] == "Regular Season"]
    # evenly sample regular season across the season for team/date diversity
    if len(reg_gids) > limit:
        step = len(reg_gids) / float(limit)
        reg_sample = [reg_gids[int(i * step)] for i in range(limit)]
    else:
        reg_sample = reg_gids
    target = list(dict.fromkeys(playoff_gids + reg_sample))[:limit]

    print(f"Target: {len(target)} games "
          f"({len(playoff_gids)} playoff available, {len(reg_sample)} reg sampled)")

    start = time.time()
    fetched = 0
    cached_skip = 0
    failed = 0
    for i, gid in enumerate(target):
        out = ROWS_DIR / f"{gid}.json"
        if out.exists():
            cached_skip += 1
            continue
        if time.time() - start > time_budget:
            print(f"\nTime budget reached after {fetched} fetches; stopping.")
            break
        try:
            rows = reconstruct_rows(gid, index[gid])
            if len(rows) < 20:
                print(f"  [{i}] {gid}: only {len(rows)} rows, skipping")
                failed += 1
                continue
            out.write_text(json.dumps({"meta": index[gid], "rows": rows}))
            fetched += 1
            if fetched % 10 == 0:
                el = time.time() - start
                print(f"  fetched {fetched} games ({el:.0f}s elapsed)")
        except Exception as e:  # noqa
            print(f"  [{i}] {gid}: PBP FAILED ({e}); skipping")
            failed += 1
        time.sleep(RATE_LIMIT)

    total_cached = len(list(ROWS_DIR.glob("*.json")))
    print(f"\nDone. fetched={fetched} skipped(cached)={cached_skip} "
          f"failed={failed}")
    print(f"Total cached game files: {total_cached}")


if __name__ == "__main__":
    main()
