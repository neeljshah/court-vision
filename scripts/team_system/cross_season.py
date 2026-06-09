"""CROSS-SEASON GATE (GATE-X) -- the 5th gate the foundry adds to signal_lab's 4.

signal_lab grades a signal IN ONE SEASON (leak-free 5-fold by game). But a single-window peak lies --
the project's hardest-won lesson. A signal is only a SURVIVOR if it ALSO replicates across INDEPENDENT
seasons. This module is the reusable harness for that, generalized from build_legacy_possessions.py
(which proved it once, hard-wired to shot_clock_leverage):

  - possession(feature, base): does `feature` lower held-out PPP error over a pure game-STATE baseline,
    PER SEASON, on the 548k legacy possession corpus (2022-23 + 2023-24)? REPLICATES = material lift
    in >= 2 independent seasons with a sign-consistent split-half. This is a HARD gate for any
    possession-grain signal -- the substrate exists, so there is no excuse to skip it.

  - prop(stat): the MONEY cross-season bar for prop signals -- thin wrapper over edge_walkforward.walk
    (policy learned on season A applied OUT-OF-SAMPLE to season B; pts/ast have real OOF+odds corpora).

  - GRAINS WITH NO SUBSTRATE (player-game box, team-game, lineup) return verdict='N/A-no-substrate' --
    recorded honestly. They can be IN-SEASON validated but CANNOT become wired survivors until a
    cross-season substrate exists for them (per the foundry's substrate-honest policy).

  python scripts/team_system/cross_season.py --feature after_to        # the pending origin GATE-X
  python scripts/team_system/cross_season.py --feature poss_dur         # re-confirm shot_clock_leverage
"""
from __future__ import annotations
import math, os, sys
from typing import Sequence
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LEGACY = os.path.join(ROOT, "data", "cache", "team_system", "legacy_possessions.parquet")
NOISE_FLOOR = 0.002                      # min relative OOS improvement to count (matches signal_lab)
BIG_SEASONS = ("2022-23", "2023-24")     # the two full independent legacy seasons (276k + 273k poss)
STATE_BASE = ("period", "grem")          # pure game-STATE baseline (a signal must add ON TOP of state)

# --- n_min_per_season floor (P0.1 keystone wiring; ADDITIVE, non-breaking) -------------------
# ARCHITECTURE.md §2 + RED_A §A5: the gate checked season-label presence + p-values but NOT
# minimum per-season sample size, so a thin 2nd season (7.6k / 1.6k / 4-game) could clear by noise.
# This wiring ATTACHES a power_class to a GATE-X result and caps thin grains at RESEARCH. It NEVER
# alters the replication verdict (purely additive fields). If the import fails the floor is advisory.
sys.path.insert(0, os.path.join(ROOT, "src"))
try:
    from loop.gate_nmin import classify_power  # noqa: E402
except Exception:  # pragma: no cover - floor is advisory if import path missing
    classify_power = None


def _attach_power(res: dict, season_counts: dict, grain_floor: str = "") -> dict:
    """Attach per-season statistical-power class to a GATE-X result (ARCHITECTURE §2).

    Additive only: adds power_class / season_counts / honesty_cap / flag_allowed_on; the
    replication verdict (res['verdict']) is untouched. A grain below its n_min floor is
    capped at RESEARCH (flag_allowed_on=False) REGARDLESS of how strong the in-sample lift is.
    """
    if classify_power is None or not season_counts:
        return res
    grain = grain_floor or res.get("grain", "")
    pc = classify_power(season_counts, grain)
    res["power_class"] = pc
    res["season_counts"] = dict(season_counts)
    if pc == "single_season_effective":
        res["honesty_cap"] = "RESEARCH"
        res["flag_allowed_on"] = False
        res["power_note"] = "below n_min_per_season floor -> capped RESEARCH (ARCHITECTURE §2 / RED_A A5)"
    else:
        res.setdefault("honesty_cap", "PROVEN-capable")
        res.setdefault("flag_allowed_on", True)
    return res


def _oos_rel(S: pd.DataFrame, feature: str, base: Sequence[str], seed: int = 0) -> tuple[float, float, float]:
    """5-fold-by-game leak-free OOS rmse on possession pts: base vs base+feature. Returns (base, full, rel)."""
    gids = np.array(sorted(S.gid.unique())); rng = np.random.default_rng(seed); rng.shuffle(gids)
    folds = np.array_split(gids, 5)
    be, fe = [], []
    for fold in folds:
        te = S[S.gid.isin(fold)]; tr = S[~S.gid.isin(fold)]
        for feats, acc in ((list(base), be), (list(base) + [feature], fe)):
            m = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.05, max_iter=250,
                                              min_samples_leaf=80, random_state=seed)
            m.fit(tr[feats], tr.pts); pr = m.predict(te[feats])
            acc.append(math.sqrt(np.mean((pr - te.pts.values) ** 2)))
    b, f = float(np.mean(be)), float(np.mean(fe))
    return b, f, (f - b) / b if b else 0.0


def possession(feature: str, base: Sequence[str] = STATE_BASE, min_games: int = 50,
               seasons: Sequence[str] = BIG_SEASONS) -> dict:
    """GATE-X for a possession-grain feature. REPLICATES = material OOS lift in >= 2 independent seasons
    with a sign-consistent split-half (the same bar signal_lab uses, applied per season)."""
    if not os.path.exists(LEGACY):
        return dict(feature=feature, verdict="N/A-no-corpus", seasons={})
    D = pd.read_parquet(LEGACY)
    D = D[(D.pts <= 4) & (D.poss_dur >= 0)]
    out = {}
    for season in seasons:
        S = D[D.season == season]
        if S.gid.nunique() < min_games:
            out[season] = dict(verdict="skip-fewgames", games=int(S.gid.nunique())); continue
        b, f, rel = _oos_rel(S, feature, base)
        gids = np.array(sorted(S.gid.unique()))
        sh1, sh2 = S[S.gid.isin(gids[::2])], S[S.gid.isin(gids[1::2])]
        c1 = float(sh1[feature].corr(sh1.pts)); c2 = float(sh2[feature].corr(sh2.pts))
        stable = np.isfinite(c1) and np.isfinite(c2) and np.sign(c1) == np.sign(c2)
        verdict = "REPLICATES" if (rel < -NOISE_FLOOR and stable) else "no"
        out[season] = dict(n=int(len(S)), games=int(S.gid.nunique()), base_rmse=round(b, 4),
                           full_rmse=round(f, 4), rel=round(rel, 4), split_half=f"{c1:+.2f}/{c2:+.2f}",
                           verdict=verdict)
    n_repl = sum(1 for r in out.values() if r.get("verdict") == "REPLICATES")
    overall = ("REPLICATES" if n_repl >= 2 else "single-season-only" if n_repl == 1 else "does-NOT-replicate")
    result = dict(feature=feature, base=list(base), grain="possession", n_replicate=n_repl,
                  verdict=overall, seasons=out)
    # P0.1: attach statistical-power class (possession corpus is 276k/273k -> cross_season; no-op floor)
    season_counts = {s: r.get("n", 0) for s, r in out.items() if "n" in r}
    return _attach_power(result, season_counts, grain_floor="possession")


def prop(stat: str) -> dict:
    """GATE-X (money side) for a prop signal: cross-season walk-forward via edge_walkforward.
    Returns the pooled two-season value-bet verdict (the proven-tested money bar)."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from edge_walkforward import _load, _roi, _boot  # noqa: E402
    except Exception as e:
        return dict(stat=stat, grain="prop", verdict=f"N/A-import ({e})")
    A = _load(stat, "regular_season_2024_25"); B = _load(stat, "regular_season_2025_26")
    if A is None or B is None:
        return dict(stat=stat, grain="prop", verdict="N/A-no-corpus (need 2 reg seasons)")
    nA, rA, _ = _roi(A); nB, rB, _ = _roi(B)
    pooled = np.concatenate([A.ret.values, B.ret.values]); lo, hi = _boot(pooled)
    both_pos = rA > 0 and rB > 0
    verdict = ("PROVEN-OOS (both seasons + pooled CI>0)" if both_pos and lo > 0 else
               "suggestive (both + but CI spans 0)" if both_pos else "FAILS cross-season")
    return dict(stat=stat, grain="prop", verdict=verdict, roi_a=round(rA, 1), roi_b=round(rB, 1),
                pooled_roi=round(float(pooled.mean() * 100), 1), pooled_ci=[round(lo, 1), round(hi, 1)],
                n=int(len(pooled)))


def gate_x(grain: str, feature: str = "", base: Sequence[str] = STATE_BASE, stat: str = "",
           season_counts: dict = None, grain_floor: str = None) -> dict:
    """Dispatch GATE-X by grain. Possession -> legacy corpus; prop -> walk-forward; else honest N/A.

    P0.1: ``season_counts`` (per-season labeled-row counts, e.g. for a player_game / quarter grain)
    is run through the n_min_per_season floor; a thin grain is capped at RESEARCH via _attach_power.
    Possession already attaches its own power class from the legacy corpus per-season n.
    """
    if grain == "possession":
        return possession(feature, base)
    if grain == "prop":
        return prop(stat)
    res = dict(grain=grain, feature=feature or stat, verdict="N/A-no-substrate",
               note=f"no cross-season corpus for {grain} grain (in-season validated only; not a wireable survivor)")
    return _attach_power(res, season_counts, grain_floor=grain_floor or grain)


def _print(res: dict) -> None:
    if res.get("grain") == "prop" or "stat" in res:
        print(f"=== GATE-X (prop money) {res.get('stat','')} -> {res['verdict']} ===")
        if "pooled_roi" in res:
            print(f"  2024-25 {res['roi_a']:+}% | 2025-26 {res['roi_b']:+}% | "
                  f"pooled {res['pooled_roi']:+}% (n={res['n']}) CI{res['pooled_ci']}")
        return
    print(f"=== GATE-X (possession) feature='{res['feature']}' base={res.get('base')} -> {res['verdict']} "
          f"({res.get('n_replicate',0)}/{len(res.get('seasons',{}))} seasons) ===")
    for season, r in res.get("seasons", {}).items():
        if r.get("verdict") in ("skip-fewgames",):
            print(f"  {season}: skip ({r.get('games')} games)"); continue
        print(f"  {season} (n={r['n']:6d}, {r['games']}g): rmse {r['base_rmse']:.4f}->{r['full_rmse']:.4f} "
              f"(rel {r['rel']:+.3%}), split-half {r['split_half']}  => {r['verdict']}")


def main():
    args = sys.argv
    if "--prop" in args:
        _print(prop(args[args.index("--prop") + 1])); return
    feat = args[args.index("--feature") + 1] if "--feature" in args else "after_to"
    base = list(STATE_BASE)
    if "--base" in args:
        base = args[args.index("--base") + 1].split(",")
    if feat in base:                                  # never put the tested feature in its own baseline
        base = [b for b in base if b != feat]
    _print(possession(feat, base))


if __name__ == "__main__":
    main()
