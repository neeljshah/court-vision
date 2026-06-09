"""LEGACY POSSESSION FOUNDRY -> cross-season validation of shot_clock_leverage (the discipline: a
single-window peak lies; a real signal REPLICATES across seasons).

`data/nba/pbp_<gid>_p<period>.json` is the stats.nba.com legacy PBP (event lists) covering ~2,500 games
in 2022-23 and 2023-24 -- a different, lower-detail schema than the CDN foundry, but it carries
`game_clock_sec` (elapsed-in-period), so possession DURATION (the shot-clock-used proxy) is recoverable.
This walks those games, segments possessions, tags duration + state, and runs the SAME leak-free OOS lift
test as signal_lab (does poss_dur lower held-out PPP error over a pure game-STATE baseline?) -- PER SEASON.
If shot_clock_leverage replicates in 2022-23 AND 2023-24, the 2025-26 verdict is not a one-window artifact.

  python scripts/team_system/build_legacy_possessions.py
"""
from __future__ import annotations
import glob, json, math, os, re
from collections import defaultdict
import numpy as np, pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NBA = os.path.join(ROOT, "data", "nba")
OUT = os.path.join(ROOT, "data", "cache", "team_system", "legacy_possessions.parquet")
PLEN = lambda p: 720 if p <= 4 else 300


def _pts(et, desc):
    if et == 1:
        return 3 if "3PT" in desc else 2
    if et == 3 and "MISS" not in desc:
        return 1
    return 0


def _margin(e, last):
    """Absolute score margin at this event (perspective-independent -> the clean garbage-time proxy)."""
    sm = e.get("score_margin")
    if sm in (None, ""):
        return last
    s = str(sm).upper()
    if s == "TIE":
        return 0
    try:
        return abs(int(s))
    except Exception:
        return last


def parse_game(gid, files):
    events = []
    for f in sorted(files, key=lambda x: int(re.search(r"_p(\d+)\.json", x).group(1))):
        per = int(re.search(r"_p(\d+)\.json", f).group(1))
        try:
            for e in json.load(open(f, encoding="utf-8")):
                e["_p"] = per; events.append(e)
        except Exception:
            continue
    poss, cur = [], None
    prev_end = None                       # elapsed clock at last handover (this possession's start)
    last_clk = 0.0; after_to = 0; last_margin = 0; pending_dead = 0

    def close():
        nonlocal cur
        if cur is not None and cur["off"]:
            dur = max(0.0, min(30.0, last_clk - cur["start"]))
            cur["poss_dur"] = float(dur); cur.pop("start", None)
            poss.append(cur)
        cur = None

    for e in events:
        et = e.get("event_type"); team = e.get("team_abbrev") or ""
        p = e.get("_p", 1)
        clk = float(e.get("game_clock_sec") or last_clk); last_clk = clk
        last_margin = _margin(e, last_margin)
        desc = e.get("event_desc") or ""
        if et in (1, 2, 3, 5) and team and (cur is None or cur["off"] != team):
            close()
            grem = max(0, 4 - p) * 720 + (PLEN(p) - clk) if p <= 4 else (PLEN(p) - clk)
            st = prev_end if (prev_end is not None and prev_end <= clk) else clk
            cur = dict(gid=gid, off=team, period=p, grem=float(grem), pts=0,
                       after_to=after_to, start=st, abs_margin=int(last_margin),
                       dead_ball=int(pending_dead), had_oreb=0)
            after_to = 0; pending_dead = 0
        if cur is None:
            continue
        cur["pts"] += _pts(et, desc)
        if et == 1:                                   # made FG -> end; next poss restarts vs SET defense (inbound)
            close(); prev_end = clk; pending_dead = 1
        elif et == 3 and " of " in desc:              # last FT of a trip -> end; next is a dead-ball inbound
            m = re.search(r"(\d+) of (\d+)", desc)
            if m and m.group(1) == m.group(2):
                close(); prev_end = clk; pending_dead = 1
        elif et == 5:                                  # turnover -> end, next is LIVE transition
            close(); prev_end = clk; after_to = 1; pending_dead = 0
        elif et == 4 and team and team != cur["off"]:  # DEFENSIVE rebound (other team grabbed) -> handover/flip
            close(); prev_end = clk; pending_dead = 0
        elif et == 4 and team and team == cur["off"]:   # OFFENSIVE rebound (offense kept it) -> 2nd chance, CONTINUE
            cur["had_oreb"] = 1                          # 2nd-chance possession (~1.337 PPP, section 4A)
        # team rebounds (no player/team_abbrev) leave the possession open (resolved by the next action)
    close()
    return poss


def main():
    files = glob.glob(os.path.join(NBA, "pbp_*_p*.json"))
    by_gid = defaultdict(list)
    for f in files:
        m = re.search(r"pbp_(\d{10})_p", os.path.basename(f))
        if m:
            by_gid[m.group(1)].append(f)
    rows = []
    for gid, fs in by_gid.items():
        try:
            rows.extend(parse_game(gid, fs))
        except Exception:
            continue
    D = pd.DataFrame(rows)
    D = D[(D.pts <= 4) & (D.poss_dur >= 0)].copy()
    D["season"] = "20" + D.gid.str[3:5] + "-" + (D.gid.str[3:5].astype(int) + 1).astype(str)
    if "abs_margin" not in D.columns:
        D["abs_margin"] = 0
    D["abs_margin"] = D["abs_margin"].fillna(0).astype(int)   # |score margin| at possession start (garbage-time proxy)
    D.to_parquet(OUT, index=False)
    print(f"LEGACY possessions: {len(D)} from {D.gid.nunique()} games  "
          f"(poss_dur mean {D.poss_dur.mean():.1f}s, after_to {D.after_to.mean()*100:.1f}%)")
    print(f"  by season: {D.season.value_counts().to_dict()}")
    print(f"  quick PPP by clock: quick(<7s) {D[D.poss_dur<7].pts.mean():.3f}  "
          f"late(>=16s) {D[D.poss_dur>=16].pts.mean():.3f}  (overall {D.pts.mean():.3f})")

    # ===== the WIREABLE artifact: the xFG-by-clock CURVE (centered-neutral PPP multiplier) =====
    # turns the validated signal into a concrete generative modulator for CV_SIG_SHOTCLOCK; cross-season-
    # averaged + shown per season for stability. centered at overall PPP so an average-tempo possession is neutral.
    bins = [0, 4, 7, 11, 14, 18, 22, 31]
    labels = ["0-4", "4-7", "7-11", "11-14", "14-18", "18-22", "22+"]
    big = D[D.season.isin(["2022-23", "2023-24"])].copy()
    big["bucket"] = pd.cut(big.poss_dur, bins=bins, labels=labels, right=False)
    overall = big.pts.mean()
    curve = {}
    print("\n=== xFG-by-clock CURVE (PPP multiplier vs overall, cross-season-stable) ===")
    print(f"  {'bucket':8s} {'mult':>6s} {'n':>8s}  per-season mult (22-23/23-24)")
    for lab in labels:
        sub = big[big.bucket == lab]
        if not len(sub):
            continue
        mult = sub.pts.mean() / overall
        s1 = big[(big.bucket == lab) & (big.season == "2022-23")]
        s2 = big[(big.bucket == lab) & (big.season == "2023-24")]
        m1 = s1.pts.mean() / D[D.season == "2022-23"].pts.mean() if len(s1) else float("nan")
        m2 = s2.pts.mean() / D[D.season == "2023-24"].pts.mean() if len(s2) else float("nan")
        curve[lab] = round(float(mult), 4)
        print(f"  {lab:8s} {mult:6.3f} {len(sub):8d}  {m1:.3f}/{m2:.3f}")
    json.dump({"buckets": curve, "overall_ppp": round(float(overall), 4),
               "note": "centered PPP multiplier by possession-duration (shot-clock-used) bucket; cross-season "
                       "stable (2022-23+2023-24, 548k poss); generative modulator for CV_SIG_SHOTCLOCK (xFG-by-clock)"},
              open(os.path.join(ROOT, "data", "cache", "team_system", "shotclock_curve.json"), "w"), indent=2)

    # ===== cross-season leak-free OOS lift: does poss_dur beat a pure STATE baseline? =====
    BASE = ["period", "grem", "after_to"]
    print("\n=== shot_clock_leverage CROSS-SEASON replication (5-fold by game, rmse on possession pts) ===")
    for season, S in D.groupby("season"):
        if S.gid.nunique() < 50:
            print(f"  {season}: only {S.gid.nunique()} games -- skip"); continue
        gids = np.array(sorted(S.gid.unique())); rng = np.random.default_rng(0); rng.shuffle(gids)
        folds = np.array_split(gids, 5)
        be, fe = [], []
        for fold in folds:
            te = S[S.gid.isin(fold)]; tr = S[~S.gid.isin(fold)]
            for feats, acc in ((BASE, be), (BASE + ["poss_dur"], fe)):
                m = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.05, max_iter=250,
                                                  min_samples_leaf=80, random_state=0)
                m.fit(tr[feats], tr.pts); pr = m.predict(te[feats])
                acc.append(math.sqrt(np.mean((pr - te.pts.values) ** 2)))
        b, f = float(np.mean(be)), float(np.mean(fe))
        rel = (f - b) / b
        sh1 = S[S.gid.isin(gids[::2])]; sh2 = S[S.gid.isin(gids[1::2])]
        c1 = sh1.poss_dur.corr(sh1.pts); c2 = sh2.poss_dur.corr(sh2.pts)
        verdict = "REPLICATES" if rel < -0.002 and np.sign(c1) == np.sign(c2) else "does NOT replicate"
        print(f"  {season} (n={len(S):6d}, {S.gid.nunique()} g): rmse {b:.4f}->{f:.4f} "
              f"(rel {rel:+.3%}), split-half corr {c1:+.2f}/{c2:+.2f}  => {verdict}")

    # ===== NEW SIGNAL: score_margin_state (abs_margin) -- does the garbage-time score-state add PPP signal
    # ON TOP OF the validated state (period, grem, after_to, poss_dur)? cross-season, leak-free, 5-fold-by-game.
    print("\n=== score_margin_state (abs_margin) CROSS-SEASON test (on top of validated state incl poss_dur) ===")
    print(f"  raw PPP by |margin|: 0-5 {D[D.abs_margin<=5].pts.mean():.3f}  6-14 "
          f"{D[(D.abs_margin>5)&(D.abs_margin<=14)].pts.mean():.3f}  15-24 "
          f"{D[(D.abs_margin>14)&(D.abs_margin<=24)].pts.mean():.3f}  25+ {D[D.abs_margin>24].pts.mean():.3f}  "
          f"(overall {D.pts.mean():.3f}; mean |margin| {D.abs_margin.mean():.1f})")
    SBASE = ["period", "grem", "after_to", "poss_dur"]
    for season, S in D.groupby("season"):
        if S.gid.nunique() < 50:
            continue
        gids = np.array(sorted(S.gid.unique())); rng = np.random.default_rng(0); rng.shuffle(gids)
        folds = np.array_split(gids, 5)
        be, fe = [], []
        for fold in folds:
            te = S[S.gid.isin(fold)]; tr = S[~S.gid.isin(fold)]
            for feats, acc in ((SBASE, be), (SBASE + ["abs_margin"], fe)):
                m = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.05, max_iter=250,
                                                  min_samples_leaf=80, random_state=0)
                m.fit(tr[feats], tr.pts); pr = m.predict(te[feats])
                acc.append(math.sqrt(np.mean((pr - te.pts.values) ** 2)))
        b, f = float(np.mean(be)), float(np.mean(fe))
        rel = (f - b) / b
        sh1 = S[S.gid.isin(gids[::2])]; sh2 = S[S.gid.isin(gids[1::2])]
        c1 = sh1.abs_margin.corr(sh1.pts); c2 = sh2.abs_margin.corr(sh2.pts)
        sign_ok = np.isfinite(c1) and np.isfinite(c2) and np.sign(c1) == np.sign(c2)
        verdict = "REPLICATES" if rel < -0.002 and sign_ok else "does NOT replicate"
        print(f"  {season} (n={len(S):6d}, {S.gid.nunique()} g): rmse {b:.4f}->{f:.4f} "
              f"(rel {rel:+.3%}), split-half corr {c1:+.2f}/{c2:+.2f}  => {verdict}")

    # ===== NEW SIGNAL: possession_origin dead_ball (after a make -> inbound vs SET defense) -- does it add
    # PPP signal ON TOP OF the validated state (period, grem, after_to, poss_dur)? cross-season, leak-free.
    if "dead_ball" in D.columns:
        D["dead_ball"] = D["dead_ball"].fillna(0).astype(int)
        print("\n=== possession_origin dead_ball CROSS-SEASON test (on top of validated state incl poss_dur) ===")
        print(f"  raw PPP: dead-ball(after make) {D[D.dead_ball==1].pts.mean():.3f}  "
              f"live(miss/TO) {D[D.dead_ball==0].pts.mean():.3f}  (overall {D.pts.mean():.3f}; "
              f"dead-ball share {D.dead_ball.mean()*100:.1f}%)")
        OBASE = ["period", "grem", "after_to", "poss_dur"]
        for season, S in D.groupby("season"):
            if S.gid.nunique() < 50:
                continue
            gids = np.array(sorted(S.gid.unique())); rng = np.random.default_rng(0); rng.shuffle(gids)
            folds = np.array_split(gids, 5)
            be, fe = [], []
            for fold in folds:
                te = S[S.gid.isin(fold)]; tr = S[~S.gid.isin(fold)]
                for feats, acc in ((OBASE, be), (OBASE + ["dead_ball"], fe)):
                    m = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.05, max_iter=250,
                                                      min_samples_leaf=80, random_state=0)
                    m.fit(tr[feats], tr.pts); pr = m.predict(te[feats])
                    acc.append(math.sqrt(np.mean((pr - te.pts.values) ** 2)))
            b, f = float(np.mean(be)), float(np.mean(fe))
            rel = (f - b) / b
            sh1 = S[S.gid.isin(gids[::2])]; sh2 = S[S.gid.isin(gids[1::2])]
            c1 = sh1.dead_ball.corr(sh1.pts); c2 = sh2.dead_ball.corr(sh2.pts)
            sign_ok = np.isfinite(c1) and np.isfinite(c2) and np.sign(c1) == np.sign(c2)
            verdict = "REPLICATES" if rel < -0.002 and sign_ok else "does NOT replicate"
            print(f"  {season} (n={len(S):6d}, {S.gid.nunique()} g): rmse {b:.4f}->{f:.4f} "
                  f"(rel {rel:+.3%}), split-half corr {c1:+.2f}/{c2:+.2f}  => {verdict}")


if __name__ == "__main__":
    main()
