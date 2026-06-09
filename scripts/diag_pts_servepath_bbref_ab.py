"""diag_pts_servepath_bbref_ab.py — Quantify the EX-5 bbref bug's ROI impact on LIVE PTS.

The gate1 -8.6% PTS number is measured on the OOF (trained fresh, 129-col, aligned),
so the EX-5 bbref-reorder bug CANNOT explain it. But the bug IS live on the production
serve path: the PTS artifact has n_features_in_=85, predict_pergame slices cols[:85],
and with CV_BBREF_REORDER_FIX OFF (default) slots 80-84 carry bbref_orb/drb/trb/bpm/ws
whereas the artifact was TRAINED with contract_*/pts_share_3pt there. 5/85 features feed
the wrong slots on EVERY live PTS prediction.

This A/B reconstructs each benashkar PTS bet AS-OF (player games strictly before the bet
date; a fresh per-bet gamelog truncation = no leakage), predicts PTS with the flag OFF
(buggy/legacy) vs ON (aligned) via the REAL predict_pergame serve path, and grades both
against the real closes (|odds|>=100, actual posted odds). Quantifies the bug's PTS ROI
impact + MAE-vs-actual. Read-only; does NOT flip the flag in production.
"""
from __future__ import annotations

import importlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from scripts.run_gate1_full_analysis import (  # noqa: E402
    _payout, load_benashkar_bets, attach_actuals_and_l10,
)

_NBA = _ROOT / "data" / "nba"


def _season_for(date_str: str) -> str:
    y, m, _ = (int(x) for x in date_str.split("-"))
    # NBA season starts ~October; Jan-June belongs to the (y-1)-y season.
    return f"{y-1}-{str(y)[2:]}" if m <= 9 else f"{y}-{str(y+1)[2:]}"


def _asof_gamelog(pid: int, season: str, cutoff: datetime):
    """Return the player's season gamelog truncated to games strictly before cutoff,
    written to a temp dir so build_prediction_row only sees prior form (no leak)."""
    path = _NBA / f"gamelog_{pid}_{season}.json"
    if not path.exists():
        return None
    try:
        games = json.load(open(path, encoding="utf-8"))
    except Exception:
        return None
    out = []
    for g in games:
        try:
            d = datetime.strptime(str(g.get("GAME_DATE")).strip(), "%b %d, %Y")
        except Exception:
            continue
        if d < cutoff:
            out.append(g)
    return out


def _predict_pts(pid, season, opp, is_home, tmpdir):
    import src.prediction.prop_pergame as m
    feats = m.build_prediction_row(pid, opp, season, is_home=is_home,
                                   gamelog_dir=tmpdir, min_prior=5)
    if feats is None:
        return None
    return m.predict_pergame("pts", feats)


def run(flag_on: bool, bets):
    """Set the flag, reload the module, predict PTS for each bet as-of."""
    os.environ["CV_BBREF_REORDER_FIX"] = "1" if flag_on else "0"
    import src.prediction.prop_pergame as m
    importlib.reload(m)
    import tempfile
    preds = {}
    tmp = tempfile.mkdtemp(prefix="bbref_ab_")
    for i, b in enumerate(bets):
        pid = b["pid"]
        date_str = b["gdate"].strftime("%Y-%m-%d")
        season = _season_for(date_str)
        cutoff = b["gdate"]
        gl = _asof_gamelog(pid, season, cutoff)
        if not gl or len(gl) < 5:
            continue
        # write truncated gamelog to tmp so build_prediction_row reads prior-only
        tmp_path = os.path.join(tmp, f"gamelog_{pid}_{season}.json")
        json.dump(gl, open(tmp_path, "w"))
        # opp/home unknown from benashkar; use neutral (home=True, opp from last matchup).
        last = str(gl[-1].get("MATCHUP", ""))
        opp = last.split()[-1] if last.split() else "LAL"
        try:
            p = _predict_pts(pid, season, opp, True, tmp)
        except Exception:
            p = None
        preds[(pid, date_str, b["line"])] = p
    return preds


def grade(bets, preds):
    settled = []
    mae = []
    for b in bets:
        key = (b["pid"], b["gdate"].strftime("%Y-%m-%d"), b["line"])
        pred = preds.get(key)
        if pred is None:
            continue
        line, actual = b["line"], b["actual"]
        if abs(actual - line) < 1e-9 or abs(pred - line) < 1e-9:
            continue
        mae.append(abs(pred - actual))
        over = pred > line
        won = (over and actual > line) or (not over and actual < line)
        settled.append(_payout(b["over_odds"] if over else b["under_odds"], won))
    n = len(settled)
    roi = sum(settled) / (n * 100) * 100 if n else 0.0
    return n, roi, (float(np.mean(mae)) if mae else 0.0)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=0,
                    help="cap to first N PTS bets (by date) for a fast A/B; 0=all")
    args = ap.parse_args()
    print("Loading benashkar PTS bets...", flush=True)
    bets = load_benashkar_bets(mainline_only=True)
    bets = attach_actuals_and_l10(bets)
    bets = [b for b in bets if b["stat"] == "pts"
            and abs(b["over_odds"]) >= 100 and abs(b["under_odds"]) >= 100]
    bets.sort(key=lambda b: b["gdate"])
    if args.sample and args.sample < len(bets):
        # stride-sample across the full date range so the A/B isn't one slice
        stride = max(1, len(bets) // args.sample)
        bets = bets[::stride][:args.sample]
    print(f"  {len(bets)} PTS bets (|odds|>=100)\n", flush=True)

    print("Predicting PTS via REAL serve path, flag OFF (legacy/buggy)...")
    preds_off = run(False, bets)
    print(f"  predicted {sum(1 for v in preds_off.values() if v is not None)} bets")
    print("Predicting PTS via REAL serve path, flag ON (aligned)...")
    preds_on = run(True, bets)
    print(f"  predicted {sum(1 for v in preds_on.values() if v is not None)} bets\n")

    # restrict to the intersection where BOTH produced a prediction (fair A/B)
    common = [b for b in bets
              if preds_off.get((b["pid"], b["gdate"].strftime("%Y-%m-%d"), b["line"])) is not None
              and preds_on.get((b["pid"], b["gdate"].strftime("%Y-%m-%d"), b["line"])) is not None]
    n_off, roi_off, mae_off = grade(common, preds_off)
    n_on, roi_on, mae_on = grade(common, preds_on)

    print("=" * 70)
    print("EX-5 bbref serve-path A/B — LIVE PTS predictions vs real benashkar closes")
    print("=" * 70)
    print(f"  flag OFF (legacy, default): n={n_off}  ROI={roi_off:+.2f}%  MAE-vs-actual={mae_off:.3f}")
    print(f"  flag ON  (aligned fix)    : n={n_on}  ROI={roi_on:+.2f}%  MAE-vs-actual={mae_on:.3f}")
    print(f"  delta (ON-OFF): ROI {roi_on-roi_off:+.2f}pp  MAE {mae_on-mae_off:+.3f}")
    # how often do the two preds actually differ, and by how much?
    diffs = []
    for b in common:
        k = (b["pid"], b["gdate"].strftime("%Y-%m-%d"), b["line"])
        diffs.append(abs(preds_off[k] - preds_on[k]))
    diffs = np.array(diffs)
    print(f"\n  |pred_ON - pred_OFF|: mean {diffs.mean():.3f}  median {np.median(diffs):.3f}  "
          f"max {diffs.max():.3f}  frac>0.5pt {np.mean(diffs>0.5)*100:.1f}%")
    print("\n  Interpretation: if the ROI delta is small/noisy, the bbref bug is a")
    print("  correctness wart but NOT the cause of negative PTS ROI. A large positive")
    print("  delta would mean the fix is worth flipping for live PTS betting.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
