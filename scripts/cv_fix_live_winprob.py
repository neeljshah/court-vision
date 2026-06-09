"""
cv_fix_live_winprob.py — live in-game home-win probability from the validated
180-game model (data/cache/cv_fix/inplay_model_v2.json). Grouped-CV Brier:
endQ1 0.215, endQ2 0.186, endQ3 0.137, midQ4 0.091 (beats ~0.19 pregame once live).

Feature formulas replicate scripts/cv_fix_inplay_v2.py::row_to_features exactly.

Usage (clock = time LEFT in the current period, MM:SS):
  python scripts/cv_fix_live_winprob.py --home 58 --away 55 --period 3 --clock 4:30
  python scripts/cv_fix_live_winprob.py --home 58 --away 55 --period 3 --clock 4:30 --poss 1 --run 6
  # --poss: 1 home has ball, -1 away, 0 unknown.  --run: margin change over last ~2 min (home perspective).
"""
from __future__ import annotations
import argparse, json, math, os

CV = "data/cache/cv_fix"
REG = 2880.0
OT = 300.0


def load_model():
    return json.load(open(os.path.join(CV, "inplay_model_v2.json")))


def secs_rem_regulation(period, clock_secs):
    if period <= 4:
        return max(0.0, (4 - period) * 720.0 + clock_secs)
    return 0.0  # OT: regulation-time feature clamps to 0 (is_ot carries the info)


def features(home, away, period, clock_secs, poss=0, run=0.0):
    is_ot = 1 if period > 4 else 0
    secs = secs_rem_regulation(period, clock_secs)
    secs_feat = 0.0 if is_ot else secs
    margin = home - away
    total = home + away
    return [
        margin,
        secs_feat,
        margin * math.sqrt(secs_feat),
        period,
        1 if period >= 3 else 0,
        total,
        abs(margin),
        run,
        poss,
        is_ot,
    ], secs


def predict(model, feats):
    z = [(x - m) / s for x, m, s in zip(feats, model["scaler_mean"], model["scaler_scale"])]
    logit = model["intercept"] + sum(c * zi for c, zi in zip(model["coef"], z))
    return 1.0 / (1.0 + math.exp(-logit))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", type=int, required=True, help="home score")
    ap.add_argument("--away", type=int, required=True, help="away score")
    ap.add_argument("--period", type=int, required=True)
    ap.add_argument("--clock", type=str, required=True, help="time LEFT in period MM:SS")
    ap.add_argument("--poss", type=int, default=0, choices=[-1, 0, 1])
    ap.add_argument("--run", type=float, default=0.0, help="margin change last ~2min (home perspective)")
    ap.add_argument("--home-name", default="HOME")
    ap.add_argument("--away-name", default="AWAY")
    args = ap.parse_args()

    mm, ss = args.clock.split(":")
    clock_secs = int(mm) * 60 + int(ss)
    model = load_model()
    feats, secs = features(args.home, args.away, args.period, clock_secs, args.poss, args.run)
    p_home = predict(model, feats)

    print(f"{args.home_name} {args.home} - {args.away} {args.away}  |  Q{args.period} {args.clock} left"
          f"  ({secs:.0f}s reg remaining)")
    print(f"  P({args.home_name} win) = {p_home*100:.1f}%   P({args.away_name} win) = {(1-p_home)*100:.1f}%")


if __name__ == "__main__":
    main()
