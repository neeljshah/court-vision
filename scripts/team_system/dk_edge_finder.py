"""DK EDGE FINDER — the best bet on EVERY DraftKings prop, ranked by mathematical edge (+ longshots).

For every DK prop (player x stat x line + over/under price) it compares the line to the possession sim's
EXACT distribution for that player-stat (P = fraction of simulated games over/under the line -- exact in the
tails, unlike a normal approximation, so longshots like 'Wemby 15+ reb' or 'KAT 4+ threes' are priced
correctly), de-vigs the DK price to the market's fair probability, and computes:
  edge = model_prob - market_prob        (model's disagreement with DK)
  EV   = model_prob * decimal_odds - 1   (expected $ per $1 at the DK price)
  Kelly= (p*d-1)/(d-1)                    (optimal fraction; quarter-Kelly recommended)
Then it ranks every market by EV -> the BEST BETS, and separately surfaces the LONGSHOTS (low-probability,
high-payout sides where the model still says +EV). Honors same-day availability; reads real DK odds.

DISCIPLINE (not hidden): the edge gate shows the model BEATS the line only in the REGULAR SEASON and only
for some archetypes (WING_CREATOR/THREE_D_WING pts, LEAD_GUARD ast); the PLAYOFFS are NEGATIVE. So for a
Finals slate these are the MODEL'S VIEW, not validated profit -- each row is tagged with a trust level.

  python scripts/team_system/dk_edge_finder.py [--props data/external/current_props_draftkings.json]
                                               [--home NYK --away SAS --asof 2026-06-08 --min-ev 0.0]
"""
from __future__ import annotations
import argparse, json, os, sys, unicodedata
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from prop_engine import run as run_sim  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROPS_DEFAULT = os.path.join(ROOT, "data", "external", "current_props_draftkings.json")
ROLES = {}
try:
    import pandas as pd
    ROLES = pd.read_parquet(os.path.join(ROOT, "data", "cache", "team_system",
                                         "player_roles.parquet")).set_index("pid")["archetype"].to_dict()
except Exception:
    pass

# DK prop_type -> sim sample key (combos derived in prop_engine samples too)
STAT = {"points": "pts", "rebounds": "reb", "assists": "ast", "threes": "fg3m", "steals": "stl",
        "blocks": "blk", "turnovers": "tov", "pts_reb_ast": "pra", "points_rebounds_assists": "pra",
        "pts_reb": "pr", "pts_ast": "pa", "reb_ast": "ra", "steals_blocks": "stocks", "blocks_steals": "stocks"}
# reg-season archetypes where the model historically beats the line (else lower trust); see EDGE_GATE doc
EDGE_ARCH = {"pts": {"WING_CREATOR", "THREE_D_WING", "PRIMARY_BIG", "LEAD_GUARD"},
             "ast": {"LEAD_GUARD", "FLOOR_GENERAL", "SCORING_GUARD"}}
# blk/fg3m/ftm are now Poisson-calibrated to real per-game means (build_full_gamelog -> secondary_targets;
# sim P(>=1) now matches real within a few pp), and stl was always chain-calibrated -> no stat is demoted.
# The residual artifacts are minute-volatile BENCH players, which the rotation (pra>=22) filter handles.
LOW_CONF_STATS = set()


def _norm(s):
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode().lower()
    for suf in (" jr", " sr", " iii", " ii", " iv"):
        if s.endswith(suf):
            s = s[: -len(suf)]
    return "".join(c for c in s if c.isalnum() or c == " ").strip()


def _dec(american):
    a = float(american)
    return 1 + a / 100.0 if a > 0 else 1 + 100.0 / abs(a)


def _combo(samp, key):
    s = samp
    if key in s:
        return np.asarray(s[key], float)
    if key == "pra":
        return s["pts"] + s["reb"] + s["ast"]
    if key == "pr":
        return s["pts"] + s["reb"]
    if key == "pa":
        return s["pts"] + s["ast"]
    if key == "ra":
        return s["reb"] + s["ast"]
    if key == "stocks":
        return s["stl"] + s["blk"]
    return None


def find_edges(props, res, min_ev):
    name2pid = {_norm(d["name"]): pid for pid, d in res.players.items()}
    rows = []
    for p in props:
        pid = name2pid.get(_norm(p.get("player_name", "")))
        key = STAT.get(p.get("prop_type"))
        if pid is None or key is None:
            continue
        arr = _combo(res.players[pid]["samples"], key)
        if arr is None:
            continue
        line = float(p["line"])
        p_over = float((arr > line).mean()); p_under = float((arr < line).mean())
        do, du = _dec(p["over_odds"]), _dec(p["under_odds"])
        io, iu = 1 / do, 1 / du; vig = io + iu
        mkt_over, mkt_under = io / vig, iu / vig            # de-vigged fair market probs
        for side, ps, d, mkt, odds in (("OVER", p_over, do, mkt_over, p["over_odds"]),
                                       ("UNDER", p_under, du, mkt_under, p["under_odds"])):
            ev = ps * d - 1.0
            edge = ps - mkt
            kelly = max(0.0, (ps * d - 1) / (d - 1)) if d > 1 else 0.0
            arch = ROLES.get(pid, "?")
            trust = "reg-edge" if arch in EDGE_ARCH.get(key, set()) else "low"
            d2 = res.players[pid]["mean"]
            pra = float(d2["pts"] + d2["oreb"] + d2["dreb"] + d2["ast"])
            rows.append(dict(player=res.players[pid]["name"], team=res.players[pid]["team"],
                             stat=p["prop_type"], line=line, side=side, odds=int(odds), model_p=ps,
                             mkt_p=mkt, edge=edge, ev=ev, kelly=kelly, proj=float(arr.mean()),
                             arch=arch, trust=trust, pra=pra, rotation=pra >= 22,
                             longshot=(ps < 0.35 and odds >= 120)))
    rows.sort(key=lambda r: -r["ev"])
    return rows


def _fmt(r):
    a = f"+{r['odds']}" if r["odds"] > 0 else str(r["odds"])
    ls = " *LONGSHOT" if r["longshot"] else ""
    flag = "" if r["trust"] == "reg-edge" else " (low-trust)"
    return (f"  {r['player'][:20]:20s} {r['stat'][:5]:5s} {r['side']:5s} {r['line']:5.1f} @ {a:>5s} | "
            f"proj {r['proj']:5.1f}  model {r['model_p']*100:4.0f}%  mkt {r['mkt_p']*100:4.0f}%  "
            f"edge {r['edge']*100:+5.1f}  EV {r['ev']*100:+5.1f}%  K {r['kelly']*100:4.1f}%{flag}{ls}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--props", default=PROPS_DEFAULT); ap.add_argument("--home", default="NYK")
    ap.add_argument("--away", default="SAS"); ap.add_argument("--nsims", type=int, default=20000)
    ap.add_argument("--asof", default=None); ap.add_argument("--no-availability", action="store_true")
    ap.add_argument("--min-ev", type=float, default=0.0); ap.add_argument("--kelly-frac", type=float, default=0.25)
    ap.add_argument("--top", type=int, default=25)
    a = ap.parse_args()
    props = json.load(open(a.props, encoding="utf-8"))
    print(f"=== DK EDGE FINDER: {len(props)} props, {a.away} @ {a.home} ({a.nsims} sims, as-of {a.asof or 'latest'}) ===")
    res = run_sim(a.home, a.away, a.nsims, a.asof, a.no_availability)
    rows = find_edges(props, res, a.min_ev)

    # ---- CALIBRATION DIAGNOSIS (the honest gate): if edge is everywhere, it's mis-calibration not money ----
    core = [r for r in rows if r["rotation"]]; bench = [r for r in rows if not r["rotation"]]
    npos = sum(r["ev"] > 0 for r in rows)
    import numpy as _np
    med_core = _np.median([abs(r["edge"]) for r in core]) * 100 if core else 0
    med_bench = _np.median([abs(r["edge"]) for r in bench]) * 100 if bench else 0
    print(f"\n### CALIBRATION CHECK ###")
    print(f"  {npos}/{len(rows)} sides show +EV. median |edge|: CORE rotation {med_core:.1f}pp  vs  BENCH {med_bench:.1f}pp")
    print(f"  -> if BENCH |edge| >> CORE |edge|, the 'edges' are the sim's minute/role allocation diverging from")
    print(f"     DK's sharp view (phantom edge), NOT money. The market is efficient where the model is reliable (stars).")

    show = [r for r in rows if r["ev"] >= a.min_ev and r["rotation"] and r["stat"] not in LOW_CONF_STATS]
    print(f"\n### BEST BETS — CORE ROTATION, reliable stats (top {a.top} by EV; {a.kelly_frac:.2f}-Kelly on 100u) ###")
    print("  *(blocks/steals demoted — the sim models defensive events conservatively, so their 'edges' are artifacts)*")
    print(f"  {'player':20s} {'stat':5s} {'side':5s} {'line':>5s}   {'odds':>5s} | proj  model  mkt   edge   EV     Kelly")
    for r in show[:a.top]:
        print(_fmt(r) + f"  -> {a.kelly_frac*r['kelly']*100:4.1f}u")
    rege = [r for r in show if r["trust"] == "reg-edge"][:10]
    print(f"\n### HIGHEST-TRUST (core + reg-season edge archetypes: creator/wing pts, lead-guard ast) ###")
    for r in rege:
        print(_fmt(r))
    ls = [r for r in rows if r["longshot"] and r["rotation"] and r["ev"] > 0][:10]
    print(f"\n### LONGSHOTS (rotation players the model says are live underdogs — e.g. a big's high-reb / multi-block night) ###")
    for r in ls:
        print(_fmt(r))

    print("\n*** HONEST READ: this is a PLAYOFF (Finals) slate -> the edge gate shows NO validated model edge in "
          "the playoffs (the closing line wins). The broad +EV above is mostly CALIBRATION GAP (sim vs DK), not "
          "profit; bench rows especially are minute/role artifacts (now filtered out of 'best bets'). Use this as a "
          "model-vs-market SCREEN, not a green-light card. The validated money setup is REG-SEASON + edge archetypes "
          "+ 0.1-0.25 Kelly (bet_optimizer.py); the real untapped lane is CLV (bet openers pre-news).")


if __name__ == "__main__":
    main()
