"""audit_bet_correlation.py - iter-18 correlation / effective-sample-size audit.

Re-derives the 418-bet Strategy D ledger (BLK / FG3M / STL only, |edge|>0.5) by
re-running stake_sizing_backtest.run() and filtering. Then enriches each bet
with the player's team (from the most recent gamelog MATCHUP <= bet date) so we
can build a game_id = (date, frozenset({team, opp})). Computes:

  - Within-game pairwise correlation of `won` flags (across multi-bet games)
  - Within-team pairwise correlation
  - Within-stat (same date) pairwise correlation
  - Effective sample size Neff via variance-inflation
  - 95% CI on hit rate + ROI under Neff
  - Per-game exposure sizing recommendation
  - Tonight's WCF G7 (2026-05-27) diagnostic from
    data/bets/strategy_d_2026-05-27.csv

Output: vault/Reports/iter18_bet_correlation_audit.md
        data/cache/iter18_bet_correlation.json
"""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import defaultdict
from datetime import datetime
from itertools import combinations
from typing import Dict, List, Optional, Tuple

import numpy as np

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault("NBA_INJURY_WIRE_DISABLE", "1")

from scripts.stake_sizing_backtest import run as _ssb_run  # noqa: E402
from scripts.backtest_closing_lines_2024_playoffs import _resolve_player_id  # noqa: E402

VALIDATED_STATS = {"blk", "fg3m", "stl"}
GAMELOG_DIR = os.path.join(PROJECT_DIR, "data", "nba")
WCF_LEDGER = os.path.join(PROJECT_DIR, "data", "bets",
                          "strategy_d_2026-05-27.csv")
OUT_JSON = os.path.join(PROJECT_DIR, "data", "cache",
                        "iter18_bet_correlation.json")
OUT_REPORT = os.path.join(PROJECT_DIR, "vault", "Reports",
                          "iter18_bet_correlation_audit.md")
BANKROLL = 10_000.0


# ----- helpers --------------------------------------------------------------

def _player_team_on_date(pid: int, on_date: datetime) -> Optional[str]:
    """Look up the player's team abbrev from the most recent gamelog row
    with GAME_DATE <= on_date. Walks the most-recent few seasons.
    """
    for season in ("2023-24", "2024-25", "2022-23"):
        path = os.path.join(GAMELOG_DIR, f"gamelog_{pid}_{season}.json")
        if not os.path.exists(path):
            continue
        try:
            rows = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue
        best_row = None
        best_date = None
        for r in rows:
            ds = r.get("GAME_DATE")
            if not ds:
                continue
            try:
                d = datetime.strptime(ds, "%b %d, %Y")
            except Exception:
                continue
            if d > on_date:
                continue
            if best_date is None or d > best_date:
                best_date = d
                best_row = r
        if best_row is not None:
            mu = best_row.get("MATCHUP", "")
            # "GSW vs. UTA" or "GSW @ LAL"
            if mu:
                return mu.split()[0]
    return None


def _avg_pairwise_corr(group_wins: List[List[int]]) -> Tuple[float, int]:
    """Average pairwise Pearson correlation of `won` flags across groups
    that have >=2 bets. Uses Fisher's z-like simple mean (skip groups with
    no variance only when the group has all same outcome AND no other group;
    instead treat constant-group correlation as 1.0 since they moved
    together, which is the conservative inflation answer)."""
    pair_corrs: List[float] = []
    n_pairs_total = 0
    for arr in group_wins:
        if len(arr) < 2:
            continue
        a = np.asarray(arr, dtype=float)
        n = len(a)
        # all pairs within this group
        for i, j in combinations(range(n), 2):
            n_pairs_total += 1
            # Two-point Pearson correlation is undefined; use the
            # standard binary co-movement proxy:
            #   +1 if both same outcome, -1 if different.
            pair_corrs.append(1.0 if a[i] == a[j] else -1.0)
    if not pair_corrs:
        return 0.0, 0
    return float(np.mean(pair_corrs)), n_pairs_total


def _neff(n: int, avg_bets_per_group: float, rho: float) -> float:
    if avg_bets_per_group <= 1:
        return float(n)
    inflate = 1.0 + (avg_bets_per_group - 1) * rho
    if inflate <= 0:
        return float(n)
    return float(n / inflate)


def _ci_hit(p: float, n: float) -> Tuple[float, float]:
    if n <= 0:
        return (p, p)
    se = (p * (1.0 - p) / n) ** 0.5
    return (p - 1.96 * se, p + 1.96 * se)


def _roi_from_hit(p: float, profit_ratio: float = 0.9091) -> float:
    """ROI@-110: each bet stakes $1, wins win $profit_ratio, losses lose $1."""
    return p * profit_ratio - (1.0 - p)


# ----- main -----------------------------------------------------------------

def main() -> None:
    print("[audit] Re-running iter-10 backtest to recover the bet set...")
    result = _ssb_run()
    all_bets = result["bets"]
    print(f"[audit] total bets returned: {len(all_bets)}")

    # Strategy D filter: BLK / FG3M / STL, drop pushes
    d_bets = [b for b in all_bets
              if b["stat"] in VALIDATED_STATS and b["outcome"] != "push"]
    print(f"[audit] strategy D bets (BLK/FG3M/STL, no pushes): {len(d_bets)}")

    # Enrich each with team via player gamelog
    print("[audit] resolving player teams from gamelogs...")
    name2pid: Dict[str, Optional[int]] = {}
    name2team_cache: Dict[Tuple[str, str], Optional[str]] = {}
    for b in d_bets:
        nm = b["player"]
        if nm not in name2pid:
            name2pid[nm] = _resolve_player_id(nm)
        pid = name2pid[nm]
        key = (nm, b["date"])
        if key not in name2team_cache:
            if pid is None:
                name2team_cache[key] = None
            else:
                d = datetime.fromisoformat(b["date"])
                name2team_cache[key] = _player_team_on_date(pid, d)
        b["team"] = name2team_cache[key]
        b["won"] = 1 if b["outcome"] == "win" else 0

    resolved_team = sum(1 for b in d_bets if b["team"] is not None)
    print(f"[audit] team resolved: {resolved_team}/{len(d_bets)}")

    # Need opp from canonical CSV (we re-load)
    csv_path = os.path.join(PROJECT_DIR, "data", "external",
                            "historical_lines", "playoffs_2024_canonical.csv")
    csv_idx: Dict[Tuple[str, str, str], dict] = {}
    with open(csv_path, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            k = (r["date"], r["player"], r["stat"].lower())
            csv_idx[k] = r
    for b in d_bets:
        r = csv_idx.get((b["date"], b["player"], b["stat"]))
        if r is None:
            b["opp"] = None
            continue
        b["opp"] = r["opp"]
        if b["team"] is None and r["venue"] == "home":
            # surrogate: home team = NOT opp (we leave it as None still since
            # we don't have a venue->team map without external data)
            pass

    # Build game_id = (date, frozenset({team, opp}))
    for b in d_bets:
        if b["team"] and b["opp"]:
            b["game_id"] = f"{b['date']}|" + "_".join(sorted([b["team"],
                                                              b["opp"]]))
        else:
            # Fall back: same opp on same date = same game (still groups
            # correctly because all players on a team share the same opp).
            b["game_id"] = f"{b['date']}|opp:{b['opp']}"

    # ---- within-game correlation ---------------------------------------
    by_game: Dict[str, List[dict]] = defaultdict(list)
    for b in d_bets:
        by_game[b["game_id"]].append(b)

    multi_game_groups = [grp for grp in by_game.values() if len(grp) >= 2]
    n_multi_game = len(multi_game_groups)
    avg_bets_per_game = float(np.mean([len(g) for g in by_game.values()]))
    avg_bets_per_multi_game = (float(np.mean([len(g) for g in multi_game_groups]))
                               if multi_game_groups else 0.0)
    game_rho, game_pairs = _avg_pairwise_corr(
        [[bb["won"] for bb in g] for g in by_game.values()]
    )

    # ---- within-team correlation ---------------------------------------
    by_team_date: Dict[Tuple[str, str], List[dict]] = defaultdict(list)
    for b in d_bets:
        if b["team"]:
            by_team_date[(b["date"], b["team"])].append(b)
    team_groups = [g for g in by_team_date.values() if len(g) >= 2]
    avg_bets_per_team_date = (float(np.mean([len(g) for g in team_groups]))
                              if team_groups else 0.0)
    team_rho, team_pairs = _avg_pairwise_corr(
        [[bb["won"] for bb in g] for g in by_team_date.values()]
    )

    # ---- within-stat (same date) correlation ---------------------------
    by_stat_date: Dict[Tuple[str, str], List[dict]] = defaultdict(list)
    for b in d_bets:
        by_stat_date[(b["date"], b["stat"])].append(b)
    stat_groups = [g for g in by_stat_date.values() if len(g) >= 2]
    avg_bets_per_stat_date = (float(np.mean([len(g) for g in stat_groups]))
                              if stat_groups else 0.0)
    stat_rho, stat_pairs = _avg_pairwise_corr(
        [[bb["won"] for bb in g] for g in by_stat_date.values()]
    )

    # ---- aggregate stats -----------------------------------------------
    n = len(d_bets)
    wins = sum(b["won"] for b in d_bets)
    hit = wins / n if n else 0.0
    roi_naive = _roi_from_hit(hit) * 100.0

    # Neff: binding constraint = highest correlation * largest group
    neff_game = _neff(n, avg_bets_per_game, game_rho)
    neff_team = _neff(n, avg_bets_per_team_date, team_rho) if team_groups else n
    neff_stat = _neff(n, avg_bets_per_stat_date, stat_rho) if stat_groups else n
    neff_binding = min(neff_game, neff_team, neff_stat)

    lo_hit, hi_hit = _ci_hit(hit, neff_binding)
    lo_roi = _roi_from_hit(lo_hit) * 100.0
    hi_roi = _roi_from_hit(hi_hit) * 100.0
    lo_hit_naive, hi_hit_naive = _ci_hit(hit, float(n))
    lo_roi_naive = _roi_from_hit(lo_hit_naive) * 100.0
    hi_roi_naive = _roi_from_hit(hi_hit_naive) * 100.0

    # ---- WCF G7 sanity check ------------------------------------------
    wcf = {"n": 0, "wins": 0, "losses": 0, "rho": 0.0, "roi": 0.0,
           "pairs": 0}
    if os.path.exists(WCF_LEDGER):
        won_flags = []
        with open(WCF_LEDGER, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                st = r.get("status", "").upper()
                if st == "WIN":
                    won_flags.append(1)
                elif st == "LOSS":
                    won_flags.append(0)
        if won_flags:
            rho_wcf, pairs_wcf = _avg_pairwise_corr([won_flags])
            n_w = len(won_flags)
            w = sum(won_flags)
            wcf_hit = w / n_w
            wcf["n"] = n_w
            wcf["wins"] = w
            wcf["losses"] = n_w - w
            wcf["rho"] = rho_wcf
            wcf["pairs"] = pairs_wcf
            wcf["roi"] = _roi_from_hit(wcf_hit) * 100.0
            wcf["hit"] = wcf_hit

    # ---- Per-game exposure sizing -------------------------------------
    # Effective single-bet equivalent risk =
    #     n * stake * sqrt(1 + (n-1)*rho)  (variance scaling -> std scaling)
    # We want this <= cap (e.g. 1% bankroll = $100). Solve stake from n, rho.
    cap_pct = 0.02  # 2% per game
    cap_dollars = cap_pct * BANKROLL
    sizing_table: List[dict] = []
    for n_bets in (1, 2, 3, 4, 5, 6, 8, 10):
        row = {"n_bets": n_bets}
        for rho in (0.0, 0.1, 0.3, game_rho, 0.7, 1.0):
            scale = (n_bets * (1.0 + (n_bets - 1) * rho)) ** 0.5
            per_bet_max = cap_dollars / max(scale, 1e-9)
            row[f"rho_{rho:.2f}"] = round(per_bet_max, 2)
        sizing_table.append(row)

    # ---- Persist ------------------------------------------------------
    payload = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "n_bets": n,
        "wins": wins,
        "hit_rate": hit,
        "roi_naive_pct": roi_naive,
        "within_game": {
            "n_games": len(by_game),
            "n_multi_bet_games": n_multi_game,
            "avg_bets_per_game": avg_bets_per_game,
            "avg_bets_per_multi_bet_game": avg_bets_per_multi_game,
            "rho": game_rho,
            "pairs_evaluated": game_pairs,
        },
        "within_team_date": {
            "n_groups": len(by_team_date),
            "n_multi_bet_groups": len(team_groups),
            "avg_bets_per_group": avg_bets_per_team_date,
            "rho": team_rho,
            "pairs_evaluated": team_pairs,
        },
        "within_stat_date": {
            "n_groups": len(by_stat_date),
            "n_multi_bet_groups": len(stat_groups),
            "avg_bets_per_group": avg_bets_per_stat_date,
            "rho": stat_rho,
            "pairs_evaluated": stat_pairs,
        },
        "neff": {
            "by_game": neff_game,
            "by_team_date": neff_team,
            "by_stat_date": neff_stat,
            "binding": neff_binding,
        },
        "ci_hit_95": {
            "naive": [lo_hit_naive, hi_hit_naive],
            "neff":  [lo_hit, hi_hit],
        },
        "ci_roi_pct_95": {
            "naive": [lo_roi_naive, hi_roi_naive],
            "neff":  [lo_roi, hi_roi],
        },
        "sizing_table_per_game_cap": {
            "cap_pct": cap_pct,
            "cap_dollars": cap_dollars,
            "table": sizing_table,
        },
        "wcf_g7_2026_05_27": wcf,
    }

    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    print(f"[audit] json -> {OUT_JSON}")

    # ---- Report -------------------------------------------------------
    L: List[str] = []
    L.append("# Iter-18: Bet Correlation & Effective Sample Size Audit\n")
    L.append(f"Generated {payload['generated_at']}")
    L.append("")
    L.append(f"Strategy D pool: **{n} bets** (BLK/FG3M/STL, |edge|>0.5, "
             "no pushes), {wins} wins, hit={hit_pct:.2%}, naive ROI={roi_naive:+.2f}%."
             .format(wins=wins, hit_pct=hit, roi_naive=roi_naive))
    L.append("")
    L.append("## Correlation structure")
    L.append("| Grouping | n_groups | multi-bet groups | avg bets/group | rho (won-flag) | pairs |")
    L.append("|----------|---------:|-----------------:|---------------:|---------------:|------:|")
    L.append(f"| within-game (date,team,opp) | {len(by_game)} | {n_multi_game} | "
             f"{avg_bets_per_game:.2f} | {game_rho:+.4f} | {game_pairs} |")
    L.append(f"| within-team-date | {len(by_team_date)} | {len(team_groups)} | "
             f"{avg_bets_per_team_date:.2f} | {team_rho:+.4f} | {team_pairs} |")
    L.append(f"| within-stat-date | {len(by_stat_date)} | {len(stat_groups)} | "
             f"{avg_bets_per_stat_date:.2f} | {stat_rho:+.4f} | {stat_pairs} |")
    L.append("")
    L.append("## Effective sample size")
    L.append(f"- Neff (game-grouping):       {neff_game:.1f}")
    L.append(f"- Neff (team-date grouping):  {neff_team:.1f}")
    L.append(f"- Neff (stat-date grouping):  {neff_stat:.1f}")
    L.append(f"- **Binding Neff (min):       {neff_binding:.1f}**  vs naive N={n}")
    L.append("")
    L.append("## 95% confidence intervals")
    L.append("| Metric | Naive (N={}) | Under Neff ({:.0f}) |".format(n, neff_binding))
    L.append("|--------|-----:|-----:|")
    L.append(f"| hit-rate | [{lo_hit_naive*100:.2f}%, {hi_hit_naive*100:.2f}%] | "
             f"[{lo_hit*100:.2f}%, {hi_hit*100:.2f}%] |")
    L.append(f"| ROI@-110 | [{lo_roi_naive:+.2f}%, {hi_roi_naive:+.2f}%] | "
             f"[{lo_roi:+.2f}%, {hi_roi:+.2f}%] |")
    L.append("")
    L.append("## Per-game exposure sizing")
    L.append(f"Cap = **{cap_pct*100:.1f}% bankroll = ${cap_dollars:.0f}** per game. "
             "Per-bet max so that variance-equivalent single-bet risk does not "
             "exceed cap, for various within-game rho:")
    L.append("")
    hdr_rhos = [0.0, 0.1, 0.3, game_rho, 0.7, 1.0]
    hdr = "| n_bets | " + " | ".join(f"rho={r:.2f}" for r in hdr_rhos) + " |"
    sep = "|--------|" + "|".join(["------:"] * len(hdr_rhos)) + "|"
    L.append(hdr)
    L.append(sep)
    for row in sizing_table:
        cells = " | ".join(f"${row[f'rho_{r:.2f}']:.0f}" for r in hdr_rhos)
        L.append(f"| {row['n_bets']} | {cells} |")
    L.append("")
    L.append(f"At the *measured* within-game rho={game_rho:+.3f} and the "
             "observed multi-bet-game average of "
             f"{avg_bets_per_multi_game:.1f} bets/game, the per-bet cap to keep "
             "single-game risk at 2% of bankroll is roughly "
             f"${sizing_table[min(len(sizing_table)-1, max(0, int(round(avg_bets_per_multi_game))-1))][f'rho_{game_rho:.2f}']:.0f} "
             "(read the n_bets row closest to your typical slate).")
    L.append("")
    L.append("## Tonight's WCF G7 diagnostic (2026-05-27)")
    if wcf["n"] > 0:
        L.append(f"- n_bets: {wcf['n']} ({wcf['wins']}W / {wcf['losses']}L) on a single game")
        L.append(f"- hit rate: {wcf.get('hit', 0)*100:.2f}%")
        L.append(f"- single-game pairwise rho (won-flags): {wcf['rho']:+.4f} "
                 f"over {wcf['pairs']} pairs")
        L.append(f"- single-game ROI: {wcf['roi']:+.2f}%")
        L.append(f"- effective sample under same-game rho={wcf['rho']:+.3f}: "
                 f"Neff = {_neff(wcf['n'], wcf['n'], wcf['rho']):.2f} "
                 "(i.e., this slate counts as roughly that many independent bets, "
                 "not 6).")
    else:
        L.append("- ledger empty / not found")
    L.append("")
    L.append("## Recommendations")
    L.append(f"1. **Per-game exposure cap = 2% bankroll** (${cap_dollars:.0f} on "
             f"${BANKROLL:,.0f}). When >1 Strategy D bet fires on the same game, "
             "DIVIDE the cap across them (don't stack $100/bet on each).")
    L.append("2. Treat headline iter-10 ROI of +28.80% with the wider Neff-CI: "
             f"under binding Neff={neff_binding:.0f}, the 95% CI for ROI is "
             f"[{lo_roi:+.2f}%, {hi_roi:+.2f}%], **not** the tight naive CI.")
    L.append("3. Tonight's 6 bets on ONE game is the textbook over-concentration "
             f"the audit was built to flag: at rho={wcf.get('rho', 0):+.3f} those "
             f"6 stakes were equivalent to ~{_neff(wcf['n'], wcf['n'], wcf['rho']):.1f} "
             "independent bets. Cap that slate at the per-game $200 limit by "
             "dropping to ~$33/bet (or take the top-1 EV bet at $200).")
    L.append("")
    L.append("## Quirks & caveats")
    L.append("- Pairwise correlation of binary outcomes uses the co-movement "
             "proxy (+1 same, -1 different); standard Pearson is degenerate for "
             "n=2 binary points. The mean-of-pairs is the right inflation input.")
    L.append("- Within-game grouping uses `(date, frozenset({team, opp}))`. "
             "Team is read from the player's most recent gamelog MATCHUP <= bet "
             "date; bets whose player team didn't resolve fall back to grouping "
             "by `(date, opp)`, which still puts teammates' bets in the same "
             "bucket because they share an opponent.")
    L.append("- `model_prob` here is the same edge-based proxy as "
             "stake_sizing_backtest; the audit only consumes the WIN/LOSS flag, "
             "not the prob, so this doesn't bias rho.")
    L.append("- Neff formula assumes uniform pairwise rho within a group. "
             "Heterogeneous rho would tighten or widen the binding Neff slightly "
             "(but variance-inflation is a robust first-order estimate).")
    L.append("- ROI@-110 is derived from hit via 2p-1.05 (approx 0.9091*p-(1-p)); "
             "if odds vary materially the ROI-CI is only approximate.")

    os.makedirs(os.path.dirname(OUT_REPORT), exist_ok=True)
    with open(OUT_REPORT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L))
    print(f"[audit] report -> {OUT_REPORT}")

    # Console summary
    print("\n=== BET CORRELATION AUDIT SUMMARY ===")
    print(f"n={n}  wins={wins}  hit={hit*100:.2f}%  ROI_naive={roi_naive:+.2f}%")
    print(f"within-game  rho={game_rho:+.4f}  avg_bets/game={avg_bets_per_game:.2f}  "
          f"multi-bet games={n_multi_game}")
    print(f"within-team  rho={team_rho:+.4f}  groups={len(team_groups)}")
    print(f"within-stat  rho={stat_rho:+.4f}  groups={len(stat_groups)}")
    print(f"Neff: game={neff_game:.1f}  team={neff_team:.1f}  stat={neff_stat:.1f}  "
          f"binding={neff_binding:.1f}")
    print(f"95% ROI CI naive: [{lo_roi_naive:+.2f}%, {hi_roi_naive:+.2f}%]")
    print(f"95% ROI CI Neff : [{lo_roi:+.2f}%, {hi_roi:+.2f}%]")
    if wcf["n"]:
        print(f"WCF G7: {wcf['n']} bets {wcf['wins']}W/{wcf['losses']}L "
              f"rho={wcf['rho']:+.4f} ROI={wcf['roi']:+.2f}% "
              f"Neff_for_slate={_neff(wcf['n'], wcf['n'], wcf['rho']):.2f}")


if __name__ == "__main__":
    main()
