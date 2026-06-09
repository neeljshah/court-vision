"""
build_player_onoff.py — Player On/Off Net-Rating Impact Atlas (2024-25)

Computes per-player on/off net-rating swing, approximate win-probability swing,
and per-game margin impact, then ranks players league-wide and per team.

OUTPUT: data/cache/intel_outcome/player_onoff.json

Net-Rating → Win-Probability Mapping
-------------------------------------
We use a logistic approximation anchored to empirical NBA data:
    P(win) ≈ logistic(net_rtg_swing * k)
where k is calibrated so that +10 net-rtg swing ≈ +0.065 win-prob swing
(consistent with NBA team-level empirical relationships: ~6–7pp per 10pts NRTG).
  k = log(0.065 / (1 - 0.065)) / 10  ≈ ... but we use a simpler linear approx
  in practice: win_prob_swing ≈ net_rtg_swing * 0.0325  (per-possession effect
  integrated over ~67 possessions/half-team → ~0.03 per net-rtg point).

Margin per game mapping:
  An on/off swing of X net-rtg points over the season translates to
  margin_swing ≈ X * (possessions_per_game / 100) ≈ X * 0.97
  (NBA avg ~96-97 possessions/game in 2024-25).

Confidence:
  LOW_CONFIDENCE if minutes_on < 200 (tiny sample; ~8 real games of meaningful time)
  OR n_games < 10.
  HIGH otherwise.

Python 3.9 | conda: basketball_ai
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent.parent.parent  # nba-ai-system/
OUT_DIR = ROOT / "data" / "cache" / "intel_outcome"
OUT_PATH = OUT_DIR / "player_onoff.json"
ONOFF_PATH = ROOT / "data" / "cache" / "on_off_features.parquet"
ADV_PATH = ROOT / "data" / "player_adv_stats.parquet"

# ── Constants ─────────────────────────────────────────────────────────────────
SEASON = "2024-25"
SEASON_START = "2024-10-01"  # filter adv_stats to 2024-25

# Possessions per game (NBA 2024-25 avg per team ≈ 97)
POSS_PER_GAME = 97.0

# Win-prob mapping: empirical NBA calibration
# +1 NRTG over a full game ≈ +0.0066 win-prob (Pythagorean derivative near .500)
# Linear approx good for the ±15 range we care about for individual players
WIN_PROB_SLOPE = 0.0066  # pp per net-rtg point (per-game basis)

# Small-sample thresholds
MIN_MINUTES_ON = 200   # < 200 min on-court → LOW_CONFIDENCE
MIN_GAMES = 10         # < 10 games played → LOW_CONFIDENCE

# Leaders list size
N_LEADERS = 50  # top-N swing leaders included in "leaders" key
N_PER_TEAM = None  # all players per team (sorted by swing)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _win_prob_swing(nrtg_swing: float) -> float:
    """Linear approximation: win-prob swing from net-rating swing.

    Calibration: a team with +10 NRTG runs ~+6.6pp win probability improvement
    in a single game. For an individual player on-court vs off-court we apply
    the same slope. Clamped to [-0.50, +0.50] for sanity.
    """
    raw = nrtg_swing * WIN_PROB_SLOPE
    return round(max(-0.50, min(0.50, raw)), 4)


def _margin_swing(nrtg_swing: float) -> float:
    """Per-game margin swing from net-rating swing.

    net_rtg is per 100 possessions. With ~97 possessions/game:
        margin_swing = nrtg_swing * (POSS_PER_GAME / 100)
    """
    return round(nrtg_swing * (POSS_PER_GAME / 100.0), 3)


def _confidence(minutes_on: float, n_games: int) -> str:
    if minutes_on < MIN_MINUTES_ON or n_games < MIN_GAMES:
        return "low"
    return "high"


def _fmt_player_id(pid: Any) -> str:
    """Return player_id as string (consistent with vault naming convention)."""
    return str(int(pid))


# ── Load Data ─────────────────────────────────────────────────────────────────

def load_onoff() -> pd.DataFrame:
    df = pd.read_parquet(ONOFF_PATH)
    # Filter to primary season
    df = df[df["season"] == SEASON].copy()
    # Use on_off_diff (identical to on_off_net_rating_diff per recon)
    df = df.rename(columns={
        "on_court_plus_minus": "on_net",
        "off_court_plus_minus": "off_net",
        "on_off_diff": "onoff_swing",
        "minutes_on": "minutes",
        "player_name": "raw_name",
        "team_abbreviation": "team",
    })
    # Normalise player name: "Last, First" → "First Last"
    def _normalize_name(n: str) -> str:
        if "," in n:
            parts = [p.strip() for p in n.split(",", 1)]
            return f"{parts[1]} {parts[0]}"
        return n

    df["name"] = df["raw_name"].apply(_normalize_name)
    return df[["player_id", "name", "team", "on_net", "off_net",
               "onoff_swing", "minutes", "on_off_impact_z"]].copy()


def load_n_games() -> pd.DataFrame:
    """Get n_games per player from player_adv_stats for 2024-25."""
    adv = pd.read_parquet(ADV_PATH, columns=["player_id", "game_id", "game_date"])
    adv = adv[adv["game_date"].astype(str) >= SEASON_START].copy()
    n_games = (
        adv.groupby("player_id")["game_id"]
        .nunique()
        .reset_index()
        .rename(columns={"game_id": "n_games"})
    )
    return n_games


# ── Build ─────────────────────────────────────────────────────────────────────

def build() -> dict:
    print(f"[build_player_onoff] Loading on/off features ({ONOFF_PATH.name})...")
    onoff = load_onoff()
    print(f"  {len(onoff)} player-rows for season={SEASON}")

    print(f"[build_player_onoff] Loading n_games from adv_stats ({ADV_PATH.name})...")
    n_games_df = load_n_games()
    print(f"  {len(n_games_df)} players with game logs since {SEASON_START}")

    # Merge
    df = onoff.merge(n_games_df, on="player_id", how="left")
    df["n_games"] = df["n_games"].fillna(0).astype(int)

    # Derived columns
    df["winprob_swing"] = df["onoff_swing"].apply(_win_prob_swing)
    df["margin_swing"] = df["onoff_swing"].apply(_margin_swing)
    df["confidence"] = df.apply(
        lambda r: _confidence(r["minutes"], r["n_games"]), axis=1
    )

    # ── Players dict ──────────────────────────────────────────────────────────
    players: dict[str, dict] = {}
    for _, row in df.iterrows():
        pid = _fmt_player_id(row["player_id"])
        players[pid] = {
            "name": row["name"],
            "team": row["team"],
            "on_net": round(float(row["on_net"]), 2),
            "off_net": round(float(row["off_net"]), 2),
            "onoff_swing": round(float(row["onoff_swing"]), 2),
            "winprob_swing": float(row["winprob_swing"]),
            "margin_swing": float(row["margin_swing"]),
            "minutes": round(float(row["minutes"]), 1),
            "n_games": int(row["n_games"]),
            "confidence": row["confidence"],
        }

    # ── League-wide leaders list ──────────────────────────────────────────────
    df_sorted = df.sort_values("onoff_swing", ascending=False).reset_index(drop=True)

    leaders = []
    for rank, (_, row) in enumerate(df_sorted.iterrows(), start=1):
        leaders.append({
            "rank": rank,
            "player_id": _fmt_player_id(row["player_id"]),
            "name": row["name"],
            "team": row["team"],
            "onoff_swing": round(float(row["onoff_swing"]), 2),
            "winprob_swing": float(row["winprob_swing"]),
            "margin_swing": float(row["margin_swing"]),
            "minutes": round(float(row["minutes"]), 1),
            "n_games": int(row["n_games"]),
            "confidence": row["confidence"],
        })

    # ── Per-team view ─────────────────────────────────────────────────────────
    by_team: dict[str, list] = {}
    for team, grp in df.groupby("team"):
        grp_sorted = grp.sort_values("onoff_swing", ascending=False)
        team_list = []
        for _, row in grp_sorted.iterrows():
            team_list.append({
                "player_id": _fmt_player_id(row["player_id"]),
                "name": row["name"],
                "onoff_swing": round(float(row["onoff_swing"]), 2),
                "winprob_swing": float(row["winprob_swing"]),
                "margin_swing": float(row["margin_swing"]),
                "minutes": round(float(row["minutes"]), 1),
                "n_games": int(row["n_games"]),
                "confidence": row["confidence"],
            })
        by_team[team] = team_list

    # ── Metadata ──────────────────────────────────────────────────────────────
    n_high = int((df["confidence"] == "high").sum())
    n_low = int((df["confidence"] == "low").sum())

    output = {
        "_meta": {
            "schema_version": "1.0",
            "season": SEASON,
            "source_files": [
                str(ONOFF_PATH.relative_to(ROOT)),
                str(ADV_PATH.relative_to(ROOT)),
            ],
            "generated": "2026-06-01",
            "n_players_total": len(df),
            "n_high_confidence": n_high,
            "n_low_confidence": n_low,
            "units": {
                "on_net": "net_rating points per 100 possessions (team, when player is on court)",
                "off_net": "net_rating points per 100 possessions (team, when player is off court)",
                "onoff_swing": "on_net minus off_net (net_rtg pts/100 poss); positive = team better with player on",
                "winprob_swing": "approximate single-game win-probability impact (fraction, not pct); linear: onoff_swing * 0.0066",
                "margin_swing": "approximate per-game scoring margin impact (points); onoff_swing * (97/100)",
                "minutes": "on-court minutes for 2024-25 season",
                "n_games": "games played in 2024-25 (from adv stats game log)",
                "confidence": "low if minutes_on < 200 OR n_games < 10; high otherwise",
            },
            "winprob_mapping": {
                "method": "linear",
                "formula": "winprob_swing = onoff_swing * 0.0066",
                "calibration": "empirical NBA: +10 NRTG ≈ +6.6pp win-probability per game (Pythagorean near .500); applied at player on/off level",
                "caveat": "on/off is teammate-confounded and lineup-composition sensitive; treat as rough ordering signal not precise estimate",
            },
            "margin_mapping": {
                "method": "linear",
                "formula": "margin_swing = onoff_swing * 0.97",
                "calibration": "NBA 2024-25 avg ~97 possessions per team per game; net_rtg/100 * 97 = expected scoring margin contribution",
            },
            "caveats": [
                "On/off net rating is severely teammate-confounded: star players share court with other stars; bench players show inflated swings due to garbage-time opponents.",
                "Small samples (< 200 min on-court) produce wild point estimates — flagged LOW_CONFIDENCE.",
                "No opponent-strength adjustment is applied. Teams with easy schedules inflate on-court net ratings.",
                "This is a descriptive within-season impact metric. For betting use, treat as rough roster-composition context, not a causal effect size.",
                "The margin/winprob conversion assumes average possession rate and is a linear approximation — valid for swings under ~15 net-rtg points.",
            ],
        },
        "players": players,
        "leaders": leaders,
        "by_team": by_team,
    }

    return output


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    data = build()

    OUT_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n[build_player_onoff] Written → {OUT_PATH}")
    print(f"  Players: {data['_meta']['n_players_total']}")
    print(f"  High-confidence: {data['_meta']['n_high_confidence']}")
    print(f"  Low-confidence:  {data['_meta']['n_low_confidence']}")

    # ── Print summary ──────────────────────────────────────────────────────────
    leaders = data["leaders"]
    print(f"\n{'='*60}")
    print("TOP-10 ON/OFF SWING LEADERS (league-wide, highest → team gains most with player on):")
    print(f"{'='*60}")
    for entry in leaders[:10]:
        conf_flag = "" if entry["confidence"] == "high" else " [LOW-CONF]"
        print(
            f"  #{entry['rank']:>3}  {entry['name']:<28}  {entry['team']}  "
            f"swing={entry['onoff_swing']:+6.1f}  margin={entry['margin_swing']:+5.2f}pt/g  "
            f"min={entry['minutes']:>5.0f}  g={entry['n_games']:>2}{conf_flag}"
        )

    print(f"\n{'='*60}")
    print("BOTTOM-5 (team loses the most with player on court):")
    print(f"{'='*60}")
    for entry in leaders[-5:]:
        conf_flag = "" if entry["confidence"] == "high" else " [LOW-CONF]"
        print(
            f"  #{entry['rank']:>3}  {entry['name']:<28}  {entry['team']}  "
            f"swing={entry['onoff_swing']:+6.1f}  margin={entry['margin_swing']:+5.2f}pt/g  "
            f"min={entry['minutes']:>5.0f}  g={entry['n_games']:>2}{conf_flag}"
        )

    print(f"\nFile size: {OUT_PATH.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
