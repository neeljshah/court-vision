"""strategy_d_decompose_by_series.py - iter-20 PnL decomposition.

Re-runs iter-10's `stake_sizing_backtest.run()` to reproduce the 418-bet
Strategy D OOS ledger (BLK/FG3M/STL only @ -110, $100 flat), then enriches
each bet with playoff round + series + player_team and aggregates PnL.

Outputs:
  - Per-round table (n_bets, hit%, ROI%, PnL @ $100, MaxDD)
  - Per-series decomposition (>= 10 bets per series only)
  - Per-stat x round breakdown
  - Stability check (std dev of per-round ROI%)
  - Top 3 / bottom 3 series by ROI
  - Markdown report at vault/Reports/strategy_d_decompose_by_series.md
  - JSON dump at data/cache/strategy_d_decompose.json
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from statistics import pstdev
from typing import Dict, List, Optional, Tuple

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

from scripts import stake_sizing_backtest as ssb  # noqa: E402
from scripts.backtest_closing_lines_2024_playoffs import (  # noqa: E402
    _resolve_player_id,
    _parse_date,
    _prior_season,
)


VALIDATED_STATS = {"blk", "fg3m", "stl"}
PROFIT_RATIO_AT_M110 = ssb.PROFIT_RATIO_AT_M110  # 0.9091
GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")

REPORT_PATH = os.path.join(PROJECT_DIR, "vault", "Reports",
                           "strategy_d_decompose_by_series.md")
JSON_PATH = os.path.join(PROJECT_DIR, "data", "cache",
                         "strategy_d_decompose.json")


# Round boundary dates (NBA 2024 playoffs schedule, real dates).
# We pick non-overlapping bins by FIRST tip of each round so a bet's date
# maps to exactly one round.
#   First Round : 2024-04-20 .. 2024-05-03 (last 1st-round game 5/3)
#   Conf Semis  : 2024-05-04 .. 2024-05-19 (last semis game 5/19)
#   Conf Finals : 2024-05-20 .. 2024-05-30 (CSV stops 5/23, no Finals)
ROUND_BOUNDS: List[Tuple[str, datetime, datetime]] = [
    ("First Round", datetime(2024, 4, 20), datetime(2024, 5, 3)),
    ("Conf Semis",  datetime(2024, 5, 4),  datetime(2024, 5, 19)),
    ("Conf Finals", datetime(2024, 5, 20), datetime(2024, 5, 30)),
]


def _classify_round(date_iso: str) -> str:
    d = datetime.fromisoformat(date_iso)
    for name, lo, hi in ROUND_BOUNDS:
        if lo <= d <= hi:
            return name
    return "Unknown"


# ---------- Player-team resolver ----------

_TEAM_CACHE: Dict[Tuple[int, str], Optional[str]] = {}


def _resolve_player_team(player_id: int, date_iso: str) -> Optional[str]:
    """Return the team abbreviation for `player_id` on `date_iso`.

    Looks up the MATCHUP field for the game played on (or closest to) that date
    in the player's per-season gamelog JSON. Falls back to most-recent prior
    game's team if no exact-date match. Cached.
    """
    cache_key = (player_id, date_iso)
    if cache_key in _TEAM_CACHE:
        return _TEAM_CACHE[cache_key]
    target = datetime.fromisoformat(date_iso)
    season = ssb._season_for_date(target)
    rows: List[dict] = []
    for try_season in (season, _prior_season(season)):
        p = os.path.join(GAMELOG_DIR, f"gamelog_{player_id}_{try_season}.json")
        if not os.path.exists(p):
            continue
        try:
            games = json.load(open(p, encoding="utf-8"))
            if isinstance(games, list):
                rows.extend(games)
        except Exception:
            continue
    if not rows:
        _TEAM_CACHE[cache_key] = None
        return None
    # Build list of (date, team) for all valid rows.
    parsed: List[Tuple[datetime, str]] = []
    for g in rows:
        gd = _parse_date(g.get("GAME_DATE"))
        if gd is None:
            continue
        matchup = str(g.get("MATCHUP", "")).strip()
        if not matchup:
            continue
        team = matchup.split()[0]
        parsed.append((gd, team))
    if not parsed:
        _TEAM_CACHE[cache_key] = None
        return None
    # Exact date match first.
    for gd, tm in parsed:
        if gd.date() == target.date():
            _TEAM_CACHE[cache_key] = tm
            return tm
    # Most-recent prior game.
    prior = [(gd, tm) for gd, tm in parsed if gd < target]
    if prior:
        prior.sort(key=lambda x: x[0])
        tm = prior[-1][1]
        _TEAM_CACHE[cache_key] = tm
        return tm
    # Else nearest future.
    parsed.sort(key=lambda x: x[0])
    _TEAM_CACHE[cache_key] = parsed[0][1]
    return parsed[0][1]


def _series_key(team_a: str, team_b: str) -> str:
    """Canonical series id = sorted team pair, e.g. ('BOS','MIA') -> 'BOS-MIA'."""
    a, b = sorted([team_a, team_b])
    return f"{a}-{b}"


# ---------- Aggregation primitives ----------

def _agg(bets: List[dict]) -> Dict[str, float]:
    n = len(bets)
    if n == 0:
        return {"n": 0, "hit_pct": 0.0, "roi_pct": 0.0, "pnl": 0.0,
                "staked": 0.0, "wins": 0, "losses": 0, "pushes": 0,
                "max_dd": 0.0}
    wins = sum(1 for b in bets if b["outcome"] == "win")
    losses = sum(1 for b in bets if b["outcome"] == "loss")
    pushes = sum(1 for b in bets if b["outcome"] == "push")
    settled = wins + losses
    staked = n * 100.0
    pnl = wins * 100.0 * PROFIT_RATIO_AT_M110 - losses * 100.0
    roi = (pnl / staked) * 100.0 if staked > 0 else 0.0
    hit = (wins / settled) * 100.0 if settled > 0 else 0.0
    # Max DD = running cumulative PnL peak-to-trough (bets sorted by date)
    bsorted = sorted(bets, key=lambda x: (x["date"], x["stat"], x["player"]))
    cum, peak, dd = 0.0, 0.0, 0.0
    for b in bsorted:
        if b["outcome"] == "win":
            cum += 100.0 * PROFIT_RATIO_AT_M110
        elif b["outcome"] == "loss":
            cum -= 100.0
        peak = max(peak, cum)
        dd = min(dd, cum - peak)
    return {"n": n, "hit_pct": hit, "roi_pct": roi, "pnl": pnl,
            "staked": staked, "wins": wins, "losses": losses,
            "pushes": pushes, "max_dd": -dd}


# ---------- Main ----------

def main() -> None:
    print("\n  iter-20 Strategy D PnL decomposition")
    result = ssb.run()
    all_bets = result["bets"]

    # Strategy D filter: BLK/FG3M/STL only
    strat_d = [b for b in all_bets if b["stat"] in VALIDATED_STATS]
    print(f"\n  Total bets from stake_sizing_backtest: {len(all_bets)}")
    print(f"  Strategy D filtered (BLK/FG3M/STL): {len(strat_d)}")

    # Enrich each bet with player_team, opp_team, round, series
    # Need a name->pid map; reuse the same resolver as ssb.
    unique_players = sorted({b["player"] for b in strat_d})
    name2pid: Dict[str, Optional[int]] = {
        nm: _resolve_player_id(nm) for nm in unique_players
    }

    # Reload the canonical CSV to get opp_team + venue per bet (date,player,stat
    # is unique enough for this CSV).
    import csv
    opp_lookup: Dict[Tuple[str, str, str], Tuple[str, str]] = {}
    with open(ssb.CSV_PATH, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            key = (r["date"], r["player"], r["stat"].lower())
            opp_lookup[key] = (r["opp"], r["venue"])

    enriched = []
    missing_team = 0
    for b in strat_d:
        key = (b["date"], b["player"], b["stat"])
        opp, venue = opp_lookup.get(key, ("?", "?"))
        pid = name2pid.get(b["player"])
        team = _resolve_player_team(pid, b["date"]) if pid is not None else None
        if team is None:
            missing_team += 1
            team = "UNK"
        round_name = _classify_round(b["date"])
        series = _series_key(team, opp)
        enriched.append({**b, "player_team": team, "opp_team": opp,
                         "venue": venue, "round": round_name,
                         "series": series})
    print(f"  enriched {len(enriched)} bets; missing_team={missing_team}")

    # ---------- Per-round table ----------
    rounds: Dict[str, List[dict]] = defaultdict(list)
    for b in enriched:
        rounds[b["round"]].append(b)
    per_round_agg = {rn: _agg(bs) for rn, bs in rounds.items()}
    total_agg = _agg(enriched)

    print("\n  PER-ROUND TABLE")
    print(f"  {'Round':<14} {'n_bets':>7} {'hit%':>8} {'ROI%':>8} "
          f"{'PnL':>10} {'MaxDD':>10}")
    for rn in ["First Round", "Conf Semis", "Conf Finals", "Unknown"]:
        if rn not in per_round_agg:
            continue
        a = per_round_agg[rn]
        if a["n"] == 0:
            continue
        print(f"  {rn:<14} {a['n']:>7} {a['hit_pct']:>7.2f}% "
              f"{a['roi_pct']:>+7.2f}% ${a['pnl']:>+9,.0f} "
              f"${a['max_dd']:>9,.0f}")
    a = total_agg
    print(f"  {'TOTAL':<14} {a['n']:>7} {a['hit_pct']:>7.2f}% "
          f"{a['roi_pct']:>+7.2f}% ${a['pnl']:>+9,.0f} "
          f"${a['max_dd']:>9,.0f}")

    # ---------- Per-series decomposition ----------
    series_buckets: Dict[str, List[dict]] = defaultdict(list)
    for b in enriched:
        series_buckets[b["series"]].append(b)
    series_agg = {sk: _agg(bs) for sk, bs in series_buckets.items() if len(bs) >= 10}
    series_sorted = sorted(series_agg.items(), key=lambda kv: kv[1]["roi_pct"],
                            reverse=True)

    print("\n  PER-SERIES (>=10 bets)")
    print(f"  {'Series':<14} {'n':>5} {'hit%':>8} {'ROI%':>8} {'PnL':>10}")
    for sk, a in series_sorted:
        # Determine which round the series belongs to (by majority).
        rnds = [b["round"] for b in series_buckets[sk]]
        round_for_series = max(set(rnds), key=rnds.count) if rnds else "?"
        print(f"  {sk:<14} {a['n']:>5} {a['hit_pct']:>7.2f}% "
              f"{a['roi_pct']:>+7.2f}% ${a['pnl']:>+9,.0f}  [{round_for_series}]")

    # ---------- Per-stat x round breakdown ----------
    print("\n  PER-STAT x ROUND")
    print(f"  {'Stat':<6} {'Round':<14} {'n':>5} {'hit%':>8} {'ROI%':>8}")
    stat_round: Dict[Tuple[str, str], List[dict]] = defaultdict(list)
    for b in enriched:
        stat_round[(b["stat"], b["round"])].append(b)
    per_stat_round_agg: Dict[str, dict] = {}
    for (stat, rn), bs in sorted(stat_round.items()):
        a = _agg(bs)
        per_stat_round_agg[f"{stat}|{rn}"] = a
        print(f"  {stat:<6} {rn:<14} {a['n']:>5} {a['hit_pct']:>7.2f}% "
              f"{a['roi_pct']:>+7.2f}%")

    # ---------- Stability ----------
    valid_round_rois = [per_round_agg[rn]["roi_pct"]
                        for rn in ["First Round", "Conf Semis", "Conf Finals"]
                        if rn in per_round_agg and per_round_agg[rn]["n"] > 0]
    roi_std = pstdev(valid_round_rois) if len(valid_round_rois) >= 2 else 0.0
    roi_spread = (max(valid_round_rois) - min(valid_round_rois)
                  if valid_round_rois else 0.0)

    if roi_std < 10.0:
        verdict = "STABLE — edge is consistent across rounds"
    elif roi_std < 20.0:
        verdict = "MODERATELY STABLE — some round-to-round variance"
    else:
        verdict = "ROUND-DEPENDENT — edge is concentrated; +28.80% may not extrapolate"

    print(f"\n  Std-dev of per-round ROI%: {roi_std:.2f}pp")
    print(f"  Spread (max-min): {roi_spread:.2f}pp")
    print(f"  Verdict: {verdict}")

    # ---------- Top 3 / Bottom 3 series ----------
    top3 = series_sorted[:3]
    bot3 = series_sorted[-3:][::-1]
    print("\n  TOP 3 series by ROI:")
    for sk, a in top3:
        print(f"    {sk:<14} n={a['n']:>3} hit={a['hit_pct']:.2f}% "
              f"ROI={a['roi_pct']:+.2f}% PnL=${a['pnl']:+,.0f}")
    print("  BOTTOM 3 series by ROI:")
    for sk, a in bot3:
        print(f"    {sk:<14} n={a['n']:>3} hit={a['hit_pct']:.2f}% "
              f"ROI={a['roi_pct']:+.2f}% PnL=${a['pnl']:+,.0f}")

    # ---------- Save outputs ----------
    out_json = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "total": total_agg,
        "per_round": per_round_agg,
        "per_series_min10": {k: v for k, v in series_agg.items()},
        "per_stat_round": per_stat_round_agg,
        "roi_std_pp": roi_std,
        "roi_spread_pp": roi_spread,
        "verdict": verdict,
        "missing_team_count": missing_team,
        "n_total_bets": len(enriched),
    }
    os.makedirs(os.path.dirname(JSON_PATH), exist_ok=True)
    with open(JSON_PATH, "w", encoding="utf-8") as fh:
        json.dump(out_json, fh, indent=2)
    print(f"\n  json -> {JSON_PATH}")

    # Markdown
    L: List[str] = []
    L.append("# Strategy D PnL Decomposition by Series — iter-20\n")
    L.append(f"Source: re-run of `stake_sizing_backtest.run()` (iter-10), filtered "
             f"to BLK/FG3M/STL @ $100 flat, -110, |edge|>0.5.\n")
    L.append(f"- Total Strategy D bets: **{total_agg['n']}** "
             f"(wins={total_agg['wins']}, losses={total_agg['losses']}, "
             f"pushes={total_agg['pushes']})")
    L.append(f"- Total PnL: **${total_agg['pnl']:+,.0f}** "
             f"on ${total_agg['staked']:,.0f} staked → "
             f"**{total_agg['roi_pct']:+.2f}%** ROI")
    L.append(f"- Hit%: **{total_agg['hit_pct']:.2f}%** "
             f"(MaxDD ${total_agg['max_dd']:,.0f})\n")

    L.append("## Per-round table")
    L.append("| Round | n_bets | hit% | ROI% | PnL @ $100 | MaxDD |")
    L.append("|-------|------:|----:|----:|---------:|-----:|")
    for rn in ["First Round", "Conf Semis", "Conf Finals", "Unknown"]:
        if rn not in per_round_agg or per_round_agg[rn]["n"] == 0:
            continue
        a = per_round_agg[rn]
        L.append(f"| {rn} | {a['n']} | {a['hit_pct']:.2f}% | "
                 f"{a['roi_pct']:+.2f}% | ${a['pnl']:+,.0f} | "
                 f"${a['max_dd']:,.0f} |")
    L.append(f"| **TOTAL** | **{total_agg['n']}** | "
             f"**{total_agg['hit_pct']:.2f}%** | "
             f"**{total_agg['roi_pct']:+.2f}%** | "
             f"**${total_agg['pnl']:+,.0f}** | "
             f"**${total_agg['max_dd']:,.0f}** |")
    L.append("")

    L.append("## Per-series decomposition (>= 10 bets)")
    L.append("| Series | Round (majority) | n | hit% | ROI% | PnL |")
    L.append("|--------|:------------------|--:|----:|----:|----:|")
    for sk, a in series_sorted:
        rnds = [b["round"] for b in series_buckets[sk]]
        round_for_series = max(set(rnds), key=rnds.count) if rnds else "?"
        L.append(f"| {sk} | {round_for_series} | {a['n']} | "
                 f"{a['hit_pct']:.2f}% | {a['roi_pct']:+.2f}% | "
                 f"${a['pnl']:+,.0f} |")
    L.append("")

    L.append("## Per-stat x round breakdown")
    L.append("| Stat | Round | n_bets | hit% | ROI% |")
    L.append("|------|-------|------:|----:|----:|")
    for (stat, rn), bs in sorted(stat_round.items()):
        a = _agg(bs)
        L.append(f"| {stat.upper()} | {rn} | {a['n']} | "
                 f"{a['hit_pct']:.2f}% | {a['roi_pct']:+.2f}% |")
    L.append("")

    L.append("## Stability check")
    L.append(f"- Std-dev of per-round ROI%: **{roi_std:.2f}pp**")
    L.append(f"- Spread (max-min ROI%): **{roi_spread:.2f}pp**")
    L.append(f"- Verdict: **{verdict}**\n")

    L.append("## Top / Bottom 3 series by ROI")
    L.append("**Top 3 (where Strategy D minted money):**")
    for sk, a in top3:
        L.append(f"- {sk}: n={a['n']}, hit={a['hit_pct']:.2f}%, "
                 f"ROI={a['roi_pct']:+.2f}%, PnL=${a['pnl']:+,.0f}")
    L.append("\n**Bottom 3 (where it underperformed):**")
    for sk, a in bot3:
        L.append(f"- {sk}: n={a['n']}, hit={a['hit_pct']:.2f}%, "
                 f"ROI={a['roi_pct']:+.2f}%, PnL=${a['pnl']:+,.0f}")
    L.append("")

    L.append("## Quirks")
    L.append("- 2024 Finals (5/30 - 6/17) are NOT in the canonical CSV "
             "(stops 5/23), so the 'Conf Finals' bin here is the conference "
             "finals games only.")
    L.append("- Round date bins are non-overlapping by first-tip; a few "
             "potential overlap days resolved to the earlier round.")
    L.append("- Series 'majority round' resolves the rare case where a series "
             "spans the bin boundary.")
    L.append(f"- Missing player_team resolutions: {missing_team}")
    L.append("- MaxDD per-round is computed on that round's cumulative curve "
             "only (not the global curve).")
    L.append("")

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    print(f"  report -> {REPORT_PATH}")


if __name__ == "__main__":
    main()
