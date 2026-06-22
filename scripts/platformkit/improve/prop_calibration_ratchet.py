"""scripts.platformkit.improve.prop_calibration_ratchet -- the PROPS "gets better" ratchet.

The prop twin of scripts.platformkit.self_improve (which handles GAME moneylines and
EXCLUDES props). Learns from REAL settled-prop outcomes (model_prob = P(picked over/under
side); outcome = win/loss) and can only ever IMPROVE or HOLD the prop forecaster -- never
regress, never market-follow.

ONE CYCLE PER SPORT:
  (a) LOAD settled prop rows (market_type='prop') for the sport: p_raw=model_prob,
      y=1 if the picked side won else 0 (push dropped), p_market=devigged market prob.
  (b) READOUT: honest Brier/ECE on the realized over/under results + a model-vs-market
      Brier/BSS comparison (calibration readout, NOT an edge claim; props have no true
      close so this market prob is the only available reference).
  (c) RECALIBRATE: leak-free walk-forward isotonic recal on OUTCOMES (never reads the
      market) -> the recal is STRUCTURALLY incapable of market-following.
  (d) GATE (the SAME eval-gate machinery as self_improve): leak-free walk_forward +
      proper scoring + cluster-robust DM vs the frozen raw baseline, PLUS a PLANTED
      NULL (isotonic on SHUFFLED outcomes) that MUST reject, PLUS a shrink-toward-market
      do-no-harm control that must yield NO improvement over the recal.
  (e) VERDICT (THE RATCHET):
        SHIP -> gate passes, planted-null rejects, recal beats baseline Brier by >tol
                AND the cluster-robust DM is significant.
        HOLD -> gate passes but no meaningful improvement (already well-calibrated).
        REJECT -> recal regresses / leak fires / the PLANTED NULL ships (gate untrustworthy).
        INSUFFICIENT_DATA -> too few settled props (cold start / offseason). Honest, never faked.
      Verdict + metrics append to data/frontend/prop_improve_ledger.jsonl.

HONESTY (binding): calibration != edge (no $ claim). Props have no true close -> CLV
unavailable; this loop scores OUTCOME calibration only. The shipped forecaster's SHIP
verdict is provably INVARIANT to market_prob -> the market-follow trap is structurally
impossible (proved in the per-file test). PROPOSE/RECORD only: NEVER arms serving, flips a
flag, or writes data/registry/. Build only under scripts/platformkit/; <=300 LOC; ASCII.
CLI: python -m scripts.platformkit.improve.prop_calibration_ratchet
Per-file test: tests/platformkit/improve/test_prop_calibration_ratchet.py
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from scripts.platformkit.recalibration import walk_forward_recalibrate, CALIBRATION_NOTE
from scripts.platformkit.eval_gate import scoring as S
from scripts.platformkit.eval_gate.dm_test import diebold_mariano
from scripts.platformkit.self_improve import (
    _read_jsonl, _outcome_to_binary, _raw_prob,
    _baseline_predict, _recal_predictor, _score_predictor, _append,
    DEFAULT_CLV_LEDGER, MIN_RECAL_GAMES, BRIER_IMPROVE_TOL,
    BRIER_REGRESS_TOL, DM_MIN_N,
)

_HERE = Path(__file__).resolve().parent
_REPO = _HERE.parents[2]
DEFAULT_PROP_LEDGER = _REPO / "data" / "frontend" / "prop_improve_ledger.jsonl"

# Sports whose props can settle today; cold sports -> INSUFFICIENT_DATA (honest).
PROP_SPORTS = ("mlb", "soccer_intl", "nba", "soccer", "tennis")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_settled_props(sport: str,
                       clv_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load REAL settled PROP rows (market_type='prop') for one sport.

    Inverse of self_improve.load_settled's do-no-harm filter: here we keep ONLY prop
    rows. p_raw = model_prob (P of the picked over/under side); y = 1 if that side won
    else 0 (push dropped); p_market = the devigged market prob for the SAME side.
    Deduped by (bet_id|market, ts) and sorted chronologically (leak-free walk-forward).
    """
    clv_path = Path(clv_path) if clv_path else DEFAULT_CLV_LEDGER
    raw = _read_jsonl(clv_path)
    sp = str(sport).lower()
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for r in raw:
        if str(r.get("sport", "")).lower() != sp:
            continue
        if str(r.get("market_type") or "") != "prop":
            continue  # PROPS ONLY
        if str(r.get("status") or "") != "settled":
            continue
        y = _outcome_to_binary(r)  # win=1 / loss=0 / push->None
        p = _raw_prob(r)           # model_prob (picked side)
        if y is None or p is None:
            continue
        ts = str(r.get("settled_at") or r.get("ts") or "")
        key = (str(r.get("bet_id") or r.get("market") or ""), ts)
        if key in seen:
            continue
        seen.add(key)
        mp = r.get("market_prob")
        out.append({
            "ts": ts,
            "market": str(r.get("market") or ""),
            "p_raw": p,
            "y": int(y),
            "p_market": float(mp) if isinstance(mp, (int, float)) else None,
        })
    out.sort(key=lambda d: d["ts"])
    return out


def honest_readout(settled: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Honest Brier/ECE on REAL settled prop results + a model-vs-market comparison.
    calibration != edge; a diagnostic, never a claim of beating the market."""
    n = len(settled)
    p = np.array([s["p_raw"] for s in settled], dtype=float)
    y = np.array([s["y"] for s in settled], dtype=float)
    out: Dict[str, Any] = {
        "n": n,
        "raw_brier": (S.brier(p, y) if n else None),
        "raw_ece": (S.ece(p, y) if n else None),
        "base_rate": (float(y.mean()) if n else None),
        "sharpness": (S.sharpness(p) if n else None),
    }
    wm = [s for s in settled if s["p_market"] is not None]
    if wm:
        pm = np.array([s["p_market"] for s in wm], dtype=float)
        pmod = np.array([s["p_raw"] for s in wm], dtype=float)
        ym = np.array([s["y"] for s in wm], dtype=float)
        out["n_with_market"] = len(wm)
        out["market_brier"] = S.brier(pm, ym)
        out["model_brier_on_market_subset"] = S.brier(pmod, ym)
        out["bss_vs_market"] = S.brier_skill_score(pmod, pm, ym)
    else:
        out["n_with_market"] = 0
        out["market_brier"] = None
        out["bss_vs_market"] = None
    out["note"] = CALIBRATION_NOTE
    return out


def _to_states(settled: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Eval-gate-shaped states from settled prop rows (mirrors self_improve._to_states,
    additionally carrying _p_market for the do-no-harm shrink control). feature_avail is
    stamped strictly BEFORE state_ts so the vintage leak guard passes on honest data and
    FIRES if a future timestamp is ever injected."""
    states: List[Dict[str, Any]] = []
    for i, s in enumerate(settled):
        state_ts = f"2000-01-01T00:00:{i % 60:02d}.{i // 60:06d}"
        avail = "1999-12-31T23:59:59.000000"
        states.append({
            "game_id": f"{s['market']}|{i}",
            "state_ts": state_ts,
            "home": f"H{i}", "away": f"A{i}",
            "outcome": int(s["y"]),
            "devig_close_prob": s["p_market"],
            "features": {"p_raw": s["p_raw"]},
            "feature_avail": {"p_raw": avail},
            "_p_raw": s["p_raw"],
            "_p_market": s["p_market"],
        })
    return states


def _null_recal_predictor(states: List[dict], seed: int = 12345):
    """PLANTED NULL: leak-free walk-forward isotonic recal fit on SHUFFLED outcomes.

    A map learned from permuted labels carries NO real signal; scored against the REAL
    outcomes it must NOT beat the baseline. If it does ('null ships'), the gate is
    overfitting and the whole cycle is REJECTED (the gate is untrustworthy)."""
    ordered = sorted(states, key=lambda s: s["state_ts"])
    p_raw = [s["_p_raw"] for s in ordered]
    y = np.array([s["outcome"] for s in ordered], dtype=float)
    rng = np.random.default_rng(seed)
    y_shuf = y[rng.permutation(len(y))]
    cal = walk_forward_recalibrate(p_raw, list(y_shuf), min_history=MIN_RECAL_GAMES // 2)
    lookup = {ordered[i]["game_id"]: float(cal[i]) for i in range(len(ordered))}

    def _fn(train: List[dict], test: dict, select_inside: bool) -> float:
        assert select_inside is True
        return float(min(1.0, max(0.0, lookup[test["game_id"]])))

    return _fn


def _market_shrink_predictor(states: List[dict], w: float = 0.5):
    """DO-NO-HARM control: shrink the leak-free recal output TOWARD the contemporaneous
    devigged market prob (available at bet time -> no leak). Once we have calibrated
    against outcomes, the market must add NO improvement (else market info -- not our
    model -- is the source of the gain). A row with no market prob falls back to the
    pure recal (no shrink)."""
    ordered = sorted(states, key=lambda s: s["state_ts"])
    p_raw = [s["_p_raw"] for s in ordered]
    y = [s["outcome"] for s in ordered]
    cal = walk_forward_recalibrate(p_raw, y, min_history=MIN_RECAL_GAMES // 2)
    lookup: Dict[str, float] = {}
    for i, s in enumerate(ordered):
        pm = s.get("_p_market")
        rc = float(cal[i])
        blend = (w * float(pm) + (1.0 - w) * rc) if isinstance(pm, (int, float)) else rc
        lookup[s["game_id"]] = float(min(1.0, max(0.0, blend)))

    def _fn(train: List[dict], test: dict, select_inside: bool) -> float:
        assert select_inside is True
        return lookup[test["game_id"]]

    return _fn


def improve_cycle(sport: str,
                  clv_path: Optional[Path] = None,
                  ledger_path: Optional[Path] = None,
                  append: bool = True,
                  null_seed: int = 12345) -> Dict[str, Any]:
    """Run one leak-free prop-calibration cycle for one sport; return + log the verdict."""
    ledger_path = Path(ledger_path) if ledger_path else DEFAULT_PROP_LEDGER
    settled = load_settled_props(sport, clv_path)
    readout = honest_readout(settled)
    rec: Dict[str, Any] = {
        "ts": _now_iso(), "sport": str(sport).lower(), "market_type": "prop",
        "n_settled": len(settled), "readout": readout, "note": CALIBRATION_NOTE,
    }

    if len(settled) < MIN_RECAL_GAMES:
        rec["verdict"] = "INSUFFICIENT_DATA"
        rec["reason"] = (f"only {len(settled)} real settled props; need >= "
                         f"{MIN_RECAL_GAMES} to recalibrate leak-free. The loop gets "
                         f"smarter as real props settle -- no improvement fabricated.")
        if append:
            _append(ledger_path, rec)
        return rec

    states = _to_states(settled)
    try:
        base_m, pm_b, y_b, gid_b = _score_predictor(states, _baseline_predict)
        cand_m, pm_c, y_c, gid_c = _score_predictor(states, _recal_predictor(states))
        null_m, _pn, _yn, gid_n = _score_predictor(states, _null_recal_predictor(states, null_seed))
        shr_m, _ps, _ys, gid_s = _score_predictor(states, _market_shrink_predictor(states))
    except AssertionError as exc:
        rec["verdict"] = "REJECT"
        rec["reason"] = f"leak guard fired: {str(exc)[:160]}"
        rec["leaked"] = True
        if append:
            _append(ledger_path, rec)
        return rec

    assert gid_b == gid_c == gid_n == gid_s, "predictor game_id order mismatch"
    d_vs_base = (pm_b - y_b) ** 2 - (pm_c - y_c) ** 2
    dm = diebold_mariano(d_vs_base, gid_c)
    d_brier = base_m["brier"] - cand_m["brier"]            # >0 => recal better
    null_delta = base_m["brier"] - null_m["brier"]          # >0 => null "ships" (BAD)
    shrink_delta = cand_m["brier"] - shr_m["brier"]         # >0 => market beats our recal
    worsened = cand_m["brier"] > base_m["brier"] + BRIER_REGRESS_TOL
    sig = dm.p_value < 0.05 and dm.n >= DM_MIN_N
    regressed = bool(worsened and sig) or (cand_m["select_inside"] is not True)
    null_shipped = null_delta > BRIER_IMPROVE_TOL
    market_follow_safe = shrink_delta <= BRIER_IMPROVE_TOL

    rec.update({
        "baseline_brier": base_m["brier"], "baseline_ece": base_m["ece"],
        "recal_brier": cand_m["brier"], "recal_ece": cand_m["ece"],
        "null_brier": null_m["brier"], "market_shrink_brier": shr_m["brier"],
        "delta_brier": d_brier, "null_delta_brier": null_delta,
        "market_shrink_delta_brier": shrink_delta,
        "dm_stat": dm.dm_stat, "dm_p": dm.p_value, "dm_n": dm.n,
        "regressed": regressed, "null_shipped": null_shipped,
        "market_follow_safe": market_follow_safe,
    })

    if null_shipped:
        rec["verdict"] = "REJECT"
        rec["reason"] = ("PLANTED NULL shipped (isotonic on SHUFFLED outcomes improved "
                         f"Brier by {null_delta:+.5f} > {BRIER_IMPROVE_TOL}); the gate is "
                         "overfitting -> reject the whole cycle (no recal shipped).")
    elif regressed:
        rec["verdict"] = "REJECT"
        rec["reason"] = ("recalibrated prop forecaster regresses vs frozen baseline "
                         f"(d_brier={d_brier:+.5f}, dm_p={dm.p_value:.4f}); held at baseline.")
    elif d_brier > BRIER_IMPROVE_TOL and sig:
        mf = "" if market_follow_safe else (" NOTE: shrink-toward-market also improves "
                                            f"({shrink_delta:+.5f}) -- market has residual info.")
        rec["verdict"] = "SHIP"
        rec["reason"] = (f"recal improves Brier by {d_brier:+.5f} (> {BRIER_IMPROVE_TOL}, "
                         f"dm_p={dm.p_value:.4f}) with no regression/leak; planted-null "
                         f"rejected -- ratchet forward. calibration != edge.{mf}")
    else:
        rec["verdict"] = "HOLD"
        rec["reason"] = (f"no meaningful/ significant calibration improvement "
                         f"(d_brier={d_brier:+.5f}, dm_p={dm.p_value:.4f}); already "
                         f"well-calibrated -- hold at baseline (honest, not a failure).")

    if append:
        _append(ledger_path, rec)
    return rec


def improve_all(clv_path: Optional[Path] = None,
                ledger_path: Optional[Path] = None,
                append: bool = True) -> Dict[str, Any]:
    """Run improve_cycle for every prop sport; return a per-sport summary."""
    results = {sp: improve_cycle(sp, clv_path, ledger_path, append) for sp in PROP_SPORTS}
    verdicts = {sp: r["verdict"] for sp, r in results.items()}
    return {"ts": _now_iso(), "verdicts": verdicts, "results": results,
            "note": CALIBRATION_NOTE}


def _main(argv: Optional[List[str]] = None) -> int:
    summary = improve_all()
    print()
    print("PROP CALIBRATION RATCHET -- leak-free Brier ratchet on REAL settled props")
    print(f"NOTE: {CALIBRATION_NOTE}")
    print("-" * 78)
    hdr = f"{'sport':<11}{'n':>6}  {'verdict':<18}{'d_brier':>10}  reason"
    print(hdr)
    print("-" * 78)
    for sp, r in summary["results"].items():
        db = r.get("delta_brier")
        db_s = f"{db:+.5f}" if isinstance(db, (int, float)) else "       --"
        reason = str(r.get("reason", ""))[:54]
        print(f"{sp:<11}{r.get('n_settled', 0):>6}  {r['verdict']:<18}{db_s:>10}  {reason}")
    print("-" * 78)
    print(f"ledger: {DEFAULT_PROP_LEDGER}")
    print("Ratchet: SHIP only when the eval-gate passes, the planted-null rejects, AND "
          "recal improves; else HOLD/REJECT. Cold start = INSUFFICIENT_DATA. PROPOSE only.")
    return 0


__all__ = [
    "load_settled_props", "honest_readout", "improve_cycle", "improve_all",
    "DEFAULT_PROP_LEDGER", "PROP_SPORTS",
]


if __name__ == "__main__":
    raise SystemExit(_main())
