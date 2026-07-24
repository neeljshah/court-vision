"""Context-conditioning: NBA team performance by game state (front-runner vs comeback).

From the running play-by-play scores in data/nba_ai.db (table play_by_play, sport='nba'),
for each team-game we compute the halftime margin (team perspective) and the second-half
margin. Split each team's games into "led at half" vs "trailed at half":

  front_runner_2h_margin = mean second-half margin in games the team LED at half
                           (positive => extends/holds leads)
  comeback_2h_margin     = mean second-half margin in games the team TRAILED at half
                           (positive => closes gaps when behind)

Front-runner teams sit high on the "led at half" axis; comeback teams high on the
"trailed at half" axis -- a quadrant scatter.

HONEST FLOOR: this corpus is thin (26 games, most teams appear 1-2x), so per-team
splits are near-empty. We enforce MIN_GAMES_PER_SPLIT and MASK teams below it rather
than print unstable per-team numbers. The robust, buildable result is the LEAGUE-LEVEL
mean-reversion stat over all team-games: does the second-half margin revert toward zero
relative to the halftime margin? That is n=team_games strong and reported as the headline.

Calibration/intelligence analytic. edge_claimed=False. No $/ROI claims.

CLI:
    python -m scripts.platformkit.analytics_showcase.ctx_team_states
    python -m scripts.platformkit.analytics_showcase.ctx_team_states --check
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

try:
    from scripts.platformkit.analytics_showcase._clone_safe import verify_recorded_artifact
except ImportError:  # bare-import fallback (running from module dir)
    from _clone_safe import verify_recorded_artifact

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DB = _REPO_ROOT / "data" / "nba_ai.db"
_OUT_JSON = Path(__file__).resolve().parent / "out" / "ctx_team_states.json"
_OUT_PNG = _REPO_ROOT / "docs" / "img" / "ctx_team_states.png"

MIN_GAMES_PER_SPLIT = 2  # need >=2 led AND >=2 trailed games to place a team on the quadrant


def _game_records(conn: sqlite3.Connection, game_id: str) -> Optional[List[Dict[str, Any]]]:
    """Return two team-game records for one game, or None if unusable.

    Uses running home_score/away_score (carry-forward across null non-scoring rows) to
    snapshot end-of-period scores, and score-increment votes to label home vs away team.
    """
    rows = list(conn.execute(
        "SELECT period, home_score, away_score, team_id FROM play_by_play "
        "WHERE game_id=? ORDER BY event_num", (game_id,)))
    if not rows:
        return None
    ph = pa = 0
    home_votes: Dict[str, int] = {}
    away_votes: Dict[str, int] = {}
    period_end: Dict[int, Tuple[int, int]] = {}
    for period, h, a, tid in rows:
        h = ph if h is None else h
        a = pa if a is None else a
        if tid:
            if h > ph:
                home_votes[tid] = home_votes.get(tid, 0) + 1
            if a > pa:
                away_votes[tid] = away_votes.get(tid, 0) + 1
        period_end[period] = (h, a)
        ph, pa = h, a
    if not home_votes or not away_votes or 2 not in period_end:
        return None
    home_team = max(home_votes, key=home_votes.get)
    away_team = max(away_votes, key=away_votes.get)
    if home_team == away_team:
        return None
    half_h, half_a = period_end[2]
    final_h, final_a = period_end[max(period_end)]  # includes OT if present
    half_margin_home = half_h - half_a
    final_margin_home = final_h - final_a
    second_half_home = final_margin_home - half_margin_home
    return [
        {"team": home_team, "opp": away_team, "half_margin": half_margin_home,
         "second_half_margin": second_half_home, "final_margin": final_margin_home},
        {"team": away_team, "opp": home_team, "half_margin": -half_margin_home,
         "second_half_margin": -second_half_home, "final_margin": -final_margin_home},
    ]


def _aggregate(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_team: Dict[str, Dict[str, List[float]]] = {}
    for r in records:
        d = by_team.setdefault(r["team"], {"led": [], "trailed": [], "all_half": [], "all_2h": []})
        d["all_half"].append(r["half_margin"])
        d["all_2h"].append(r["second_half_margin"])
        if r["half_margin"] > 0:
            d["led"].append(r["second_half_margin"])
        elif r["half_margin"] < 0:
            d["trailed"].append(r["second_half_margin"])
    teams: List[Dict[str, Any]] = []
    for team, d in sorted(by_team.items()):
        n_led, n_tr = len(d["led"]), len(d["trailed"])
        placed = n_led >= MIN_GAMES_PER_SPLIT and n_tr >= MIN_GAMES_PER_SPLIT
        teams.append({
            "team": team,
            "n_games": len(d["all_half"]),
            "n_led_at_half": n_led,
            "n_trailed_at_half": n_tr,
            "front_runner_2h_margin": round(float(np.mean(d["led"])), 3) if n_led else None,
            "comeback_2h_margin": round(float(np.mean(d["trailed"])), 3) if n_tr else None,
            "placed_on_quadrant": placed,
            "masked_below_floor": not placed,
        })
    return {"teams": teams}


def _league_stats(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Robust n=team_games headline: does the second-half margin revert toward zero
    relative to the halftime margin? slope<0 in the deviation sense => mean reversion."""
    x = np.array([r["half_margin"] for r in records], dtype=float)
    y = np.array([r["second_half_margin"] for r in records], dtype=float)
    n = len(records)
    if n < 3 or np.std(x) < 1e-9:
        return {"n_team_games": n, "buildable": False,
                "reason": "too few team-games or no halftime-margin spread"}
    slope, intercept = np.polyfit(x, y, 1)
    pearson = float(np.corrcoef(x, y)[0, 1])
    led = y[x > 0]
    trailed = y[x < 0]
    return {
        "n_team_games": n,
        "buildable": True,
        "slope_2h_on_half": round(float(slope), 4),
        "intercept": round(float(intercept), 4),
        "pearson_r": round(pearson, 4),
        "mean_2h_margin_when_led_at_half": round(float(led.mean()), 3) if led.size else None,
        "n_led": int(led.size),
        "mean_2h_margin_when_trailed_at_half": round(float(trailed.mean()), 3) if trailed.size else None,
        "n_trailed": int(trailed.size),
        "interpretation": (
            "slope < 0 => 2nd-half margin reverts against the halftime lead (mean reversion); "
            "~0 => leads persist; > 0 => leads compound. Descriptive stat, not an edge claim."),
    }


def build(db_path: Optional[Path] = None) -> Dict[str, Any]:
    path = db_path or _DB
    if not path.exists():
        return {"edge_claimed": False, "status": "not_buildable",
                "reason": f"nba_ai.db absent at {path} (gitignored on a fresh clone)"}
    conn = sqlite3.connect(str(path))
    try:
        as_of = conn.execute(
            "SELECT MAX(fetched_at) FROM play_by_play WHERE sport='nba'").fetchone()[0]
        game_ids = [r[0] for r in conn.execute(
            "SELECT DISTINCT game_id FROM play_by_play WHERE sport='nba'")]
        records: List[Dict[str, Any]] = []
        for gid in game_ids:
            recs = _game_records(conn, gid)
            if recs:
                records.extend(recs)
    finally:
        conn.close()

    if not records:
        return {"edge_claimed": False, "status": "not_buildable",
                "reason": "no usable team-game records (no running pbp scores)"}

    agg = _aggregate(records)
    league = _league_stats(records)
    n_placed = sum(1 for t in agg["teams"] if t["placed_on_quadrant"])
    if n_placed == 0:
        team_verdict = (
            "0 teams meet the n>=%d-per-split floor (led AND trailed at half): per-team "
            "front-runner vs comeback separation is NOT buildable from this %d-game corpus. "
            "Use the league-level mean-reversion stat as the headline." % (
                MIN_GAMES_PER_SPLIT, len(game_ids)))
    else:
        team_verdict = "%d teams meet the floor and are placed on the quadrant." % n_placed

    return {
        "edge_claimed": False,
        "as_of": as_of,
        "source_artifact": "data/nba_ai.db :: play_by_play (sport='nba')",
        "method": ("halftime margin & second-half margin per team-game from running pbp "
                   "scores; split each team's games by led/trailed at half"),
        "min_games_per_split": MIN_GAMES_PER_SPLIT,
        "n_games": len(game_ids),
        "n_team_games": len(records),
        "n_teams_placed_on_quadrant": n_placed,
        "team_verdict": team_verdict,
        "league_mean_reversion": league,
        "teams": agg["teams"],
        "floors_and_assumptions": [
            "Thin corpus: most teams appear 1-2x, so per-team splits are 0-2 games; teams "
            "below MIN_GAMES_PER_SPLIT in either split are masked, never printed as stable.",
            "Halftime = end of period 2; final includes OT if present (max period snapshot).",
            "Home/away labeled by score-increment votes; ties/degenerate games dropped.",
            "League stat is the robust n=team_games result; per-team is illustrative only.",
        ],
    }


def _render_png(data: Dict[str, Any], out_path: Path) -> bool:
    if data.get("status") == "not_buildable":
        return False
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:  # noqa: BLE001
        return False

    teams = [t for t in data["teams"]
             if t["front_runner_2h_margin"] is not None and t["comeback_2h_margin"] is not None]
    fig, ax = plt.subplots(figsize=(9, 8))
    ax.axhline(0, color="gray", lw=1)
    ax.axvline(0, color="gray", lw=1)
    for t in teams:
        placed = t["placed_on_quadrant"]
        ax.scatter(t["front_runner_2h_margin"], t["comeback_2h_margin"],
                   s=60 if placed else 30,
                   color="#1f77b4" if placed else "0.75",
                   edgecolor="black" if placed else "none", zorder=3 if placed else 2)
        ax.annotate(t["team"], (t["front_runner_2h_margin"], t["comeback_2h_margin"]),
                    fontsize=7, color="black" if placed else "0.6",
                    xytext=(3, 3), textcoords="offset points")
    ax.set_xlabel("front-runner axis: mean 2nd-half margin when LEADING at half")
    ax.set_ylabel("comeback axis: mean 2nd-half margin when TRAILING at half")
    n_placed = data.get("n_teams_placed_on_quadrant", 0)
    ax.set_title(
        "NBA team game-state quadrant (front-runner vs comeback)\n"
        "gray = below n>=%d-per-split floor (illustrative, not stable) | %d placed | "
        "calibration analytic, not an edge claim" % (MIN_GAMES_PER_SPLIT, n_placed))
    fig.text(0.5, 0.005,
             "Source: %s | as_of %s | edge_claimed=False" % (
                 data.get("source_artifact", "data/nba_ai.db"), data.get("as_of")),
             ha="center", fontsize=7, color="gray")
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return True


def main() -> int:
    data = build()
    _OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    _OUT_JSON.write_text(json.dumps(data, indent=2, ensure_ascii=True), encoding="utf-8")
    png_ok = _render_png(data, _OUT_PNG)
    print(json.dumps({
        "json_out": str(_OUT_JSON),
        "png_out": str(_OUT_PNG) if png_ok else None,
        "status": data.get("status", "ok"),
        "team_verdict": data.get("team_verdict"),
        "league": data.get("league_mean_reversion"),
    }, indent=2, ensure_ascii=True))
    return 0


def _validate(data: Dict[str, Any]) -> None:
    assert data.get("edge_claimed") is False, "edge_claimed must be False"
    assert "status" in data or "league_mean_reversion" in data, "missing core keys"
    if data.get("status") != "not_buildable":
        assert "teams" in data and isinstance(data["teams"], list), "teams list missing"


def check() -> int:
    # Self-check the math on a tiny synthetic corpus first (runnable, no DB needed).
    recs = [
        {"team": "AAA", "half_margin": 10, "second_half_margin": -4, "final_margin": 6},
        {"team": "AAA", "half_margin": 8, "second_half_margin": -2, "final_margin": 6},
        {"team": "AAA", "half_margin": -6, "second_half_margin": 9, "final_margin": 3},
        {"team": "AAA", "half_margin": -4, "second_half_margin": 7, "final_margin": 3},
    ]
    agg = _aggregate(recs)["teams"][0]
    assert agg["n_led_at_half"] == 2 and agg["n_trailed_at_half"] == 2, agg
    assert agg["placed_on_quadrant"] is True, agg
    assert agg["front_runner_2h_margin"] == -3.0, agg  # mean(-4,-2)
    assert agg["comeback_2h_margin"] == 8.0, agg       # mean(9,7)
    lg = _league_stats(recs)
    assert lg["buildable"] and lg["slope_2h_on_half"] < 0, lg  # clear mean reversion
    print("ctx_team_states math self-check OK")

    # Then verify the recorded artifact (clone-safe: DB may be absent).
    if not _DB.exists():
        verify_recorded_artifact(_OUT_JSON, _validate, "ctx_team_states")
        return 0
    assert _OUT_JSON.exists() and _OUT_JSON.stat().st_size > 0, _OUT_JSON
    _validate(json.loads(_OUT_JSON.read_text(encoding="utf-8")))
    print("OK: ctx_team_states self-check passed (local artifact validated)")
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(check() if "--check" in sys.argv else main())
