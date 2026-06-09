"""
effects_momentum_runs.py  –  momentum autocorrelation in NBA PBP

QUESTION: Is there real momentum beyond chance?
Does a scoring run in the previous N possessions predict the next possession
outcome beyond the team's base eFG rate?

METHOD:
  - Parse all PBP JSON files in data/cache/team_system/pbp/
  - For each game reconstruct a sequence of possession outcomes per team:
      scored | not scored | (FT-only counted separately)
  - Compute:
      (a) Lag-1 autocorrelation of scoring indicator (raw)
      (b) Run effect: P(score | prev K all scored) vs P(score | prev K all missed)
      (c) Pace effect: possession rate in the 5 possessions AFTER a run vs base

HONEST PRIOR: most NBA momentum literature finds autocorrelation ~ 0 to +0.03.
Big numbers = confound (lineup changes, foul trouble, etc.).

Output: magnitude as an eFG multiplier on short_term_pace_eff.
"""

import json
import math
import os
import sys
from pathlib import Path

# Ensure project root on sys.path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

PBP_DIR = ROOT / "data" / "cache" / "team_system" / "pbp"
BOX_DIR = ROOT / "data" / "cache" / "team_system" / "box"

# ──────────────────────────────────────────────────────────────────────────────
# helpers
# ──────────────────────────────────────────────────────────────────────────────

def parse_clock(s: str) -> float:
    """ISO duration -> seconds remaining in period."""
    if not s:
        return 0.0
    import re
    m = re.match(r"PT(?:(\d+)M)?(?:([\d.]+)S)?", s)
    if not m:
        return 0.0
    return float(m.group(1) or 0) * 60 + float(m.group(2) or 0)


def period_len(p: int) -> int:
    return 720 if p <= 4 else 300


def game_sec(period: int, rem: float) -> float:
    before = sum(period_len(pp) for pp in range(1, period))
    return before + (period_len(period) - rem)


def extract_possession_sequence(actions: list) -> list[dict]:
    """
    Return one record per scoring event (field goals + free throw clusters).
    Each record: {gsec, team_id, pts_scored, is_run_scored}

    We build a simpler sequence: each possession ends with either a score or not.
    We track alternating possessions using the 'possession' field (team_id who HAS the ball).
    """
    records = []
    sh = sa = 0
    last_poss_team = None
    last_poss_gsec = 0.0
    poss_pts = 0  # pts scored this possession

    # track active possession across events
    for act in actions:
        at = act.get("actionType", "")
        period = int(act.get("period") or 1)
        rem = parse_clock(act.get("clock") or "")
        gsec = game_sec(period, rem)

        poss_team = act.get("possession")  # team_id that has the ball
        if poss_team:
            try:
                poss_team = int(poss_team)
            except Exception:
                poss_team = None

        # update score
        new_h = act.get("scoreHome")
        new_a = act.get("scoreAway")
        if new_h not in (None, ""):
            try:
                nh, na = int(new_h), int(new_a)
                dh, da = nh - sh, na - sa
                sh, sa = nh, na
                pts = dh + da
                if pts > 0:
                    scoring_team_pts = dh if dh else da
                    records.append({
                        "gsec": gsec,
                        "scored": 1,
                        "pts": scoring_team_pts,
                        "poss_team": poss_team,
                    })
            except Exception:
                pass

    return records


def build_poss_sequence_from_fg(actions: list) -> list[dict]:
    """
    Reconstruct a possession-level scoring sequence.
    Each possession = one FGA (or a FT cluster after a non-shooting foul).
    Returns list of {gsec, team_id, scored, pts} per FGA possession.
    """
    sh = sa = 0
    events = []

    for act in actions:
        at = act.get("actionType", "")
        period = int(act.get("period") or 1)
        rem = parse_clock(act.get("clock") or "")
        gsec = game_sec(period, rem)
        tid_raw = act.get("teamId") or 0
        tid = int(tid_raw) if tid_raw else 0

        # update score tracker
        new_h = act.get("scoreHome")
        new_a = act.get("scoreAway")
        if new_h not in (None, ""):
            try:
                sh, sa = int(new_h), int(new_a)
            except Exception:
                pass

        # field goal attempt = end of a possession
        if at in ("2pt", "3pt") and tid:
            made = act.get("shotResult") == "Made"
            pts_scored = 0
            if made:
                pts_scored = 3 if at == "3pt" else 2
            events.append({
                "gsec": gsec,
                "team_id": tid,
                "scored": 1 if made else 0,
                "pts": pts_scored,
                "efg": pts_scored / 2,  # eFG contribution per shot
            })
        elif at == "turnover" and tid:
            events.append({
                "gsec": gsec,
                "team_id": tid,
                "scored": 0,
                "pts": 0,
                "efg": 0.0,
            })

    return events


# ──────────────────────────────────────────────────────────────────────────────
# main analysis
# ──────────────────────────────────────────────────────────────────────────────

def analyze_game(pbp_path: Path) -> list[dict]:
    with open(pbp_path, encoding="utf-8") as f:
        data = json.load(f)
    actions = data.get("game", {}).get("actions", [])
    if not actions:
        return []
    return build_poss_sequence_from_fg(actions)


def run_autocorrelation(all_seqs: list[list[dict]]) -> dict:
    """
    For each game, per team, compute lag-1 and lag-2 autocorrelation of
    the scored indicator.  Pool across all games.
    """
    lag1_pairs = []  # (x_t, x_{t+1}) same team consecutive possessions
    lag2_pairs = []

    for seq in all_seqs:
        if len(seq) < 5:
            continue
        # Group by team within game
        teams = {}
        for ev in seq:
            tid = ev["team_id"]
            teams.setdefault(tid, []).append(ev["scored"])

        for tid, scored_list in teams.items():
            n = len(scored_list)
            for i in range(n - 1):
                lag1_pairs.append((scored_list[i], scored_list[i + 1]))
            for i in range(n - 2):
                lag2_pairs.append((scored_list[i], scored_list[i + 2]))

    def autocorr(pairs):
        if not pairs:
            return 0.0, len(pairs)
        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        n = len(xs)
        mx = sum(xs) / n
        my = sum(ys) / n
        cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / n
        sx = math.sqrt(sum((x - mx) ** 2 for x in xs) / n + 1e-12)
        sy = math.sqrt(sum((y - my) ** 2 for y in ys) / n + 1e-12)
        return cov / (sx * sy), n

    r1, n1 = autocorr(lag1_pairs)
    r2, n2 = autocorr(lag2_pairs)
    return {"lag1_r": r1, "lag1_n": n1, "lag2_r": r2, "lag2_n": n2}


def run_run_effect(all_seqs: list[list[dict]], run_len: int = 3) -> dict:
    """
    Compare P(score on possession T+1) given:
      - HOT: previous `run_len` consecutive possessions all scored
      - COLD: previous `run_len` consecutive possessions all missed
    vs overall base rate.
    """
    base_scored = base_total = 0
    hot_scored = hot_total = 0
    cold_scored = cold_total = 0

    for seq in all_seqs:
        if len(seq) < run_len + 2:
            continue

        teams = {}
        for ev in seq:
            tid = ev["team_id"]
            teams.setdefault(tid, []).append(ev["scored"])

        for tid, scored_list in teams.items():
            n = len(scored_list)
            base_scored += sum(scored_list)
            base_total += n
            for i in range(run_len, n - 1):
                window = scored_list[i - run_len:i]
                next_val = scored_list[i]
                if all(w == 1 for w in window):
                    hot_scored += next_val
                    hot_total += 1
                elif all(w == 0 for w in window):
                    cold_scored += next_val
                    cold_total += 1

    base_rate = base_scored / base_total if base_total else 0
    hot_rate = hot_scored / hot_total if hot_total else 0
    cold_rate = cold_scored / cold_total if cold_total else 0

    return {
        "run_len": run_len,
        "base_rate": base_rate,
        "base_n": base_total,
        "hot_rate": hot_rate,
        "hot_n": hot_total,
        "cold_rate": cold_rate,
        "cold_n": cold_total,
        "hot_vs_base": hot_rate - base_rate,
        "cold_vs_base": cold_rate - base_rate,
        "hot_multiplier": hot_rate / base_rate if base_rate else 1.0,
        "cold_multiplier": cold_rate / base_rate if base_rate else 1.0,
    }


def two_prop_z(p1, n1, p2, n2) -> float:
    """z-score for two proportions."""
    if n1 == 0 or n2 == 0:
        return 0.0
    p_pool = (p1 * n1 + p2 * n2) / (n1 + n2)
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2) + 1e-12)
    return (p1 - p2) / se


def main():
    pbp_files = sorted(PBP_DIR.glob("*.json"))
    print(f"Loading {len(pbp_files)} PBP games...")

    all_seqs = []
    total_possessions = 0
    for fp in pbp_files:
        seq = analyze_game(fp)
        if seq:
            all_seqs.append(seq)
            total_possessions += len(seq)

    print(f"Parsed {len(all_seqs)} games, {total_possessions:,} FGA/TOV possessions\n")

    # ── LAG AUTOCORRELATION ──────────────────────────────────────────────────
    ac = run_autocorrelation(all_seqs)
    print("=" * 60)
    print("LAG AUTOCORRELATION OF SCORING INDICATOR (same team)")
    print("=" * 60)
    print(f"  Lag-1  r = {ac['lag1_r']:+.4f}  (n={ac['lag1_n']:,} pairs)")
    print(f"  Lag-2  r = {ac['lag2_r']:+.4f}  (n={ac['lag2_n']:,} pairs)")
    print()

    # ── RUN EFFECTS ──────────────────────────────────────────────────────────
    for run_len in [2, 3, 4]:
        re = run_run_effect(all_seqs, run_len=run_len)
        z_hot  = two_prop_z(re["hot_rate"],  re["hot_n"],  re["base_rate"], re["base_n"])
        z_cold = two_prop_z(re["cold_rate"], re["cold_n"], re["base_rate"], re["base_n"])
        print(f"RUN EFFECT (run_len={run_len})")
        print(f"  Base rate   : {re['base_rate']:.3f}  (n={re['base_n']:,})")
        print(f"  HOT  rate   : {re['hot_rate']:.3f}  (n={re['hot_n']:,})  "
              f"delta={re['hot_vs_base']:+.4f}  z={z_hot:+.2f}  mult={re['hot_multiplier']:.4f}")
        print(f"  COLD rate   : {re['cold_rate']:.3f}  (n={re['cold_n']:,})  "
              f"delta={re['cold_vs_base']:+.4f}  z={z_cold:+.2f}  mult={re['cold_multiplier']:.4f}")
        print()

    # ── HEADLINE SUMMARY ─────────────────────────────────────────────────────
    re3 = run_run_effect(all_seqs, run_len=3)
    hot_mult  = re3["hot_multiplier"]
    cold_mult = re3["cold_multiplier"]
    base_rate = re3["base_rate"]

    # The useful multiplier for the simulator is the HOT effect
    # (hot run predicts next possession).  Symmetric momentum would be abs deviation.
    momentum_mult = hot_mult  # > 1.0 if real
    print("=" * 60)
    print("HEADLINE FOR SIMULATOR")
    print("=" * 60)
    print(f"  Base FGA-success rate      : {base_rate:.3f}")
    print(f"  After 3-poss HOT run       : {re3['hot_rate']:.3f}  (mult {hot_mult:.4f})")
    print(f"  After 3-poss COLD run      : {re3['cold_rate']:.3f}  (mult {cold_mult:.4f})")
    print(f"  Lag-1 autocorrelation      : {ac['lag1_r']:+.4f}")
    print()
    print("VERDICT:")
    if abs(ac['lag1_r']) < 0.02 and abs(re3['hot_vs_base']) < 0.005:
        print("  Autocorrelation is NEAR ZERO — momentum is NOISE in this sample.")
        print("  Simulator should NOT use a meaningful momentum multiplier.")
        print(f"  Recommended short_term_pace_eff momentum multiplier: ~1.000")
    elif abs(ac['lag1_r']) < 0.05:
        print("  Autocorrelation is SMALL but non-trivial.")
        print(f"  Conservative short_term_pace_eff momentum multiplier: {hot_mult:.4f}")
    else:
        print("  Autocorrelation is moderate — check for confound (lineup changes).")
        print(f"  short_term_pace_eff momentum multiplier: {hot_mult:.4f}")

    print()
    print("NOTE: FGA + TOV only (no FT-only possessions). Lag-1 on same team's")
    print("consecutive possessions within game. n per sample noted above.")


if __name__ == "__main__":
    main()
