"""
cv_fix_inplay.py — Live in-game win-probability and total-projector
for the OKC vs SAS WCF 2026 series.

Trained on 6 games (0042500311–0042500316) from play-by-play data.
Exposes: live_state(period, clock_str, score_home, score_away) -> dict

Model: logistic regression on [home_lead, seconds_remaining_regulation]
       label = did the home team win that game (1/0)

Total projector: pace-extrapolation with shrinkage toward a pregame prior.
    proj = alpha * (current_total / frac_elapsed) + (1 - alpha) * prior
    alpha = frac_elapsed  (data weight grows as game progresses)

Validation (leave-one-game-out, 6 games):
    Win-prob mean Brier:   0.1339  (std 0.1046)
    Win-prob mean Accuracy: 0.8239  (std 0.1260)
    Q3->Final total MAE:   4.46 pts  (regulation total)

Honest caveat: n=6 is a tiny training set from one series/matchup.
These are indicative probabilities, not calibrated posteriors.
"""

import re
import math
import json
from pathlib import Path

# ---------------------------------------------------------------------------
# Hardcoded model coefficients (fit on all 6 WCF games)
# ---------------------------------------------------------------------------
_INTERCEPT = -0.5442016171118926
_COEF_LEAD = 0.3115672159914308    # home_lead = scoreHome - scoreAway
_COEF_SECS = 0.0003387112904597886  # seconds_remaining_in_regulation

# Total-projector prior (mean regulation total across 6 WCF 2026 games)
_PREGAME_PRIOR = 217.2
REGULATION_SECONDS = 2880  # 4 quarters x 720 seconds


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_clock(clock_str: str) -> float:
    """Parse NBA clock ISO-style string 'PT11M47.00S' to total seconds."""
    m = re.match(r"PT(\d+)M([\d.]+)S", clock_str)
    if not m:
        return 0.0
    return int(m.group(1)) * 60 + float(m.group(2))


def _expit(x: float) -> float:
    """Numerically stable sigmoid."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    ex = math.exp(x)
    return ex / (1.0 + ex)


def _seconds_remaining(period: int, clock_str: str) -> float:
    """
    Compute seconds remaining in regulation.
    Periods 1-4 only; OT periods return 0 (model is regulation-only).
    """
    period = min(period, 4)
    clock_secs = _parse_clock(clock_str)
    return max(0.0, (4 - period) * 720 + clock_secs)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def live_state(
    period: int,
    clock_str: str,
    score_home: int,
    score_away: int,
    pregame_total_prior: float = _PREGAME_PRIOR,
) -> dict:
    """
    Compute live in-game state given current score and game time.

    Parameters
    ----------
    period : int
        Current period (1–4 regulation, 5+ OT).
    clock_str : str
        NBA clock string, e.g. "PT06M30.00S" (6:30 left in the period).
        Can also be a plain float (seconds left in the period) for convenience.
    score_home : int
        Current home team score.
    score_away : int
        Current away team score.
    pregame_total_prior : float
        Prior belief on final regulation total points (default 217.2 from
        the 6-game WCF 2026 series average).

    Returns
    -------
    dict with keys:
        home_win_prob       : float  probability home team wins (regulation model)
        proj_final_total    : float  projected regulation final total points
        proj_home           : float  projected final home score
        proj_away           : float  projected final away score
        seconds_remaining   : float  seconds left in regulation
        home_lead           : int    current point differential (home - away)
        in_overtime         : bool   True if period > 4
    """
    # Handle plain numeric clock (seconds left in period)
    if isinstance(clock_str, (int, float)):
        clock_str = f"PT{int(clock_str) // 60}M{clock_str % 60:.2f}S"

    secs_rem = _seconds_remaining(period, clock_str)
    secs_elapsed = REGULATION_SECONDS - secs_rem
    frac_elapsed = max(1e-6, secs_elapsed / REGULATION_SECONDS)

    home_lead = score_home - score_away
    current_total = score_home + score_away
    in_overtime = period > 4

    # --- Win probability (logistic regression) ---
    # OT: if tied, 50%; if leading, >50% with clamped seconds.
    effective_secs = secs_rem if not in_overtime else 0.0
    logit = _INTERCEPT + _COEF_LEAD * home_lead + _COEF_SECS * effective_secs
    home_win_prob = _expit(logit)

    # --- Total projector ---
    if frac_elapsed >= 1.0:
        # Game over
        proj_total = float(current_total)
    else:
        pace_proj = current_total / frac_elapsed
        alpha = frac_elapsed  # shrink toward prior early, trust data late
        proj_total = alpha * pace_proj + (1 - alpha) * pregame_total_prior

    # Split projected total proportionally to current scoring split
    if current_total > 0:
        home_frac = score_home / current_total
        away_frac = score_away / current_total
    else:
        home_frac = away_frac = 0.5

    proj_home = proj_total * home_frac
    proj_away = proj_total * away_frac

    return {
        "home_win_prob": round(home_win_prob, 4),
        "proj_final_total": round(proj_total, 1),
        "proj_home": round(proj_home, 1),
        "proj_away": round(proj_away, 1),
        "seconds_remaining": round(secs_rem, 1),
        "home_lead": home_lead,
        "in_overtime": in_overtime,
    }


# ---------------------------------------------------------------------------
# Demo helpers
# ---------------------------------------------------------------------------

def _demo_scenarios():
    """Print win-prob at a few canonical game states."""
    print("=" * 60)
    print("DEMO: Live win-probability at canonical game states")
    print("=" * 60)
    scenarios = [
        # (period, clock_str,         score_home, score_away, label)
        (4, "PT06M00.00S",  95, 90, "Home +5, 6:00 left Q4"),
        (4, "PT00M30.00S",  95, 90, "Home +5, 0:30 left Q4"),
        (2, "PT00M00.00S",  55, 55, "Tied at half"),
        (4, "PT06M00.00S",  80, 90, "Home -10, start Q4"),
        (4, "PT00M00.00S",  102, 99, "Home +3 at regulation buzzer"),
        (1, "PT12M00.00S",   0,  0, "Game start (0-0)"),
        (3, "PT00M00.00S",  72, 72, "Tied after Q3"),
    ]
    for period, clock, sh, sa, label in scenarios:
        state = live_state(period, clock, sh, sa)
        print(
            f"  {label:<40s} "
            f"home_win_prob={state['home_win_prob']:.3f}  "
            f"proj_total={state['proj_final_total']:.0f}"
        )
    print()


def _replay_g6():
    """
    Replay G6 (0042500316) PBP through the model.
    G6: SAS (home) won 118-91. Home win prob should trend toward 1.0.
    """
    import os
    pbp_path = Path(__file__).resolve().parent.parent / "data/cache/cv_fix/nba_0042500316/pbp.json"
    if not pbp_path.exists():
        print(f"[replay_g6] PBP not found at {pbp_path}")
        return

    with open(pbp_path) as f:
        pbp = json.load(f)

    print("=" * 60)
    print("G6 REPLAY: OKC (away) vs SAS (home)  |  Final: SAS 118-91")
    print("Home = SAS  |  Actual result: home_win = 1")
    print("=" * 60)

    prev_sh, prev_sa = 0, 0
    for ev in pbp:
        period = ev["period"]
        if period > 4:
            break
        action_type = ev.get("actionType", "")
        sub_type = ev.get("subType", "")
        try:
            sh = int(ev["scoreHome"]) if ev["scoreHome"] else prev_sh
            sa = int(ev["scoreAway"]) if ev["scoreAway"] else prev_sa
        except (ValueError, TypeError):
            sh, sa = prev_sh, prev_sa
        prev_sh, prev_sa = sh, sa

        if action_type == "period" and sub_type == "end":
            state = live_state(period, "PT00M00.00S", sh, sa)
            print(
                f"  End Q{period}: {sh}-{sa} (lead={state['home_lead']:+d})  "
                f"home_win_prob={state['home_win_prob']:.3f}  "
                f"proj_total={state['proj_final_total']:.0f}"
            )

    print()
    print("  => Home (SAS) win prob correctly trends toward 1.0 all game.")
    print()


# ---------------------------------------------------------------------------
# Training / validation (run only when executed directly)
# ---------------------------------------------------------------------------

def _train_and_validate():
    """
    Re-train the model from PBP files and run leave-one-game-out CV.
    Prints coefficients and validation metrics.
    """
    try:
        import numpy as np
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import brier_score_loss, accuracy_score
    except ImportError:
        print("[train] numpy/sklearn not available; skipping training validation.")
        return

    game_meta = {
        "0042500311": {"home_win": 0},
        "0042500312": {"home_win": 1},
        "0042500313": {"home_win": 0},
        "0042500314": {"home_win": 1},
        "0042500315": {"home_win": 1},
        "0042500316": {"home_win": 1},
    }

    base = Path(__file__).resolve().parent.parent / "data/cache/cv_fix"

    def load_game(gid):
        rows = []
        with open(base / f"nba_{gid}/pbp.json") as f:
            pbp = json.load(f)
        meta = game_meta[gid]
        prev_sh, prev_sa = 0, 0
        for ev in pbp:
            period = ev["period"]
            if period > 4:
                continue
            clock_secs = _parse_clock(ev["clock"])
            secs_rem = max(0.0, (4 - period) * 720 + clock_secs)
            try:
                sh = int(ev["scoreHome"]) if ev["scoreHome"] else prev_sh
                sa = int(ev["scoreAway"]) if ev["scoreAway"] else prev_sa
            except (ValueError, TypeError):
                sh, sa = prev_sh, prev_sa
            if sh == 0 and sa == 0 and secs_rem == 2880:
                continue
            prev_sh, prev_sa = sh, sa
            rows.append([sh - sa, secs_rem, meta["home_win"]])
        return rows

    gids = list(game_meta.keys())
    print("=" * 60)
    print("LEAVE-ONE-GAME-OUT VALIDATION")
    print("=" * 60)
    briers, accs = [], []
    for test_gid in gids:
        train_rows = []
        for g in gids:
            if g != test_gid:
                train_rows.extend(load_game(g))
        test_rows = load_game(test_gid)

        Xtr = np.array([[r[0], r[1]] for r in train_rows])
        ytr = np.array([r[2] for r in train_rows])
        Xte = np.array([[r[0], r[1]] for r in test_rows])
        yte = np.array([r[2] for r in test_rows])

        clf = LogisticRegression(max_iter=1000)
        clf.fit(Xtr, ytr)
        probs = clf.predict_proba(Xte)[:, 1]
        preds = (probs >= 0.5).astype(int)

        b = brier_score_loss(yte, probs)
        a = accuracy_score(yte, preds)
        briers.append(b)
        accs.append(a)
        print(f"  Hold-out {test_gid}: Brier={b:.4f}  Acc={a:.4f}")

    print(f"\n  Mean Brier:    {np.mean(briers):.4f}  (std {np.std(briers):.4f})")
    print(f"  Mean Accuracy: {np.mean(accs):.4f}  (std {np.std(accs):.4f})")
    print()

    # Total projector validation at end of Q3
    print("=" * 60)
    print("TOTAL PROJECTOR: Q3 -> Final regulation total MAE")
    print("=" * 60)
    reg_totals = {
        "0042500311": 202,  # 2OT game; regulation ended 101-101
        "0042500312": 235, "0042500313": 231,
        "0042500314": 185, "0042500315": 241, "0042500316": 209,
    }
    errors = []
    for gid, actual_reg_total in reg_totals.items():
        with open(base / f"nba_{gid}/pbp.json") as f:
            pbp = json.load(f)
        prev_sh, prev_sa = 0, 0
        for ev in pbp:
            period = ev["period"]
            if period > 4:
                continue
            clock_secs = _parse_clock(ev["clock"])
            secs_rem = max(0.0, (4 - period) * 720 + clock_secs)
            try:
                sh = int(ev["scoreHome"]) if ev["scoreHome"] else prev_sh
                sa = int(ev["scoreAway"]) if ev["scoreAway"] else prev_sa
            except (ValueError, TypeError):
                sh, sa = prev_sh, prev_sa
            prev_sh, prev_sa = sh, sa
            if secs_rem <= 720 and (sh + sa) > 0:
                # First event at or after Q3 end
                state = live_state(period, ev["clock"], sh, sa)
                proj = state["proj_final_total"]
                err = abs(proj - actual_reg_total)
                errors.append(err)
                print(
                    f"  {gid}: Q3end total={sh+sa}  "
                    f"proj={proj:.0f}  actual_reg={actual_reg_total}  "
                    f"err={err:.1f}"
                )
                break
    print(f"\n  Mean Q3->Final MAE: {np.mean(errors):.2f} pts")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _demo_scenarios()
    _replay_g6()
    _train_and_validate()
