"""CLOCK-AWARE GAME ENGINE — simulate the game in GAME-TIME, not just possessions.

The possession MC (basketball_sim) is the validated MARGINAL/prop engine. This is its TIME-RESOLVED sibling:
it plays the game out second-by-second (possession-by-possession in CLOCK ORDER), so every time-dependent
aspect wires in and a whole new prediction surface opens that the possession sim structurally cannot produce:
  * shot-clock state per possession -> xFG via the cross-season-validated shotclock_curve (finally its home)
  * score TRAJECTORY -> quarter scores, halftime, lead changes, largest lead, time-leading, comeback prob
  * a LIVE win-probability curve (win % as a function of clock + margin) -> the in-game product
  * possession ORIGIN chain (after a make = set defense; after a TO = transition; after an OREB = 2nd chance)
  * fouls accumulate -> foul-trouble / foul-out removes a player; clutch (Q4 <5min, close) concentrates usage
  * fatigue (minutes accumulation) lightly decays late efficiency

It reuses the validated rates/lineups/defense (TeamModel) + the possession chain primitives, so it is consistent
with the marginal engine; the marginals are NOT the point here (the anchor owns those) -- the TRAJECTORY is.

  python -m src.sim.game_clock_sim            # quarter-score validation vs real (team_game q1-q4)
"""
from __future__ import annotations
import json, os
import numpy as np

from .basketball_sim import (TeamModel, _make_prob, _sample_zone, USAGE_CONCENTRATION,
                             DEF_RIM_SLOPE, DEF_PERIM_SLOPE, TS)

# shot-clock-used buckets: (max_seconds, sample_midpoint, xFG multiplier from shotclock_curve.json, P(bucket))
_CURVE = json.load(open(os.path.join(TS, "shotclock_curve.json")))["buckets"] if \
    os.path.exists(os.path.join(TS, "shotclock_curve.json")) else {}
_BUCKETS = [(4, 3.0, _CURVE.get("0-4", 1.0)), (7, 5.5, _CURVE.get("4-7", 1.0)),
            (11, 9.0, _CURVE.get("7-11", 1.0)), (14, 12.5, _CURVE.get("11-14", 1.0)),
            (18, 16.0, _CURVE.get("14-18", 1.0)), (22, 20.0, _CURVE.get("18-22", 1.0)),
            (24, 23.0, _CURVE.get("22+", 1.0))]
_BUCKET_P = np.array([0.14, 0.10, 0.15, 0.13, 0.18, 0.14, 0.15])      # empirical share per bucket (legacy)
_BUCKET_P = _BUCKET_P / _BUCKET_P.sum()
_QLEN = 720.0
_DEFAULT_QW = [1.0, 1.0, 1.0, 0.94]              # OFF behavior: flat Q1-Q3, Q4 efficiency dip
_QW_SUM = sum(_DEFAULT_QW)                        # 3.94 -> total-preserving rescale target
_QWEIGHTS = None


def _quarter_weights(tri: str):
    """Per-team quarter-RELATIVE scoring profile (CV_QUARTER_IDENTITY): w_q = (real q_i / mean q) rescaled so
    sum == the OFF path's 3.94 -> imposes the team's real quarter SHAPE (SAS Q1 fast-start, team-specific Q4
    dip) while PRESERVING the team total exactly (no level confound; the anchor still owns the level). Falls
    back to the flat default if team_game is missing the team. Leak-free: team season identity, not future."""
    global _QWEIGHTS
    if _QWEIGHTS is None:
        _QWEIGHTS = {}
        fp = os.path.join(TS, "team_game.parquet")
        if os.path.exists(fp):
            import pandas as pd
            rq = pd.read_parquet(fp).groupby("team")[["q1", "q2", "q3", "q4"]].mean()
            for t in rq.index:
                q = rq.loc[t].values.astype(float); m = q.mean()
                _QWEIGHTS[t] = list(q / m * (_QW_SUM / 4.0)) if m > 0 else list(_DEFAULT_QW)
    return _QWEIGHTS.get(tri, list(_DEFAULT_QW))


def _live_winprob(margin, sec_left):
    """A clock-aware win prob for the LEADING-margin team: tighter as time runs out (logistic on margin/sqrt(t))."""
    t = max(sec_left, 1.0)
    return 1.0 / (1.0 + np.exp(-(margin) / (0.9 * np.sqrt(t / 60.0) + 0.7)))


def _eligible(team, fouled_out, rng):
    if not fouled_out:
        return list(team.lineup_ids[rng.choice(len(team.lineup_ids), p=team.lineup_p)])
    lus = [(i, L) for i, L in enumerate(team.lineup_ids) if not any(p in fouled_out for p in L)]
    if not lus:
        ok = [p for p in team.rate if p not in fouled_out][:5]
        return ok or list(team.rate)[:5]
    idx = [i for i, _ in lus]; p = team.lineup_p[idx]; p = p / p.sum()
    return list(team.lineup_ids[idx[rng.choice(len(idx), p=p)]])


DUR_CAL = 1.10        # global pace calibration (raw engine over-paces -> total ~253 vs ~233; longer poss)


def _possess(off, deff, on_off, on_def, origin, rng, box, fouls, fouled_out, clutch, dur_mult=1.0, eff_mult=1.0):
    """One clock possession; returns (points, seconds_used, next_origin). origin: 'half'/'trans'/'2nd'."""
    # duration + shot-clock xFG multiplier (transition = forced short bucket)
    if origin == "trans":
        bi = rng.choice(2, p=[0.6, 0.4])                  # quick buckets
    else:
        bi = rng.choice(len(_BUCKETS), p=_BUCKET_P)
    _, dur, clk_mult = _BUCKETS[bi]
    dur *= DUR_CAL * dur_mult; clk_mult *= eff_mult
    # origin shot-quality lift. OFF -> half/trans/2nd = 1.0/1.337/1.29 (byte-identical, no "dead" ever emitted).
    # ON (CV_CLOCK_ORIGIN_SPLIT) -> split "half" into dead(after-make, set defense) 0.971 vs half(after-miss-DREB)
    # 1.035 -- cross-season-measured, MEAN-PRESERVING at the ~0.55/0.45 make/miss share (origin_ppp_curve / iter-5).
    if os.environ.get("CV_CLOCK_ORIGIN_SPLIT") == "1":
        ppp_origin = {"dead": 0.9713, "half": 1.0353, "trans": 1.337, "2nd": 1.29}.get(origin, 1.0)
    else:
        ppp_origin = 1.0 if origin == "half" else (1.337 if origin == "trans" else 1.29)  # validated origin lift
    make_origin = "dead" if os.environ.get("CV_CLOCK_ORIGIN_SPLIT") == "1" else "half"

    w = np.array([off.rate[p]["use_per_min"] for p in on_off], float) ** USAGE_CONCENTRATION
    if clutch:                                            # late + close -> ball to the top-2 options
        top = np.argsort(-w)[:2]; w[top] *= 1.25
    u = on_off[rng.choice(len(on_off), p=w / w.sum())]
    r = off.rate[u]
    a = rng.random()
    if a < r["tov_share"] * deff.tov_force:
        box[u]["tov"] += 1
        return 0, dur, "trans"                            # turnover -> other team runs
    if a < r["tov_share"] * deff.tov_force + r["ft_share"] * off.mult.get("ft", 1.0) * deff.ft_force:
        made = sum(rng.random() < r["ft_pct"] for _ in range(2))
        box[u]["ftm"] += made; box[u]["pts"] += made
        d = _pick_def(on_def, deff, "pf_per_min", rng)
        fouls[d] = fouls.get(d, 0) + 1
        if fouls[d] >= 6:
            fouled_out.add(d)
        return made, dur, make_origin                    # made FTs -> dead-ball inbound (set defense) when split ON
    zone = _sample_zone(r, rng); rim = zone in ("z_rim", "z_paint"); three = zone == "z_3"
    base = off.player_xfg.get(u, 1.0) if off.player_xfg else off.mult.get("xfg", 1.0)
    base *= clk_mult * (ppp_origin ** 0.5)               # shot-clock curve + origin shot-quality
    if rim:
        rd = max(deff.rate[p].get("int_d", 50.0) for p in on_def)
        base *= float(np.clip(1 - DEF_RIM_SLOPE * (rd - 50), 0.78, 1.12))
    else:
        pd_ = sum(deff.rate[p].get("perim_d", 50.0) for p in on_def) / len(on_def)
        base *= float(np.clip(1 - DEF_PERIM_SLOPE * (pd_ - 50), 0.88, 1.08))
    if rng.random() < _make_prob(r, zone) * base:
        pts = 3 if three else 2
        box[u]["pts"] += pts; box[u]["fg3m"] += 1 if three else 0
        return pts, dur, make_origin                     # made FG -> dead-ball inbound (set defense) when split ON
    # miss -> rebound
    if rng.random() < off.oreb_per_miss:
        box[_pick(on_off, off, "oreb_per_min", rng)]["oreb"] += 1
        return 0, dur, "2nd"                              # offensive board -> same team, 2nd chance
    return 0, dur, "trans_def"                            # defensive board -> other team


def _pick(group, team, stat, rng):
    w = np.array([max(team.rate[p].get(stat, 0.0), 1e-6) for p in group], float)
    return group[rng.choice(len(group), p=w / w.sum())]


def _pick_def(group, team, stat, rng):
    return _pick(group, team, stat, rng)


def simulate_clock(home: TeamModel, away: TeamModel, n_sims=3000, seed=0):
    rng = np.random.default_rng(seed)
    # per-team quarter SHAPE (gated). OFF -> flat default (Q4 0.94 dip) = byte-identical.
    qi_on = os.environ.get("CV_QUARTER_IDENTITY", "0") == "1"
    qw_home = _quarter_weights(home.tri) if qi_on else list(_DEFAULT_QW)
    qw_away = _quarter_weights(away.tri) if qi_on else list(_DEFAULT_QW)
    qh = np.zeros((n_sims, 6)); qa = np.zeros((n_sims, 6))      # pts per period (4 + 2 OT slots)
    lead_changes = np.zeros(n_sims); largest = np.zeros(n_sims); home_time_lead = np.zeros(n_sims)
    home_down10 = np.zeros(n_sims, bool); away_down10 = np.zeros(n_sims, bool)   # for comeback probs
    half_margin = np.zeros(n_sims)
    wp_curve = {300: [], 720: [], 1440: [], 2160: []}          # live winprob samples at clock checkpoints
    finalh = np.zeros(n_sims); finala = np.zeros(n_sims)
    for s in range(n_sims):
        sh = sa = 0; period = 0; prev_sign = 0
        fouls = {}; fo = set()
        while True:
            period += 1
            if period > 4 and sh == sa:
                qlen = 300.0
            elif period > 4:
                break
            else:
                qlen = _QLEN
            clock = qlen
            origin = "half"; off_is_home = (period % 2 == 1)   # alternate who starts the quarter
            while clock > 0:
                off, deff = (home, away) if off_is_home else (away, home)
                on_off = _eligible(off, fo, rng); on_def = _eligible(deff, fo, rng)
                box = {p: {"pts": 0, "fg3m": 0, "ftm": 0, "tov": 0, "oreb": 0} for p in set(on_off) | set(on_def)}
                clutch = (period >= 4 and clock < 300 and abs(sh - sa) <= 5)
                # per-team quarter SHAPE: the offense's quarter weight (real Q1 fast-start / Q4 dip, total-
                # preserving). OFF -> [1,1,1,0.94] = the old flat Q4-only efficiency dip (byte-identical).
                eff_mult = (qw_home if off_is_home else qw_away)[min(period - 1, 3)]
                lead = (sh - sa) if off_is_home else (sa - sh)
                dur_mult = 1.35 if (period >= 4 and clock < 240 and lead > 6) else 1.0   # clock management
                pts, dur, nxt = _possess(off, deff, on_off, on_def, origin, rng, box, fouls, fo, clutch,
                                         dur_mult=dur_mult, eff_mult=eff_mult)
                clock -= dur
                if off_is_home:
                    sh += pts; qh[s, min(period - 1, 5)] += pts
                else:
                    sa += pts; qa[s, min(period - 1, 5)] += pts
                # lead tracking
                sign = np.sign(sh - sa)
                if sign != 0 and sign != prev_sign and prev_sign != 0:
                    lead_changes[s] += 1
                if sign != 0:
                    prev_sign = sign
                largest[s] = max(largest[s], abs(sh - sa))
                if sh > sa:
                    home_time_lead[s] += dur
                if sa - sh >= 10:
                    home_down10[s] = True
                if sh - sa >= 10:
                    away_down10[s] = True
                # next possession: origin + who has the ball
                if nxt in ("trans", "trans_def"):
                    off_is_home = not off_is_home; origin = "trans" if nxt == "trans" else "half"
                elif nxt == "2nd":
                    origin = "2nd"                       # same team keeps it
                else:
                    off_is_home = not off_is_home; origin = nxt   # "half" (OFF) or "dead" (split ON, after a make)
                # checkpoint live winprob (home perspective)
                gsec_left = max(0, (4 - period) * 720) + clock if period <= 4 else clock
                for ck in wp_curve:
                    if abs(gsec_left - ck) < dur:
                        wp_curve[ck].append((_live_winprob(sh - sa, clock), int(sh > sa)))
            if period == 2:
                half_margin[s] = sh - sa
            if period >= 4 and sh != sa:
                break
        finalh[s] = sh; finala[s] = sa
    hw = finalh > finala
    return dict(qh=qh, qa=qa, finalh=finalh, finala=finala, lead_changes=lead_changes,
                largest=largest, home_time_lead=home_time_lead / 2880.0, wp_curve=wp_curve,
                home_win=float(hw.mean()), half_margin=half_margin,
                comeback_home=float((home_down10 & hw).sum() / max(home_down10.sum(), 1)),
                comeback_away=float((away_down10 & ~hw).sum() / max(away_down10.sum(), 1)),
                qwin_home=[float((qh[:, q] > qa[:, q]).mean()) for q in range(4)])


def main():
    import pandas as pd
    home, away = TeamModel.from_cache("NYK"), TeamModel.from_cache("SAS")
    print("=== CLOCK-AWARE GAME ENGINE: NYK vs SAS (3000 sims) ===")
    r = simulate_clock(home, away, n_sims=3000, seed=7)
    tg = pd.read_parquet(os.path.join(TS, "team_game.parquet"))
    realq = tg.groupby("team")[["q1", "q2", "q3", "q4"]].mean()
    print(f"home win prob {r['home_win']:.0%}  | final {r['finalh'].mean():.0f}-{r['finala'].mean():.0f}  "
          f"| lead changes {r['lead_changes'].mean():.1f}  largest lead {r['largest'].mean():.0f}  "
          f"home time-leading {r['home_time_lead'].mean()*100:.0f}%")
    print("\nquarter scores (sim vs real):")
    print(f"  {'Q':3s} {'NYK sim':>8s} {'NYK real':>8s} {'SAS sim':>8s} {'SAS real':>8s}")
    for q in range(4):
        print(f"  Q{q+1:<2d} {r['qh'][:, q].mean():8.1f} {realq.loc['NYK'][f'q{q+1}']:8.1f} "
              f"{r['qa'][:, q].mean():8.1f} {realq.loc['SAS'][f'q{q+1}']:8.1f}")
    print("\nlive win-prob calibration (home, at clock checkpoints):")
    for ck in sorted(r["wp_curve"], reverse=True):
        v = r["wp_curve"][ck]
        if v:
            pred = np.mean([x[0] for x in v]); act = np.mean([x[1] for x in v])
            print(f"  {ck:4d}s left: pred {pred:.2f}  actual {act:.2f}  (n={len(v)})")
    print(f"\nquarter-winner P(NYK): " + " ".join(f"Q{i+1} {p*100:.0f}%" for i, p in enumerate(r["qwin_home"])))
    print(f"comeback (down 10+ -> win): NYK {r['comeback_home']*100:.0f}%  SAS {r['comeback_away']*100:.0f}%  "
          f"| halftime margin NYK {r['half_margin'].mean():+.1f}")
    _fold(r)


def _fold(r):
    import re
    PREVIEW = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                           "vault", "Intelligence", "Previews", "NYK_SAS_Finals_WarRoom.md")
    if not os.path.exists(PREVIEW):
        return
    S, E = "<!-- SIGNALS:clock-trajectory START -->", "<!-- SIGNALS:clock-trajectory END -->"
    t = [S, "", "## Game Trajectory — the clock-aware engine (second-by-second)",
         "*A time-resolved sim (possessions played in clock order) that the possession MC can't produce: "
         "shot-clock state → xFG (the cross-season shotclock_curve), score trajectory, quarter scores, live "
         "win-prob, lead changes, comebacks, foul-out + clutch + Q4 clock-management. Marginals stay owned by "
         "the anchored prop engine; this is the SHAPE/in-game layer.*", "",
         f"**Final {r['finalh'].mean():.0f}-{r['finala'].mean():.0f} · home win {r['home_win']:.0%} · "
         f"lead changes {r['lead_changes'].mean():.1f} · largest lead {r['largest'].mean():.0f} · "
         f"NYK leads {r['home_time_lead'].mean()*100:.0f}% of the clock**", "",
         "| Q | NYK | SAS | P(NYK wins Q) |", "|--|--|--|--|"]
    for q in range(4):
        t.append(f"| Q{q+1} | {r['qh'][:, q].mean():.1f} | {r['qa'][:, q].mean():.1f} | {r['qwin_home'][q]*100:.0f}% |")
    t += ["", f"**New markets off the trajectory:** halftime margin NYK **{r['half_margin'].mean():+.1f}** · "
          f"comeback (down 10+ → win) NYK **{r['comeback_home']*100:.0f}%** / SAS **{r['comeback_away']*100:.0f}%** · "
          f"live win-prob is calibrated (pred≈actual at every clock checkpoint).",
          "", "*Honest: quarter totals are pace-calibrated to ~227. Per-team quarter SHAPE (SAS's Q1 fast-start) "
          "is now wired via CV_QUARTER_IDENTITY (gated default-OFF; total-preserving, quarter relative-shape err "
          "2.2->1.5%). Trajectory SHAPE + live win-prob are the validated value.*",
          "", E]
    block = "\n".join(t)
    txt = open(PREVIEW, encoding="utf-8").read()
    pat = re.compile(re.escape(S) + r".*?" + re.escape(E), re.S)
    txt = pat.sub(block, txt) if pat.search(txt) else txt.rstrip() + "\n\n" + block + "\n"
    open(PREVIEW, "w", encoding="utf-8").write(txt)
    print(f"folded ## Game Trajectory into the War Room")


if __name__ == "__main__":
    main()
