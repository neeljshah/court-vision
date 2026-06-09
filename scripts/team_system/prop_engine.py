"""PROP ENGINE — every prop the book offers, derived from ONE coherent possession sim, + breakout prediction.

The sim accumulates a full per-player box every sim (pts/reb/ast/3pm/stl/blk/tov/ftm/fga/fgm/oreb/dreb/pf,
all anchored to season×recency means). Because every prop is a function of those joint samples, ONE sim
prices the WHOLE menu coherently — singles, combos (PRA/PR/PA/RA/stocks), milestones (P(pts>=X)), and the
exotics (double-double, triple-double) — plus a BREAKOUT score = the upper-tail probability a player goes
off relative to his own expectation (who might pop tonight). Fast (reads existing samples), reactive (honors
same-day availability), usable (folds a full prop sheet + breakout watch into the War Room).

  python scripts/team_system/prop_engine.py --home NYK --away SAS --nsims 20000 [--asof YYYY-MM-DD]
"""
from __future__ import annotations
import argparse, os, re, sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"))
from sim.basketball_sim import TeamModel  # noqa: E402
from sim.fast_sim import simulate_game_fast  # noqa: E402
from availability import out_ids_for  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PREVIEW = os.path.join(ROOT, "vault", "Intelligence", "Previews", "NYK_SAS_Finals_WarRoom.md")
ASC = lambda s: str(s).encode("ascii", "replace").decode()

# the full single-stat menu + the combos every book lists
SINGLES = ["pts", "reb", "ast", "fg3m", "stl", "blk", "tov", "ftm", "fga", "fgm", "oreb", "dreb", "pf"]
LABEL = {"fg3m": "3PM", "ftm": "FTM", "fga": "FGA", "fgm": "FGM", "oreb": "OREB", "dreb": "DREB", "pf": "PF",
         "stl": "STL", "blk": "BLK", "tov": "TOV", "pts": "PTS", "reb": "REB", "ast": "AST"}
# common milestone lines per stat (book "X+" markets)
MILESTONES = {"pts": [10, 15, 20, 25, 30, 35], "reb": [6, 8, 10, 12], "ast": [4, 6, 8, 10],
              "fg3m": [1, 2, 3, 4, 5], "stl": [1, 2, 3], "blk": [1, 2, 3], "pra": [20, 30, 40, 50]}


def _combos(s):
    """Derive every combo prop from the joint per-sim samples (correlation preserved by the shared sim)."""
    return {"pra": s["pts"] + s["reb"] + s["ast"], "pr": s["pts"] + s["reb"], "pa": s["pts"] + s["ast"],
            "ra": s["reb"] + s["ast"], "stocks": s["stl"] + s["blk"], "pts": s["pts"], "reb": s["reb"],
            "ast": s["ast"], **{k: s[k] for k in SINGLES}}


def _qline(x):
    """A book-style line = the median snapped to .5 (the fair line; book shades around it)."""
    return round(float(np.quantile(x, 0.5)) * 2) / 2


def player_props(d):
    """The full prop universe for one player from his joint samples."""
    s = {k: np.asarray(v, float) for k, v in d["samples"].items()}
    c = _combos(s)
    out = {}
    for k, arr in c.items():
        out[k] = dict(mean=float(arr.mean()), q10=float(np.quantile(arr, .1)),
                      q50=float(np.quantile(arr, .5)), q90=float(np.quantile(arr, .9)),
                      ceiling=float(np.quantile(arr, .95)), line=_qline(arr))
    # milestone hit-probabilities (book "X+" markets)
    mil = {}
    for stat, lines in MILESTONES.items():
        arr = c[stat]
        mil[stat] = {x: float((arr >= x).mean()) for x in lines}
    # exotics: double-double / triple-double from pts/reb/ast
    cnt = (s["pts"] >= 10).astype(int) + (s["reb"] >= 10).astype(int) + (s["ast"] >= 10).astype(int)
    out["dd"] = {"prob": float((cnt >= 2).mean())}
    out["td"] = {"prob": float((cnt >= 3).mean())}
    out["milestones"] = mil
    # BREAKOUT: probability of a genuinely BIG night on an ABSOLUTE scale (a self-relative mean+1.5sd
    # threshold is ~the same tail % for everyone -> useless). p20 differentiates role players (a 20-pt
    # game is a real pop for a 10-median guy, routine for a star); for stars the "pop" is the 30/35 ceiling.
    med = float(np.quantile(s["pts"], .5)); q95 = float(np.quantile(s["pts"], .95))
    p20 = float((s["pts"] >= 20).mean()); p30 = float((s["pts"] >= 30).mean())
    thr = max(20.0, round(1.5 * med))                   # a clearly-big night for THIS player
    out["breakout"] = dict(prob=float((s["pts"] >= thr).mean()), thr=thr, p20=p20, p30=p30,
                           ceiling=q95, upside=q95 - med)
    out["_med_pts"] = med
    return out


def run(home_tri, away_tri, nsims, asof, no_avail):
    oh = set() if no_avail else out_ids_for(home_tri, asof)
    oa = set() if no_avail else out_ids_for(away_tri, asof)
    home = TeamModel.from_cache(home_tri, out_ids=oh)
    away = TeamModel.from_cache(away_tri, out_ids=oa)
    res = simulate_game_fast(home, away, n_sims=nsims, seed=2026, anchor=True, defense=True,
                             context={"neutral_site": False})
    return res


def archetype_breakout(props, res):
    """Archetype-level breakout propensity: which roles carry the fattest upside tonight."""
    import pandas as pd
    try:
        roles = pd.read_parquet(os.path.join(ROOT, "data", "cache", "team_system",
                                              "player_roles.parquet")).set_index("pid")["archetype"].to_dict()
    except Exception:
        roles = {}
    agg = {}
    for pid, pr in props.items():
        if not (5 <= pr["_med_pts"] < 18):              # non-star rotation = where a "pop" is a surprise
            continue
        a = roles.get(pid, "UNK")
        agg.setdefault(a, []).append(pr["breakout"]["p20"])
    return sorted(((a, float(np.mean(v)), len(v)) for a, v in agg.items() if v), key=lambda x: -x[1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", default="NYK"); ap.add_argument("--away", default="SAS")
    ap.add_argument("--nsims", type=int, default=20000); ap.add_argument("--asof", default=None)
    ap.add_argument("--no-availability", action="store_true"); ap.add_argument("--no-fold", action="store_true")
    a = ap.parse_args()
    res = run(a.home, a.away, a.nsims, a.asof, a.no_availability)
    props = {pid: player_props(d) for pid, d in res.players.items()}
    names = {pid: (ASC(d["name"]), d["team"]) for pid, d in res.players.items()}
    rotation = [pid for pid in props if props[pid]["_med_pts"] >= 6]
    rotation.sort(key=lambda p: -props[p]["pts"]["q50"])

    # ---- full prop sheet ----
    print(f"=== FULL PROP UNIVERSE: {a.away} @ {a.home} ({a.nsims} sims) ===")
    hdr = f"{'player':20s} {'PTS':>4s} {'REB':>4s} {'AST':>4s} {'3PM':>4s} {'STL':>4s} {'BLK':>4s} {'PRA':>5s} {'DD%':>4s} {'BRK%':>5s}"
    print(hdr)
    for p in rotation:
        pr = props[p]; nm = names[p][0]
        print(f"{nm:20s} {pr['pts']['q50']:4.0f} {pr['reb']['q50']:4.0f} {pr['ast']['q50']:4.0f} "
              f"{pr['fg3m']['q50']:4.0f} {pr['stl']['q50']:4.1f} {pr['blk']['q50']:4.1f} "
              f"{pr['pra']['q50']:5.0f} {pr['dd']['prob']*100:4.0f} {pr['breakout']['prob']*100:5.0f}")

    # ---- breakout watch: non-stars by P(20+) = the live longshots; stars by P(30+) = ceiling games ----
    role = [p for p in rotation if props[p]["_med_pts"] < 18]
    stars = [p for p in rotation if props[p]["_med_pts"] >= 18]
    brk = sorted(role, key=lambda p: -props[p]["breakout"]["p20"])[:6]
    star_ceil = sorted(stars, key=lambda p: -props[p]["breakout"]["p30"])[:4]
    print("\n=== BREAKOUT WATCH (non-stars who might POP for 20+) ===")
    for p in brk:
        pr = props[p]
        print(f"  {names[p][0]:20s} ({names[p][1]}) P(20+) {pr['breakout']['p20']*100:4.0f}%  "
              f"median {pr['_med_pts']:.0f} -> ceiling {pr['breakout']['ceiling']:.0f} (+{pr['breakout']['upside']:.0f})")
    print("  -- star ceiling games (P 30+):", ", ".join(f"{names[p][0].split()[-1]} {props[p]['breakout']['p30']*100:.0f}%" for p in star_ceil))
    arch = archetype_breakout(props, res)
    print("\n=== ARCHETYPE breakout propensity (avg P(20+) among non-stars, this matchup) ===")
    for a_, v, n in arch[:8]:
        print(f"  {a_:16s} {v*100:4.0f}%  (n={n})")

    if a.no_fold:
        return
    _fold(props, names, rotation, brk, star_ceil, arch, a.home, a.away)


def _fold(props, names, rotation, brk, star_ceil, arch, home, away):
    L = LABEL
    t = ["<!-- SIGNALS:prop-universe START -->", "",
         f"## Prop Universe — every market from one sim ({away} @ {home})", "",
         "*One coherent GPU possession sim prices the WHOLE menu (singles, combos, milestones, double-doubles) "
         "with the correlations intact — q50 is the fair line, q90 the realistic ceiling. Honors same-day "
         "availability. Secondary stats (3PM/STL/BLK/TOV/FTM) are season-anchored; pregame playoff props "
         "stay un-bettable (closing line beats the model in playoffs) — these are projections.*", "",
         "| Player | PTS | REB | AST | 3PM | STL | BLK | TOV | PRA | DD% | TD% |",
         "|---|--|--|--|--|--|--|--|--|--|--|"]
    for p in rotation:
        pr = props[p]
        t.append(f"| {names[p][0]} | {pr['pts']['q50']:.0f} | {pr['reb']['q50']:.0f} | {pr['ast']['q50']:.0f} "
                 f"| {pr['fg3m']['q50']:.0f} | {pr['stl']['q50']:.1f} | {pr['blk']['q50']:.1f} "
                 f"| {pr['tov']['q50']:.1f} | {pr['pra']['q50']:.0f} | {pr['dd']['prob']*100:.0f} | {pr['td']['prob']*100:.0f} |")
    # milestone ladders for the stars (P of clearing each X+ market)
    t += ["", "**Milestone ladders (P of clearing the X+ market):**"]
    for p in rotation[:4]:
        m = props[p]["milestones"]["pts"]
        t.append(f"- {names[p][0]} PTS: " + " · ".join(f"{x}+ {m[x]*100:.0f}%" for x in [20, 25, 30, 35]))
    t += ["", "### Breakout Watch — who might pop tonight",
          "*The upside the median line hides. **Longshots** = non-stars by P(a 20+ point game); **ceiling games** "
          "= stars by P(30+). Role players with real ceilings are the live longshot props.*", "",
          "**Longshots (non-stars, P of a 20+ game):**"]
    for p in brk:
        pr = props[p]
        t.append(f"- **{names[p][0]}** ({names[p][1]}): P(20+) **{pr['breakout']['p20']*100:.0f}%** — "
                 f"median {pr['_med_pts']:.0f} → ceiling {pr['breakout']['ceiling']:.0f} (+{pr['breakout']['upside']:.0f})")
    t += ["", "**Star ceiling games (P of 30+):** "
          + " · ".join(f"{names[p][0]} {props[p]['breakout']['p30']*100:.0f}%" for p in star_ceil),
          "", "**Archetype breakout propensity** (avg P(20+) among non-stars this matchup): "
          + " · ".join(f"{a_} {v*100:.0f}%" for a_, v, n in arch[:6]), "", "<!-- SIGNALS:prop-universe END -->"]
    block = "\n".join(t)
    if os.path.exists(PREVIEW):
        txt = open(PREVIEW, encoding="utf-8").read()
        pat = re.compile(re.escape("<!-- SIGNALS:prop-universe START -->") + r".*?"
                         + re.escape("<!-- SIGNALS:prop-universe END -->"), re.S)
        txt = pat.sub(block, txt) if pat.search(txt) else txt.rstrip() + "\n\n" + block + "\n"
        open(PREVIEW, "w", encoding="utf-8").write(txt)
        print(f"\nfolded ## Prop Universe + Breakout Watch into {os.path.relpath(PREVIEW, ROOT)}")


if __name__ == "__main__":
    main()
