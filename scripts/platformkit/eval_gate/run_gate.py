"""The eval-gate CLI -- the contract every future change is judged by (blueprint N1).

`python -m scripts.platformkit.eval_gate.run_gate --golden` runs end-to-end OFFLINE
(< 60s, no network, no data/): loads the SYNTHETIC golden fixture, runs the leak-free
walk_forward with the deterministic offline predictor, scores each corpus (BSS, Brier
+ clustered 95% CI, log_loss, ECE diag, resolution, sharpness, DM stat + p), labels
BEATS / MATCHES / BEHIND, applies the regression-vs-frozen-baseline rule, prints a
one-screen ASCII scoreboard, and exits 0/1 (1 on regression on EITHER corpus or a leak).

HONESTY: the golden fixture is a SYNTHETIC reproducibility / regression ANCHOR, NOT a
real calibration claim. BSS <= 0 / MATCHES_CLOSE is an HONEST SUCCESS, never a failure.
The gate BLOCKS only on regression-vs-frozen-baseline or a leak-guard assertion -- never
on "fails to beat the close". The LLM never emits a probability here.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
from typing import Callable, List, Optional

import numpy as np
from scripts.platformkit.combo.fwer_budget import DEFAULT_EPS, eps_eff

try:  # bare run from eval_gate cwd (so test_gate.py can `from run_gate import ...`)
    from golden_loader import load_golden
    from walkforward import walk_forward
    import scoring as S
    from dm_test import diebold_mariano
    from offline_predict import offline_predict_fn
    from romano_wolf import romano_wolf_stepdown
    from spa_test import hansen_spa
except ImportError:  # python -m package run
    from .golden_loader import load_golden
    from .walkforward import walk_forward
    from . import scoring as S
    from .dm_test import diebold_mariano
    from .offline_predict import offline_predict_fn
    from .romano_wolf import romano_wolf_stepdown
    from .spa_test import hansen_spa

CORPORA = ["nba_2023_24", "nba_2024_25"]   # "mlb_2024" registered-but-skipped slot
SKIPPED_SLOTS = ["mlb_2024"]
DM_MIN_N = 200
BRIER_REGRESS_TOL = 0.005                   # pre-registered min meaningful Brier delta
ROMANO_WOLF_BOOTSTRAPS = 2000
SPA_BOOTSTRAPS = 2000
OFFLINE_BUDGET_SECONDS = 60.0

_HERE = Path(__file__).resolve().parent
_BASELINE_DIR = _HERE / "baselines"

def load_baseline(name: str) -> dict:
    """Load the pre-registered frozen baseline. Prefers the sibling `baseline` module
    when present; else reads baselines/<name>.json. FileNotFoundError when absent ->
    the caller treats that slot as CORPUS_ABSENT.
    """
    try:
        try:
            from baseline import load_baseline as _lb  # type: ignore
        except ImportError:
            from .baseline import load_baseline as _lb  # type: ignore
        return _lb(name)
    except ImportError:
        pass
    p = _BASELINE_DIR / f"{name}.json"
    if not p.exists():
        raise FileNotFoundError(f"baseline missing: {p}")
    with open(p, "r", encoding="ascii") as fh:
        return json.load(fh)

def _load_model_predictor() -> Callable:
    """Real --corpus path: wire proof_nba.ml_accuracy entry points (documented, NOT
    exercised offline). The offline --golden path NEVER imports proof_nba.
    """
    from scripts.platformkit.proof_nba import ml_accuracy  # noqa: F401

    def _fn(train, test, select_inside):  # pragma: no cover (real path)
        return ml_accuracy.run(train, test, select_inside=select_inside)
    return _fn

def _verdict(bss: float, dm, bm: float, bc: float) -> str:
    # S40b (prior red team, agent 1.3): DM_MIN_N was tested against dm.n -- raw STATES --
    # while the SE that produced dm.p_value clusters by game. 200 states can be far fewer
    # than 200 independent games (the golden fixture is 103 states over 70 game_ids), so
    # the floor is now applied to the clusters the statistic actually has.
    if bss > 0 and dm.p_value < 0.05 and dm.n >= DM_MIN_N and dm.n_clusters >= DM_MIN_N:
        return "BEATS_CLOSE"
    lo, hi = dm.ci95
    if lo <= 0.0 <= hi:                       # CI on (loss_close - loss_model) overlaps 0
        return "MATCHES_CLOSE"
    # d = loss_close - loss_model, so a STRICTLY NEGATIVE interval is the model doing worse.
    # A strictly positive interval that did not clear the BEATS_CLOSE bar above is a
    # non-claim, not a loss -- it used to be mislabelled BEHIND, contradicting this
    # function's own documented contract ("CI strictly negative -> BEHIND").
    return "BEHIND" if hi < 0.0 else "MATCHES_CLOSE"   # honest, recorded, NON-blocking


def evaluate_corpus(name: str, predict_fn: Callable, states: List[dict]) -> dict:
    """Score one corpus end-to-end. Never blocks on a non-beat; only regression / leak."""
    # S40b / RT-18: the gate is the fail-closed path, so it opts into the ALLOW-list
    # redaction. A settled column added to the fixture schema later raises LeakError here
    # instead of reaching predict_fn (measured before the fix: Brier 0.0000, no LeakError).
    res = walk_forward(states, predict_fn, select_inside=True, strict_redaction=True)
    # feature-selection-inside-window is non-negotiable: a False flag fails the run
    regressed = res.select_inside is not True
    recs = res.records
    pm = np.array([r["p_model"] for r in recs], dtype=float)
    pc = np.array([r["p_close"] for r in recs], dtype=float)
    y = np.array([r["y"] for r in recs], dtype=float)
    gid = [r["game_id"] for r in recs]
    bm, bc = S.brier(pm, y), S.brier(pc, y)
    bss = S.brier_skill_score(pm, pc, y)
    d = (pc - y) ** 2 - (pm - y) ** 2         # close loss - model loss (>0 => model better)
    dm = diebold_mariano(d, gid)
    out = {
        "corpus": name, "n": len(recs),
        "brier_model": bm, "brier_close": bc, "bss": bss,
        "log_loss": S.log_loss(pm, y), "ece": S.ece(pm, y),
        "resolution": S.resolution(pm, y), "sharpness": S.sharpness(pm),
        "dm_stat": dm.dm_stat, "dm_p": dm.p_value, "ci95": dm.ci95,
        "verdict": _verdict(bss, dm, bm, bc), "leaked": False,
        "_loss_diff": d, "_game_ids": gid,
    }

    # REGRESSION (BLOCKS): worse than the frozen baseline by > tol AND a DM test of
    # model-vs-baseline per-game losses is significant. Fail-safe to the absolute
    # worsening alone when the baseline carries no per-game loss vector.
    base = load_baseline(name)
    worsened = bm > base["brier_model"] + BRIER_REGRESS_TOL
    lm = (pm - y) ** 2                        # per-game model loss
    base_pergame = base.get("per_game_model_loss")
    if base_pergame is not None and len(base_pergame) == len(lm):
        d_vs_base = np.asarray(base_pergame, dtype=float) - lm  # >0 => base better
        sig = diebold_mariano(d_vs_base, gid).p_value < 0.05
        out["regressed"] = bool(regressed or (worsened and sig))
    else:
        out["regressed"] = bool(regressed or worsened)
    return out

def _load_states(name: str, golden_path: Optional[str], corpus_dir: Optional[str]) -> List[dict]:
    """Under --golden BOTH nba corpora load the SAME committed golden fixture (filtered
    by season when present, else the full set). A real --corpus dir would read
    data/domains/<sport>; that branch raises FileNotFoundError offline.
    """
    if corpus_dir:
        raise FileNotFoundError(f"real corpus path not available offline: {corpus_dir}")
    states = load_golden(golden_path)
    season = name.replace("nba_", "").replace("_", "-")  # nba_2023_24 -> 2023-24
    filt = [s for s in states if s.get("season") == season]
    return filt if filt else states

def run_gate_in_process(predict_fn: Callable, states: Optional[List[dict]] = None,
                        golden_path: Optional[str] = None,
                        corpus_dir: Optional[str] = None) -> List[dict]:
    """Return scoreboard rows WITHOUT sys.exit (for tests + embedding). When corpus_dir
    is set (real --corpus path), _load_states raises FileNotFoundError offline -> every
    slot is CORPUS_ABSENT and the gate fails closed (empty measured set)."""
    rows: List[dict] = []
    n_trials = len(CORPORA)
    for name in CORPORA:
        try:
            st = states if states is not None else _load_states(name, golden_path, corpus_dir)
            row = evaluate_corpus(name, predict_fn, st)
            row["n_trials_this_sweep"] = n_trials
            rows.append(row)
        except FileNotFoundError:
            rows.append({"corpus": name, "status": "CORPUS_ABSENT (skip)",
                         "n_trials_this_sweep": n_trials})
        except AssertionError as exc:
            if "LEAK" in str(exc):
                rows.append({"corpus": name, "leaked": True, "regressed": True,
                             "status": "LEAK", "n_trials_this_sweep": n_trials})
            else:
                raise
    measured = [r for r in rows if "_loss_diff" in r]
    if measured:
        alpha = DEFAULT_EPS
        bonferroni = eps_eff(alpha, n_trials)
        started = __import__("time").perf_counter()
        correction = "romano_wolf"
        power_loss = "none"
        try:
            rw = romano_wolf_stepdown([r["_loss_diff"] for r in measured],
                                      [r["_game_ids"] for r in measured], alpha=alpha,
                                      n_bootstrap=ROMANO_WOLF_BOOTSTRAPS)
            try:
                spa = hansen_spa([r["_loss_diff"] for r in measured],
                                 [r["_game_ids"] for r in measured], alpha=alpha,
                                 n_bootstrap=SPA_BOOTSTRAPS)
                spa_note = "available"
            except ValueError as exc:
                spa = None
                spa_note = "UNAVAILABLE: " + str(exc)
            elapsed = __import__("time").perf_counter() - started
            if elapsed > OFFLINE_BUDGET_SECONDS:
                raise TimeoutError("Romano-Wolf exceeded offline budget")
            adjusted = rw.adjusted_p
        except TimeoutError:
            elapsed = __import__("time").perf_counter() - started
            correction = "bonferroni"
            power_loss = "Romano-Wolf unavailable inside 60s; Bonferroni used"
            adjusted = tuple(min(1.0, r["dm_p"] * n_trials) for r in measured)
            spa = None
            spa_note = "UNAVAILABLE: Romano-Wolf timeout"
        for spa_index, (row, corrected_p) in enumerate(zip(measured, adjusted)):
            row.update({"bonferroni_eps": bonferroni, "corrected_method": correction,
                        "corrected_dm_p": corrected_p, "stepdown_seconds": elapsed,
                        "power_loss": power_loss,
                        "ship_eligible": bool(row["dm_stat"] > 0.0 and corrected_p <= alpha),
                        "spa_p": None if spa is None else spa.family_p,
                        "spa_stat": None if spa is None else spa.studentized_stats[spa_index],
                        "spa_note": spa_note})
            # S40b (prior red team, agent 1.1): _verdict runs BEFORE the multiplicity
            # correction exists, so BEATS_CLOSE was decided on the RAW dm p while
            # corrected_dm_p / ship_eligible were written here and never consulted. A
            # "beat" the corrected p does not support is not a beat; the raw label is
            # kept alongside so the downgrade is visible rather than silent.
            if row["verdict"] == "BEATS_CLOSE" and not row["ship_eligible"]:
                row["verdict_uncorrected"] = "BEATS_CLOSE"
                row["verdict"] = "MATCHES_CLOSE"
            row.pop("_loss_diff", None)
            row.pop("_game_ids", None)
    for slot in SKIPPED_SLOTS:
        rows.append({"corpus": slot, "status": "CORPUS_ABSENT (skip)",
                     "n_trials_this_sweep": n_trials})
    return rows


def gate_exit_code(rows: List[dict]) -> int:
    measured = [r for r in rows if "regressed" in r]
    fail = (any(r.get("regressed") for r in measured)
            or any(r.get("leaked") for r in rows)
            or not measured)                 # empty measured -> fail-closed
    return 1 if fail else 0

def _fmt(x, w=8):
    return f"{x:>{w}.4f}" if isinstance(x, (int, float)) else f"{str(x):>{w}}"


def _print_scoreboard(rows: List[dict]) -> None:
    print("eval gate -- calibration vs Shin-devigged close (BSS primary)")
    print("-" * 96)
    hdr = (f"{'corpus':<13}{'n':>5}{'brier_m':>9}{'brier_c':>9}{'bss':>8}"
           f"{'ece':>8}{'sharp':>8}{'dm_p':>8}{'K':>4}  {'verdict':<14}{'regr':>5}")
    print(hdr)
    print("-" * 96)
    for r in rows:
        if "status" in r and "n" not in r:
            print(f"{r['corpus']:<13}{'--':>5}  {r['status']}")
            continue
        print(f"{r['corpus']:<13}{r['n']:>5}"
              f"{_fmt(r['brier_model'], 9)}{_fmt(r['brier_close'], 9)}{_fmt(r['bss'])}"
              f"{_fmt(r['ece'])}{_fmt(r['sharpness'])}{_fmt(r['dm_p'])}{r['n_trials_this_sweep']:>4}  "
              f"{r['verdict']:<14}{('YES' if r['regressed'] else 'no'):>5}")
    print("-" * 96)
    print("GOLDEN FIXTURE = SYNTHETIC ANCHOR (not a real calibration claim); "
          "blocks on REGRESSION/LEAK only")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="eval gate: calibration vs devigged close")
    ap.add_argument("--golden", action="store_true",
                    help="run offline on the committed synthetic golden fixture")
    ap.add_argument("--corpus", default=None,
                    help="path to a real corpus dir (data/domains/<sport>); human-run")
    args = ap.parse_args(argv)
    # offline --golden NEVER imports proof_nba; real --corpus wires it (not run offline)
    predict_fn = _load_model_predictor() if args.corpus else offline_predict_fn
    rows = run_gate_in_process(predict_fn, golden_path=None, corpus_dir=args.corpus)
    _print_scoreboard(rows)
    return gate_exit_code(rows)


if __name__ == "__main__":
    sys.exit(main())
