"""Lineup-proxy context conditioning: team win rate with a player ACTIVE vs
INACTIVE (played vs missed), the honest stand-in for RAPM when no stint data
exists.

RAPM is OUT OF REACH here -- we have no play-by-play stint matrix, only
player-game box rows. So this builds the crude, defensible proxy instead: for
each player who missed >= 5 of their team's games (inside their own tenure
window), compare the team's win rate in games the player was ACTIVE vs the
games they MISSED, with a Wald CI on the difference.

BINDING CONFOUND (declared on EVERY row, matches the on/off family rule):
with-vs-without is NOT a causal player-impact estimate. WHY a player misses
games is entangled with everything -- injuries cluster (other starters hurt
too), rest games are scheduled against specific opponents, blowouts pull
starters, and the replacement lineup differs. This is the classic
with/without = roster confound. DESCRIPTIVE_ONLY, edge_claimed=False.

Source: data/cache/cv_fix/leaguegamelog_regular_season.parquet
        (player-level 2025-26 regular-season game log, 1230 games).
Output: out/ctx_lineup_proxy.json + docs/img/ctx_lineup_proxy.png

Usage:
    python -m scripts.platformkit.analytics_showcase.ctx_lineup_proxy
    python -m scripts.platformkit.analytics_showcase.ctx_lineup_proxy --check
"""
from __future__ import annotations

import argparse
import json
import math
import os
from collections import Counter
from typing import Any

try:
    from scripts.platformkit.analytics_showcase._clone_safe import verify_recorded_artifact
except ImportError:  # bare-clone / direct-run fallback
    from _clone_safe import verify_recorded_artifact

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
SRC_PARQUET = os.path.join(REPO_ROOT, "data", "cache", "cv_fix", "leaguegamelog_regular_season.parquet")
OUT_JSON = os.path.join(REPO_ROOT, "scripts", "platformkit", "analytics_showcase", "out", "ctx_lineup_proxy.json")
OUT_PNG = os.path.join(REPO_ROOT, "docs", "img", "ctx_lineup_proxy.png")

MIN_MISSED = 5      # spec floor: only players who missed >= 5 team games
MIN_ACTIVE = 15     # need enough active games for a stable active-side win rate
TOP_N = 12          # rows shown per side in the forest plot
AS_OF = "2025-26 regular season (through 2026-04-12)"

CONFOUND = (
    "WITH/WITHOUT = ROSTER CONFOUND: this is NOT a causal player-impact estimate. "
    "Why a player missed games is entangled with injuries clustering, rest-game "
    "scheduling, blowout pulls, and a different replacement lineup -- none controlled "
    "for. DESCRIPTIVE_ONLY, not a predictive or edge claim."
)


def _load_rows() -> list[dict[str, Any]]:
    import pandas as pd
    cols = ["PLAYER_ID", "PLAYER_NAME", "TEAM_ID", "TEAM_ABBREVIATION", "GAME_ID", "GAME_DATE", "WL"]
    df = pd.read_parquet(SRC_PARQUET, columns=cols)
    return df.to_dict("records")


def _team_games(rows: list[dict[str, Any]]) -> dict[int, dict[str, tuple[str, bool]]]:
    """team_id -> {game_id: (game_date, won)}. WL is consistent per team-game."""
    tg: dict[int, dict[str, tuple[str, bool]]] = {}
    for r in rows:
        wl = r.get("WL")
        if wl not in ("W", "L"):
            continue
        tg.setdefault(int(r["TEAM_ID"]), {})[str(r["GAME_ID"])] = (str(r["GAME_DATE"]), wl == "W")
    return tg


def _wald_ci(pa: float, na: int, pm: float, nm: int) -> tuple[float, float]:
    """95% Wald CI half-width on (pa - pm), difference of two proportions."""
    se = math.sqrt(pa * (1.0 - pa) / na + pm * (1.0 - pm) / nm)
    half = 1.96 * se
    return round(-half, 4), round(half, 4)  # centered offsets around delta


def build() -> dict[str, Any]:
    if not os.path.exists(SRC_PARQUET):
        return {
            "status": "not_buildable",
            "reason": f"source game log absent at {os.path.relpath(SRC_PARQUET, REPO_ROOT)} "
                      "(gitignored data/, expected on a fresh clone)",
            "edge_claimed": False,
            "confound": CONFOUND,
            "players": [],
        }

    rows = _load_rows()
    team_games = _team_games(rows)

    # (player_id, team_id) -> {"name": .., "abbr": .., "active": set(gid)}
    per: dict[tuple[int, int], dict[str, Any]] = {}
    for r in rows:
        if r.get("WL") not in ("W", "L"):
            continue
        key = (int(r["PLAYER_ID"]), int(r["TEAM_ID"]))
        d = per.setdefault(key, {"names": Counter(), "abbr": str(r.get("TEAM_ABBREVIATION") or ""), "active": set()})
        d["names"][str(r.get("PLAYER_NAME") or "")] += 1
        d["active"].add(str(r["GAME_ID"]))

    results: list[dict[str, Any]] = []
    for (pid, tid), d in per.items():
        active = d["active"]
        team_all = team_games.get(tid, {})
        active_dates = [team_all[g][0] for g in active if g in team_all]
        if not active_dates:
            continue
        first, last = min(active_dates), max(active_dates)
        # tenure-window team games: bounds the trade/join confound
        tenure = {g: info for g, info in team_all.items() if first <= info[0] <= last}
        missed = set(tenure) - active
        na, nm = len(active), len(missed)
        if nm < MIN_MISSED or na < MIN_ACTIVE:
            continue
        wr_active = sum(tenure[g][1] for g in active if g in tenure) / na
        wr_missed = sum(tenure[g][1] for g in missed) / nm
        delta = wr_active - wr_missed
        ci_lo, ci_hi = _wald_ci(wr_active, na, wr_missed, nm)
        results.append({
            "player_id": pid,
            "team_id": tid,
            "team": d["abbr"],
            "player_name": d["names"].most_common(1)[0][0],
            "n_active": na,
            "n_missed": nm,
            "win_rate_active": round(wr_active, 4),
            "win_rate_missed": round(wr_missed, 4),
            "delta_win_rate": round(delta, 4),
            "ci95_offset": [ci_lo, ci_hi],
            "confound": CONFOUND,
        })

    results.sort(key=lambda x: x["delta_win_rate"], reverse=True)
    deltas = [r["delta_win_rate"] for r in results]

    return {
        "status": "ok",
        "edge_claimed": False,
        "method": "team win rate with player ACTIVE vs MISSED, inside the player's "
                  "own tenure window; Wald 95% CI on the win-rate difference. RAPM-free proxy.",
        "source_artifact": os.path.relpath(SRC_PARQUET, REPO_ROOT).replace("\\", "/"),
        "as_of": AS_OF,
        "floors": {"min_missed": MIN_MISSED, "min_active": MIN_ACTIVE},
        "confound": CONFOUND,
        "n_qualified": len(results),
        "delta_summary": {
            "n": len(deltas),
            "mean": round(sum(deltas) / len(deltas), 4) if deltas else None,
            "min": round(min(deltas), 4) if deltas else None,
            "max": round(max(deltas), 4) if deltas else None,
        },
        "top_help": results[:TOP_N],
        "top_hurt": results[-TOP_N:][::-1] if len(results) >= TOP_N else results[::-1],
        "players": results,
    }


def render_chart(res: dict[str, Any]) -> bool:
    if res.get("status") != "ok" or not res.get("players"):
        return False
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False

    top = res["top_help"]
    bot = res["top_hurt"]
    # forest: help block (green) on top, hurt block (red) below, each sorted by delta
    block = top + bot
    labels = [f"{r['player_name']} ({r['team']})" for r in block]
    deltas = [r["delta_win_rate"] for r in block]
    los = [r["ci95_offset"][0] for r in block]
    his = [r["ci95_offset"][1] for r in block]
    ns = [f"n={r['n_active']}/{r['n_missed']}" for r in block]
    colors = ["#2a9d5c"] * len(top) + ["#c0392b"] * len(bot)

    y = list(range(len(block)))
    fig, ax = plt.subplots(figsize=(9, max(4, 0.42 * len(block))))
    for yi, dv, lo, hi, c in zip(y, deltas, los, his, colors):
        ax.plot([dv + lo, dv + hi], [yi, yi], color=c, linewidth=1.4, alpha=0.7)
        ax.plot(dv, yi, "o", color=c, markersize=6)
    for yi, dv, lab in zip(y, deltas, ns):
        ax.text(1.02, yi, lab, transform=ax.get_yaxis_transform(), va="center", fontsize=7, color="#555")
    ax.axvline(0, color="black", linewidth=0.6)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=7)
    ax.invert_yaxis()
    ax.set_xlabel("team win-rate delta: ACTIVE - MISSED (95% Wald CI)", fontsize=9)
    ax.set_title("Lineup-proxy: team win rate with player active vs missed\n"
                 "WITH/WITHOUT = ROSTER CONFOUND -- descriptive only, not causal impact", fontsize=9)
    fig.text(0.01, 0.005,
             f"Source: {res['source_artifact']} | as_of {res['as_of']} | "
             f"floors: missed>={res['floors']['min_missed']}, active>={res['floors']['min_active']} | "
             "edge_claimed=False", fontsize=6, color="gray")
    fig.tight_layout(rect=(0, 0.03, 0.86, 1))
    os.makedirs(os.path.dirname(OUT_PNG), exist_ok=True)
    fig.savefig(OUT_PNG, dpi=140)
    plt.close(fig)
    return True


def run() -> dict[str, Any]:
    res = build()
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    res["plot_written"] = render_chart(res)
    with open(OUT_JSON, "w", encoding="ascii") as f:
        json.dump(res, f, indent=2)
    return res


def _validate(data: dict[str, Any]) -> None:
    assert data.get("status") in ("ok", "not_buildable"), data.get("status")
    assert data.get("edge_claimed") is False
    assert "CONFOUND" in data.get("confound", "").upper()
    if data["status"] == "ok":
        for r in data.get("players", []):
            assert r["n_missed"] >= MIN_MISSED and r["n_active"] >= MIN_ACTIVE, r
            # 3 independently-rounded-to-4dp fields: worst-case combined rounding error ~2e-4
            assert abs(r["delta_win_rate"] - (r["win_rate_active"] - r["win_rate_missed"])) < 2e-4, r
            assert "CONFOUND" in r["confound"].upper()


def check() -> None:
    if os.path.exists(SRC_PARQUET):
        res = build()
        _validate(res)
        print(f"ctx_lineup_proxy self-check OK ({res.get('status')}, n_qualified={res.get('n_qualified')})")
    else:
        verify_recorded_artifact(OUT_JSON, _validate, "ctx_lineup_proxy")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        check()
    else:
        r = run()
        print(json.dumps({
            "status": r["status"], "n_qualified": r.get("n_qualified"),
            "delta_summary": r.get("delta_summary"), "plot_written": r.get("plot_written"),
        }, indent=2))
