"""scripts.platformkit.eval_gate.s58_e2_slice_trial -- S58 trial 1: MLB e2_regime leak-free vs
e4_blend leak-free on e2's OWN covered slice (charged T2, one ledger row, serial).

Arms are the S06 game-first-date builders (stacker.e2_gd_series / e4_gd_series), so both
series are OOF with per-fold game-disjoint asserts (S36). SEAL -> CHARGE -> compute (Q1/Q2):
the appended ledger row's k_cumulative is the only K used. The factory path (tiers.run_tier)
does NOT fit a per-tick in-game comparison -- cpcv_evaluate pools one prediction per event --
so the charge goes through _charge_ledger with the S13 fields and dual_bar_verdict is applied
by hand. Family "ingame_mlb_arms" is NOT in the frozen FWER partition: the family bar is a
family of one and labelled so; under tiers it would be NOT_IN_FROZEN_FAMILIES. Calibration
language only. Prereg: docs/evidence/harness/S58_TRIAL1_PREREG_2026-09-03.md.
Per-file test: python -m pytest tests/platformkit/eval_gate/test_s58_e2_slice_trial.py -q
"""
from __future__ import annotations

import hashlib, json, math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from scripts.platformkit.combo.fwer_budget import min_corpora_eff
from scripts.platformkit.eval_gate.backtest_runner import _charge_ledger
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.eval_gate.family_bars import dual_bar_verdict, render_bars
from scripts.platformkit.eval_gate.pbo import cscv_pbo
from scripts.platformkit.eval_gate.stacker import _finite, _first_dates, brier, e2_gd_series, e4_gd_series
from scripts.platformkit.ingame.gap_effective_n import effective_sample_size

REPO = Path(__file__).resolve().parents[3]
LEDGER = REPO / "data" / "cache" / "eval_gate" / "backtest_fwer.jsonl"
PREREG = REPO / "docs" / "evidence" / "harness" / "S58_TRIAL1_PREREG_2026-09-03.md"
PREREG_SHA256 = "5c5238e611baef75e2eb36fdfc1b63e36d9ba902ee80ea1fa9842e8b8a378de5"  # sealed first, 112856f47
SPEC_ID = "scripts.platformkit.eval_gate.s58_e2_slice_trial:mlb_e2_slice_v1"
FAMILY, TIER, START, END = "ingame_mlb_arms", "T2", "2026-06-28", "2026-07-12"
BAR, ALPHA = 0.004, 0.05                       # never move (Q3)
SLICE = (6579, 157)                            # ticks / games asserted BEFORE the charge
REPRO = {"e2_gd": 0.254350980569169, "e4_gd_scored47104": 0.206785778212713}
Series = List[Optional[float]]


def score_slice(ticks: Sequence[dict], cand: Series, inc: Series, idxs: Sequence[int], k: int,
                *, extra: Optional[Dict[str, Series]] = None, prior_p: Sequence[float] = ()) -> dict:
    """Paired per-tick comparison on `idxs`; d > 0 means the candidate is better. Pure."""
    idxs = sorted(idxs, key=lambda i: (str(ticks[i]["timestamp"]), str(ticks[i]["game"]), i))
    games = [str(ticks[i]["game"]) for i in idxs]
    y = np.array([float(ticks[i]["outcome"]) for i in idxs])
    p_c, p_i = (np.array([float(s[i]) for i in idxs]) for s in (cand, inc))
    l_c, l_i = (p_c - y) ** 2, (p_i - y) ** 2
    b_c, b_i, d = float(l_c.mean()), float(l_i.mean()), l_i - l_c
    dm = diebold_mariano(d.tolist(), games)
    raw_p = float(dm.p_value)
    bars = dual_bar_verdict(raw_p, k, list(prior_p) + [raw_p], alpha=ALPHA, family=None)
    bars["bars_line"], bars["family"] = render_bars(bars), FAMILY + " (NOT frozen; family of one)"
    improvement = b_i - b_c
    conds = {"improvement_ge_bar": improvement >= BAR, "dm_ci_excludes_0_favouring_candidate": dm.ci95[0] > 0.0,
             "deflated_p_lt_alpha": bool(bars["global_pass"]), "family_bar_pass": bool(bars["family_pass"])}
    verdict = "AHEAD" if all(conds.values()) else ("BEHIND" if b_c > b_i else "NULL")
    ess = effective_sample_size(pd.DataFrame({"game": games, "loss_differential": d}))
    cols = {"candidate": p_c, "incumbent": p_i}
    for name, s in (extra or {}).items():
        if all(_finite(s[i]) for i in idxs): cols[name] = np.array([float(s[i]) for i in idxs])  # noqa: E701
    pbo = cscv_pbo(np.column_stack(list(cols.values())), y.astype(int))
    return {"n_ticks": len(idxs), "n_games": len(set(games)), "k_at_launch": int(k),
            "brier": {"candidate_e2_gd": b_c, "incumbent_e4_gd_slice": b_i,
                      **{n: float(brier(v, y)) for n, v in cols.items() if n not in ("candidate", "incumbent")}},
            "improvement": improvement, "bar_improvement": BAR, "conditions": conds, "verdict": verdict,
            "dm": {"stat": float(dm.dm_stat), "p_raw": raw_p, "ci95": [float(dm.ci95[0]), float(dm.ci95[1])],
                   "n_clusters": int(dm.n_clusters)},
            "deflated_p": float(bars["deflated_p"]), "bars": bars,
            "pbo": {"pbo": float(pbo.pbo), "n_obs": int(pbo.n_obs), "n_splits": int(pbo.n_splits), "configs": list(cols)},
            "ess_scored_differential": {kk: float(vv) for kk, vv in ess.items()},
            "min_corpora_eff_at_launch_k": int(min_corpora_eff(1, k)), "single_window": True}


def run_trial(ticks, cand: Series, inc: Series, idxs: Sequence[int], *, ledger_path: Path,
              prereg_path: Path = PREREG, prereg_sha256: str = PREREG_SHA256, repro: Sequence[tuple] = (),
              extra=None, out_path: Optional[Path] = None, series_path: Optional[Path] = None) -> dict:
    """SEAL -> CHARGE (one row, S13 fields) -> reproduce arms -> score. Nothing scored before the row."""
    seal = hashlib.sha256(Path(prereg_path).read_bytes()).hexdigest()
    if seal != prereg_sha256: raise AssertionError("prereg sha mismatch: %s != %s" % (seal, prereg_sha256))  # noqa: E701
    row = _charge_ledger(Path(ledger_path), SPEC_ID, "mlb", START, END, family=FAMILY, tier=TIER,
                         hypothesis_hash=hashlib.sha256(SPEC_ID.encode()).hexdigest(), prereg_sha256=seal)
    k = int(row["k_cumulative"])                                       # the ONLY K used
    for name, series, ridx, target in repro:
        got = brier([float(series[i]) for i in ridx], [float(ticks[i]["outcome"]) for i in ridx])
        assert abs(got - target) < 1e-9, "ARM REPRODUCTION FAILED %s: %.15f vs %.15f (n=%d)" % (name, got, target, len(ridx))
    res = score_slice(ticks, cand, inc, idxs, k, extra=extra)
    first = _first_dates(ticks)
    weeks = sorted({"%04d-W%02d" % datetime.fromisoformat(first[str(ticks[i]["game"])]).isocalendar()[:2] for i in idxs})
    res.update({"generated_at": datetime.now(timezone.utc).isoformat(), "prereg": str(prereg_path), "prereg_sha256": seal,
                "ledger_row": dict(row), "spec_id": SPEC_ID, "family": FAMILY, "tier": TIER,
                "partition": {"basis": "iso_week", "verdict_blocks": weeks, "screen_blocks": [],
                              "note": "e2_regime was never screened on any row; the whole slice is VERDICT (prereg)"},
                "arm_reproduction": [{"name": n, "target": t, "n": len(r)} for n, _, r, t in repro],
                "per_tick_series": str(series_path) if series_path else None})
    if series_path:
        i2 = sorted(idxs, key=lambda i: (str(ticks[i]["timestamp"]), str(ticks[i]["game"]), i))
        pd.DataFrame({"tick_index": i2, "game": [str(ticks[i]["game"]) for i in i2],
                      "timestamp": [str(ticks[i]["timestamp"]) for i in i2], "y": [float(ticks[i]["outcome"]) for i in i2],
                      "e2_gd": [float(cand[i]) for i in i2], "e4_gd": [float(inc[i]) for i in i2]}).to_csv(series_path, index=False)
    if out_path:
        Path(out_path).write_text(json.dumps(res, indent=1, sort_keys=True, default=lambda o: o.item() if hasattr(o, "item") else str(o)), "ascii")
    return res


def main() -> int:
    """The REAL charged trial 1 (main repo, canonical ledger). Data prep before the charge is counts-only."""
    from scripts.platformkit import hedge_trial_arms as A
    from scripts.platformkit.ingame_replay_scoreboard import discover_store
    ticks, features = A.load_corpus(discover_store(REPO / "data" / "cache"), "mlb")
    raw: Series = [float(t["model_prob"]) for t in ticks]
    e4g, e2g = e4_gd_series(ticks, features), e2_gd_series(ticks)
    e2o, e4o = A.e2_regime_series(ticks), A.e4_blend_series(ticks, features)
    hedge_e4 = A.hedge_series(ticks, {"e4_blend": e4o}, 371)
    scored = [i for i, t in enumerate(ticks) if _finite(hedge_e4[i]) and _finite(t.get("market_prob"))]
    e2i = [i for i in range(len(ticks)) if _finite(e2g[i]) and _finite(e2o[i]) and _finite(ticks[i].get("market_prob"))]
    idxs = [i for i, t in enumerate(ticks) if _finite(e2g[i]) and _finite(t.get("market_prob"))]
    assert all(_finite(e4g[i]) for i in idxs), "e4_gd absent on the e2 slice"
    assert (len(idxs), len({str(ticks[i]["game"]) for i in idxs})) == SLICE, "denominator drift"
    assert (len(scored), len(e2i)) == (47104, 6579), "reproduction denominators drift"
    out = REPO / "data" / "cache" / "eval_gate"
    res = run_trial(ticks, e2g, e4g, idxs, ledger_path=LEDGER, extra={"raw_model": raw},
                    repro=[("e2_gd", e2g, e2i, REPRO["e2_gd"]), ("e4_gd_scored47104", e4g, scored, REPRO["e4_gd_scored47104"])],
                    out_path=out / "s58_trial1_e2_slice_2026-09-03.json", series_path=out / "s58_trial1_e2_slice_series_2026-09-03.csv")
    b = res["brier"]
    print("S58 trial1 %s | e2_gd %.15f vs e4_gd(slice) %.15f | improvement %.6f | dm_ci95 %s | deflated_p %.6g | K %d" % (
        res["verdict"], b["candidate_e2_gd"], b["incumbent_e4_gd_slice"], res["improvement"], res["dm"]["ci95"], res["deflated_p"], res["k_at_launch"]))
    print(res["bars"]["bars_line"]); print("pbo %.3f n_obs %d | ess %s" % (res["pbo"]["pbo"], res["pbo"]["n_obs"], res["ess_scored_differential"]))
    return 0


if __name__ == "__main__": raise SystemExit(main())  # noqa: E701
