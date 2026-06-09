"""OUTCOME-IMPACT validation: does the leak-free team_strength as_of SRS produce
a real betting edge vs REAL game lines (ATS spread + total O/U)?

Model (point-in-time, leak-free for SPREAD):
  model_margin = (home_rating_asof - away_rating_asof) + league_home_court_margin
  -> bet HOME ATS if model_margin > -home_spread (i.e. model home-cover margin > 0)

Totals are graded too, but the per-team total tendency (avg_game_total /
game_total_vs_league) in team_strength.json is a SEASON AGGREGATE = full-season
hindsight => the TOTAL grade is NOT leak-free (optimistic / scouting only).
Reported separately and flagged.

Real lines: data/pregame_spreads.parquet (ESPN home_spread + total, no odds col
 -> impose flat -110, the side-juice convention of scripts/grade_m2_game_lines.py).
Outcomes: data/nba/linescores_all.json (OT-corrected, same loader as the M2 grader).

DISCIPLINE (hard prior lessons):
  - grade vs REAL posted lines @ -110; payout = 100/abs(odds)
  - coherence guard: blind HOME+AWAY (and OVER+UNDER) ROI must be ~ -2*vig (<0).
    A positive sum => corrupt/biased join => refuse to trust the grade.
  - gate on n_games_prior >= 50 (drop early-season SRS noise)
  - TWO-CORPUS: rolling-origin -> two date windows (H1 vs H2 of the season).
    A finding that passes one window but not the other = REJECT.
  - regular season only (team_strength as_of has ONLY 00225 reg-season game_ids;
    no playoff game_ids present -> playoff split is empty by construction).

Writes nothing to production. Prints a structured report.
"""
from __future__ import annotations
import json
import os
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NBA = os.path.join(ROOT, "data", "nba")
TS = os.path.join(ROOT, "data", "cache", "intel_outcome", "team_strength.json")
SPREADS = os.path.join(ROOT, "data", "pregame_spreads.parquet")

ODDS = -110.0  # standard side juice (pregame_spreads has no odds col)
N_PRIOR_GATE = 50

ESPN2NBA = {"GS": "GSW", "NO": "NOP", "NY": "NYK", "SA": "SAS",
            "UTAH": "UTA", "WSH": "WAS"}


def payout(win: bool) -> float:
    return (100.0 / abs(ODDS)) if win else -1.0


# ---------------------------------------------------------------------------
def load_outcomes():
    """game_id -> (home_score, away_score, had_ot). Same OT-corrected loader as
    scripts/grade_m2_game_lines.py (q1-q4 + OT, require non-zero regulation)."""
    with open(os.path.join(NBA, "linescores_all.json"), encoding="utf-8") as f:
        ls = json.load(f)
    out = {}
    for gid, v in ls.items():
        try:
            h = sum(float(v.get(f"home_q{i}", 0) or 0) for i in range(1, 5)) + float(v.get("home_pts_ot", 0) or 0)
            a = sum(float(v.get(f"away_q{i}", 0) or 0) for i in range(1, 5)) + float(v.get("away_pts_ot", 0) or 0)
        except (TypeError, ValueError):
            continue
        reg_h = sum(float(v.get(f"home_q{i}", 0) or 0) for i in range(1, 5))
        reg_a = sum(float(v.get(f"away_q{i}", 0) or 0) for i in range(1, 5))
        if reg_h <= 0 or reg_a <= 0:
            continue
        out[gid] = (h, a, bool(v.get("had_ot", False)))
    return out


def load_season_games():
    """game_id -> (home_team, away_team, game_date) for 2025-26 (NBA abbrevs)."""
    p = os.path.join(NBA, "season_games_2025-26.json")
    d = json.load(open(p, encoding="utf-8"))
    rows = d.get("rows", d) if isinstance(d, dict) else d
    out = {}
    for r in rows:
        if not r.get("home_team") or not r.get("away_team"):
            continue  # skip malformed sim-only fragments
        gid = str(r["game_id"])
        out[gid] = (r["home_team"], r["away_team"], str(r["game_date"])[:10])
    return out


def load_team_strength():
    d = json.load(open(TS, encoding="utf-8"))
    lg = d["league"]
    hca = float(lg["home_court_margin_pts"])
    lg_total = float(lg["avg_game_total_pts"])
    # per-team as_of: (team, game_id) -> (rating_to_date, n_games_prior)
    asof = {}
    tot_tend = {}  # team -> game_total_vs_league (season aggregate, LEAKY)
    for t, v in d["teams"].items():
        tot_tend[t] = float(v.get("game_total_vs_league", 0.0))
        for r in v["as_of"]:
            asof[(t, str(r["game_id"]))] = (float(r["rating_to_date"]), int(r["n_games_prior"]))
    return hca, lg_total, asof, tot_tend


# ---------------------------------------------------------------------------
def build_frame():
    hca, lg_total, asof, tot_tend = load_team_strength()
    sg = load_season_games()
    outc = load_outcomes()

    # real lines (ESPN), map abbrevs to NBA
    sp = pd.read_parquet(SPREADS)
    sp["game_date"] = sp["game_date"].astype(str).str[:10]
    for col in ("home_team", "away_team"):
        sp[col] = sp[col].map(lambda t: ESPN2NBA.get(t, t))
    # DATE-TOLERANT join (EX-3 lesson): pregame_spreads game_date is up to 1 day
    # off season_games (ET-vs-UTC boundary). An EXACT-date join silently drops
    # ~76% of games and selection-biases survivors toward home covers (false
    # blind-HOME signal). Index by (home,away)->[(date, spread, total)], then for
    # each game pick the line whose date is within 1 day, nearest first.
    line_by_ha = {}
    for r in sp.itertuples(index=False):
        line_by_ha.setdefault((r.home_team, r.away_team), []).append(
            (pd.Timestamp(r.game_date), float(r.home_spread), float(r.total)))

    def lookup_line(gdate, home, away):
        cands = line_by_ha.get((home, away))
        if not cands:
            return None
        gd = pd.Timestamp(gdate)
        best = None
        bestdd = 99
        for (ld, sprd, tot) in cands:
            dd = abs((ld - gd).days)
            if dd <= 1 and dd < bestdd:
                best = (sprd, tot)
                bestdd = dd
        return best

    rows = []
    n_no_line = n_no_outcome = n_no_rating = 0
    for gid, (home, away, gdate) in sg.items():
        if not gid.startswith("00225"):
            continue  # reg season only (as_of has only these anyway)
        if gid not in outc:
            n_no_outcome += 1
            continue
        hr = asof.get((home, gid))
        ar = asof.get((away, gid))
        if hr is None or ar is None:
            n_no_rating += 1
            continue
        line = lookup_line(gdate, home, away)
        if line is None:
            n_no_line += 1
            continue
        home_spread, total = line
        h_score, a_score, had_ot = outc[gid]
        score_diff = h_score - a_score          # home margin
        total_box = h_score + a_score
        home_rating, n_prior_h = hr
        away_rating, n_prior_a = ar
        n_prior = min(n_prior_h, n_prior_a)
        model_margin = (home_rating - away_rating) + hca
        # model total: league avg + both teams' season tendency (LEAKY tendency)
        model_total = lg_total + tot_tend.get(home, 0.0) + tot_tend.get(away, 0.0)
        rows.append({
            "game_id": gid, "date": gdate, "home": home, "away": away,
            "home_spread": home_spread, "total": total,
            "score_diff": score_diff, "total_box": total_box, "had_ot": had_ot,
            "model_margin": model_margin, "model_total": model_total,
            "n_prior": n_prior,
        })
    df = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    print(f"[build] season_games={len(sg)} | graded n={len(df)} "
          f"(skipped: no_outcome={n_no_outcome} no_rating={n_no_rating} no_line={n_no_line})")
    return df


# ---------------------------------------------------------------------------
def grade_spread(df):
    """Bet model's ATS side. home cover margin = score_diff + home_spread.
    model home-cover margin = model_margin + home_spread."""
    bets = []
    for r in df.itertuples(index=False):
        model_cov = r.model_margin + r.home_spread
        if abs(model_cov) < 1e-9:
            continue
        side_home = model_cov > 0
        cov = r.score_diff + r.home_spread
        if abs(cov) < 1e-9:
            continue  # push
        home_covers = cov > 0
        won = (side_home and home_covers) or (not side_home and not home_covers)
        bets.append(payout(won))
    return _summ(bets)


def grade_total(df):
    bets = []
    for r in df.itertuples(index=False):
        if abs(r.model_total - r.total) < 1e-9:
            continue
        side_over = r.model_total > r.total
        if abs(r.total_box - r.total) < 1e-9:
            continue  # push
        outcome_over = r.total_box > r.total
        won = (side_over and outcome_over) or (not side_over and not outcome_over)
        bets.append(payout(won))
    return _summ(bets)


def blind(df, kind, side):
    bets = []
    for r in df.itertuples(index=False):
        if kind == "spread":
            cov = r.score_diff + r.home_spread
            if abs(cov) < 1e-9:
                continue
            home_covers = cov > 0
            won = (side == "HOME" and home_covers) or (side == "AWAY" and not home_covers)
        else:
            if abs(r.total_box - r.total) < 1e-9:
                continue
            over = r.total_box > r.total
            won = (side == "OVER" and over) or (side == "UNDER" and not over)
        bets.append(payout(won))
    return _summ(bets)


def _summ(bets):
    b = np.array(bets, dtype=float)
    n = len(b)
    if n == 0:
        return {"n": 0, "win_pct": 0.0, "roi_pct": 0.0}
    return {"n": int(n), "win_pct": float((b > 0).mean() * 100),
            "roi_pct": float(b.sum() / n * 100)}


def edge_thresh(df, kind, edge):
    if kind == "spread":
        sub = df[(df["model_margin"] + df["home_spread"]).abs() >= edge]
        return grade_spread(sub)
    else:
        sub = df[(df["model_total"] - df["total"]).abs() >= edge]
        return grade_total(sub)


# ---------------------------------------------------------------------------
def report_corpus(df, label):
    print(f"\n===== {label}  (n={len(df)}) =====")
    coh_s = {"HOME": blind(df, "spread", "HOME"), "AWAY": blind(df, "spread", "AWAY")}
    coh_t = {"OVER": blind(df, "total", "OVER"), "UNDER": blind(df, "total", "UNDER")}
    s_sum = coh_s["HOME"]["roi_pct"] + coh_s["AWAY"]["roi_pct"]
    t_sum = coh_t["OVER"]["roi_pct"] + coh_t["UNDER"]["roi_pct"]
    print(f"  COHERENCE spread: blind-HOME {coh_s['HOME']['roi_pct']:+.2f}% + blind-AWAY "
          f"{coh_s['AWAY']['roi_pct']:+.2f}% = {s_sum:+.2f}%  "
          f"({'OK<0' if s_sum < 0 else 'CORRUPT>0'})")
    print(f"  COHERENCE total : blind-OVER {coh_t['OVER']['roi_pct']:+.2f}% + blind-UNDER "
          f"{coh_t['UNDER']['roi_pct']:+.2f}% = {t_sum:+.2f}%  "
          f"({'OK<0' if t_sum < 0 else 'CORRUPT>0'})")
    sp = grade_spread(df)
    to = grade_total(df)
    print(f"  SPREAD (leak-free) : n={sp['n']:4d} win={sp['win_pct']:5.1f}% roi={sp['roi_pct']:+7.2f}%")
    print(f"  TOTAL  (LEAKY tend): n={to['n']:4d} win={to['win_pct']:5.1f}% roi={to['roi_pct']:+7.2f}%")
    print("  edge-threshold (spread, leak-free):")
    for e in (2, 4, 6):
        v = edge_thresh(df, "spread", e)
        print(f"    edge>={e}: n={v['n']:4d} win={v['win_pct']:5.1f}% roi={v['roi_pct']:+7.2f}%")
    return {"label": label, "n": len(df), "coh_spread_sum": s_sum, "coh_total_sum": t_sum,
            "spread": sp, "total": to,
            "spread_edge": {e: edge_thresh(df, "spread", e) for e in (2, 4, 6)}}


def main():
    df = build_frame()
    df = df[df["n_prior"] >= N_PRIOR_GATE].reset_index(drop=True)
    print(f"[gate] n_games_prior>={N_PRIOR_GATE}: n={len(df)}  "
          f"date {df['date'].min()} -> {df['date'].max()}")

    results = {}
    results["ALL"] = report_corpus(df, "FULL regular season (gated)")

    # rolling-origin two windows: split by median date
    df = df.sort_values("date").reset_index(drop=True)
    mid = len(df) // 2
    h1 = df.iloc[:mid].reset_index(drop=True)
    h2 = df.iloc[mid:].reset_index(drop=True)
    print(f"\n[two-corpus] H1 {h1['date'].min()}..{h1['date'].max()} (n={len(h1)})  |  "
          f"H2 {h2['date'].min()}..{h2['date'].max()} (n={len(h2)})")
    results["H1"] = report_corpus(h1, "WINDOW 1 (first half of season)")
    results["H2"] = report_corpus(h2, "WINDOW 2 (second half of season)")

    # rolling-origin: 3 chronological thirds (extra robustness check)
    print("\n[rolling-origin] 3 chronological thirds:")
    n = len(df)
    for i, (lo, hi) in enumerate([(0, n // 3), (n // 3, 2 * n // 3), (2 * n // 3, n)], 1):
        sub = df.iloc[lo:hi]
        sp = grade_spread(sub)
        to = grade_total(sub)
        print(f"  T{i} {sub['date'].min()}..{sub['date'].max()} n={len(sub):4d} | "
              f"SPREAD win={sp['win_pct']:5.1f}% roi={sp['roi_pct']:+7.2f}% | "
              f"TOTAL win={to['win_pct']:5.1f}% roi={to['roi_pct']:+7.2f}%")
        results[f"T{i}"] = {"spread": sp, "total": to,
                            "date_lo": sub['date'].min(), "date_hi": sub['date'].max()}

    out = os.path.join(ROOT, "data", "cache", "_exp", "team_strength_line_grade.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    json.dump(results, open(out, "w"), indent=2)
    print(f"\n[done] wrote {out}")


if __name__ == "__main__":
    main()
