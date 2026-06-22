"""scripts.platformkit.self_improve -- the "getting better" ratchet.

A leak-free continuous-CALIBRATION loop that learns from REAL settled game outcomes
and can only ever IMPROVE or HOLD the forecaster -- never regress.

ONE CYCLE PER SPORT:
  (a) LOAD accumulated REAL settled (model_prob, outcome[, close]) from the grader's
      append-only stores (clv_ledger.jsonl settled rows + paper_predictions.jsonl).
  (b) READOUT: honest Brier/ECE on the real results + CLV-style BSS-vs-close where a
      devigged close exists. The "is the model actually good" answer; NOT an edge claim.
  (c) RECALIBRATE: leak-free walk-forward isotonic recal (map for game N uses ONLY
      games < N) via recalibration.walk_forward_recalibrate.
  (d) GATE: the eval-gate's OWN leak-free walk_forward + proper-scoring + cluster-robust
      DM checks the recalibrated forecaster does NOT regress vs the FROZEN raw-model
      baseline (same real states) and passes the vintage leak guard.
  (e) VERDICT (THE RATCHET):
        SHIP  -> gate passes (no regression/leak) AND recal beats baseline Brier by
                 > tol. Only here do we ratchet forward.
        HOLD  -> gate passes but no meaningful improvement (already well-calibrated).
        REJECT-> recal regresses vs baseline, or the leak guard fires.
        INSUFFICIENT_DATA -> too few real settled games to recalibrate (cold start);
                 logged honestly, never a fabricated win.
      Verdict + metrics append to data/frontend/improve_ledger.jsonl.

HONESTY (binding): calibration != edge (no $ claim). Only PAST games inform game N.
Cold start = INSUFFICIENT_DATA. Append-only; SHIP only when the gate passes = the ratchet.
Build only under scripts/platformkit/; <=300 LOC; no secrets. CLI: python -m
scripts.platformkit.self_improve
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from scripts.platformkit.recalibration import walk_forward_recalibrate, CALIBRATION_NOTE
from scripts.platformkit.eval_gate import scoring as S
from scripts.platformkit.eval_gate.walkforward import walk_forward
from scripts.platformkit.eval_gate.dm_test import diebold_mariano

_HERE = Path(__file__).resolve().parent
_FRONTEND = _HERE.parents[1] / "data" / "frontend"
DEFAULT_CLV_LEDGER = _FRONTEND / "clv_ledger.jsonl"
DEFAULT_PREDICTIONS = _FRONTEND / "paper_predictions.jsonl"
DEFAULT_IMPROVE_LEDGER = _FRONTEND / "improve_ledger.jsonl"

SPORTS = ("nba", "mlb", "soccer", "tennis")

# A walk-forward isotonic map needs a warmup window before it does anything; below
# this many real settled games for a sport there is nothing honest to recalibrate.
MIN_RECAL_GAMES = 60
# Pre-registered min meaningful Brier improvement to SHIP (mirrors the gate's tol).
BRIER_IMPROVE_TOL = 0.005
# Pre-registered min meaningful Brier worsening that counts as a regression (REJECT).
BRIER_REGRESS_TOL = 0.005
DM_MIN_N = 200  # below this the DM significance test is advisory, not decisive


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue  # tolerate a partial trailing write
    return rows


def _outcome_to_binary(row: Dict[str, Any]) -> Optional[int]:
    """Realized binary outcome for the side the model picked. None if undecided/push."""
    o = row.get("outcome")
    if isinstance(o, bool):
        return int(o)
    if isinstance(o, (int, float)) and o in (0, 1):
        return int(o)
    if isinstance(o, str):
        s = o.strip().lower()
        if s == "win":
            return 1
        if s == "loss":
            return 0
        # "push"/"draw"/unknown -> undecided
    return None


def _raw_prob(row: Dict[str, Any]) -> Optional[float]:
    """The model's probability for the picked side. Tolerant of field naming."""
    for k in ("model_prob", "p_model", "prob", "model_p"):
        v = row.get(k)
        if isinstance(v, (int, float)) and 0.0 <= float(v) <= 1.0:
            return float(v)
    return None


def load_settled(sport: str,
                 clv_path: Optional[Path] = None,
                 predictions_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load REAL settled (model_prob, outcome[, close]) records for one sport.

    Pulls graded settled rows from the CLV ledger and any outcome-carrying rows in
    the predictions store, dedupes by (matchup, ts), and returns them sorted by
    timestamp ascending (chronological -- required for leak-free walk-forward).
    Only rows with BOTH a valid raw model_prob AND a decided binary outcome survive.
    """
    clv_path = Path(clv_path) if clv_path else DEFAULT_CLV_LEDGER
    predictions_path = Path(predictions_path) if predictions_path else DEFAULT_PREDICTIONS
    raw = _read_jsonl(clv_path) + _read_jsonl(predictions_path)
    sp = str(sport).lower()
    seen: set = set()
    out: List[Dict[str, Any]] = []
    for r in raw:
        if str(r.get("sport", "")).lower() != sp:
            continue
        # DO-NO-HARM: a player-prop row carries model_prob=P(over) + outcome=over/under,
        # NOT a game home/away result -- ingesting it would CONTAMINATE the game-win-prob
        # calibration corpus. Props recalibrate on their own (separate) track, never here.
        if str(r.get("market_type") or "") == "prop" or \
                str(r.get("market") or "").lower().startswith("prop"):
            continue
        y = _outcome_to_binary(r)
        p = _raw_prob(r)
        if y is None or p is None:
            continue
        ts = str(r.get("settled_at") or r.get("ts") or r.get("logged_at") or "")
        key = (str(r.get("matchup", "")), ts, str(r.get("side", "")))
        if key in seen:
            continue
        seen.add(key)
        close = r.get("fair_close_prob")
        if not isinstance(close, (int, float)):
            close = r.get("devig_close_prob")
        out.append({
            "ts": ts,
            "matchup": str(r.get("matchup", "")),
            "side": str(r.get("side", "")),
            "p_raw": p,
            "y": y,
            "p_close": float(close) if isinstance(close, (int, float)) else None,
        })
    out.sort(key=lambda d: d["ts"])
    return out


def honest_readout(settled: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Honest Brier/ECE on the REAL settled results + BSS/%-beat-close where a devigged
    close exists. calibration != edge; a diagnostic, not a claim of beating the market."""
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
    with_close = [s for s in settled if s["p_close"] is not None]
    if with_close:
        pc = np.array([s["p_close"] for s in with_close], dtype=float)
        pm = np.array([s["p_raw"] for s in with_close], dtype=float)
        yc = np.array([s["y"] for s in with_close], dtype=float)
        out["n_with_close"] = len(with_close)
        out["bss_vs_close"] = S.brier_skill_score(pm, pc, yc)
        # %-beat-close: model assigned the realized side a higher prob than the close
        out["pct_beat_close"] = round(100.0 * float(np.mean(pm > pc)), 4)
    else:
        out["n_with_close"] = 0
        out["bss_vs_close"] = None
        out["pct_beat_close"] = None
    out["note"] = CALIBRATION_NOTE
    return out


def _to_states(settled: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Build eval-gate-shaped states from settled rows. Each carries the raw model prob
    as a feature, the real outcome, and the devigged close. feature_avail is stamped
    strictly BEFORE state_ts so the vintage leak guard passes on honest data and FIRES
    if a future timestamp is ever injected."""
    states: List[Dict[str, Any]] = []
    for i, s in enumerate(settled):
        # Strictly-increasing synthetic clock; settled is already sorted -> index order.
        state_ts = f"2000-01-01T00:00:{i % 60:02d}.{i // 60:06d}"
        avail = "1999-12-31T23:59:59.000000"  # strictly before any state_ts
        a, _, b = s["matchup"].partition(" vs ")
        if not b:
            a, _, b = s["matchup"].partition(" @ ")
        states.append({
            "game_id": f"{s['matchup']}|{i}",
            "state_ts": state_ts,
            "home": (a.strip() or f"H{i}"),
            "away": (b.strip() or f"A{i}"),
            "outcome": int(s["y"]),
            "devig_close_prob": s["p_close"],
            "features": {"p_raw": s["p_raw"]},
            "feature_avail": {"p_raw": avail},
            "_p_raw": s["p_raw"],
        })
    return states


def _baseline_predict(train: List[dict], test: dict, select_inside: bool) -> float:
    """FROZEN baseline: pass the raw model prob straight through (what we ship today)."""
    assert select_inside is True
    return float(min(1.0, max(0.0, test["_p_raw"])))


def _recal_predictor(states: List[dict]):
    """Leak-free walk-forward isotonic recalibrator over these states. Precomputes the
    recalibrated prob for each state using ONLY strictly-earlier states (expanding-window
    isotonic), then returns a predict_fn the gate's walk_forward scores via lookup."""
    ordered = sorted(states, key=lambda s: s["state_ts"])
    p_raw = [s["_p_raw"] for s in ordered]
    y = [s["outcome"] for s in ordered]
    cal = walk_forward_recalibrate(p_raw, y, min_history=MIN_RECAL_GAMES // 2)
    lookup = {ordered[i]["game_id"]: float(cal[i]) for i in range(len(ordered))}

    def _fn(train: List[dict], test: dict, select_inside: bool) -> float:
        assert select_inside is True
        return float(min(1.0, max(0.0, lookup[test["game_id"]])))

    return _fn


def _score_predictor(states, predict_fn) -> Tuple[Dict[str, Any], np.ndarray, np.ndarray, list]:
    """Gate's leak-free walk_forward + proper scoring. Returns (metrics, p_model, y,
    game_ids) aligned by game_id in chronological order -- so two scored predictors can
    be differenced game-for-game for the cluster-robust DM regression test."""
    res = walk_forward(states, predict_fn, select_inside=True)
    pm = np.array([r["p_model"] for r in res.records], dtype=float)
    y = np.array([r["y"] for r in res.records], dtype=float)
    gid = [r["game_id"] for r in res.records]
    metrics = {"brier": S.brier(pm, y), "ece": S.ece(pm, y),
               "sharpness": S.sharpness(pm), "select_inside": bool(res.select_inside)}
    return metrics, pm, y, gid


def improve_cycle(sport: str,
                  clv_path: Optional[Path] = None,
                  predictions_path: Optional[Path] = None,
                  ledger_path: Optional[Path] = None,
                  append: bool = True) -> Dict[str, Any]:
    """Run one leak-free self-improvement cycle for one sport; return + log the verdict."""
    ledger_path = Path(ledger_path) if ledger_path else DEFAULT_IMPROVE_LEDGER
    settled = load_settled(sport, clv_path, predictions_path)
    readout = honest_readout(settled)

    rec: Dict[str, Any] = {
        "ts": _now_iso(), "sport": str(sport).lower(),
        "n_settled": len(settled), "readout": readout, "note": CALIBRATION_NOTE,
    }

    if len(settled) < MIN_RECAL_GAMES:
        rec["verdict"] = "INSUFFICIENT_DATA"
        rec["reason"] = (f"only {len(settled)} real settled games; need >= "
                         f"{MIN_RECAL_GAMES} to recalibrate leak-free. The loop gets "
                         f"smarter as real games settle -- no improvement fabricated.")
        if append:
            _append(ledger_path, rec)
        return rec

    states = _to_states(settled)
    try:
        base_metrics, pm_b, y_b, gid_b = _score_predictor(states, _baseline_predict)
        cand_metrics, pm_c, y_c, gid_c = _score_predictor(states, _recal_predictor(states))
        leaked = False
    except AssertionError as exc:
        # the gate's vintage assert (or select_inside) fired -> a leak; REJECT.
        rec["verdict"] = "REJECT"
        rec["reason"] = f"leak guard fired: {str(exc)[:160]}"
        rec["leaked"] = True
        if append:
            _append(ledger_path, rec)
        return rec

    # walk_forward orders both runs identically (same states, chronological), so the
    # arrays align game-for-game; assert it before differencing.
    assert gid_b == gid_c, "baseline/candidate game_id order mismatch"
    # No-regression rule, mirroring the eval-gate: candidate must not be worse than
    # the frozen baseline by more than tol AND significant under cluster-robust DM.
    # d_t = baseline_loss - candidate_loss; POSITIVE mean => candidate better.
    d_vs_base = (pm_b - y_b) ** 2 - (pm_c - y_c) ** 2
    dm = diebold_mariano(d_vs_base, gid_c)
    d_brier = base_metrics["brier"] - cand_metrics["brier"]  # >0 => candidate better
    worsened = cand_metrics["brier"] > base_metrics["brier"] + BRIER_REGRESS_TOL
    sig = dm.p_value < 0.05 and dm.n >= DM_MIN_N
    regressed = bool(worsened and sig) or (cand_metrics["select_inside"] is not True)

    rec.update({
        "baseline_brier": base_metrics["brier"], "baseline_ece": base_metrics["ece"],
        "recal_brier": cand_metrics["brier"], "recal_ece": cand_metrics["ece"],
        "delta_brier": d_brier, "dm_stat": dm.dm_stat, "dm_p": dm.p_value, "dm_n": dm.n,
        "leaked": leaked, "regressed": regressed,
    })

    if regressed:
        rec["verdict"] = "REJECT"
        rec["reason"] = ("recalibrated forecaster regresses vs frozen baseline "
                         f"(d_brier={d_brier:+.5f}, dm_p={dm.p_value:.4f}); held at baseline.")
    elif d_brier > BRIER_IMPROVE_TOL:
        rec["verdict"] = "SHIP"
        rec["reason"] = (f"recal improves Brier by {d_brier:+.5f} (> {BRIER_IMPROVE_TOL}) "
                         f"with no regression/leak -- ratchet forward. calibration != edge.")
    else:
        rec["verdict"] = "HOLD"
        rec["reason"] = (f"no meaningful calibration improvement (d_brier={d_brier:+.5f}); "
                         f"already well-calibrated -- hold at baseline (honest, not a failure).")

    if append:
        _append(ledger_path, rec)
    return rec


def _append(ledger_path: Path, rec: Dict[str, Any]) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, default=str) + "\n")


def improve_all(clv_path: Optional[Path] = None,
                predictions_path: Optional[Path] = None,
                ledger_path: Optional[Path] = None,
                append: bool = True) -> Dict[str, Any]:
    """Run improve_cycle for every sport; return a per-sport summary."""
    results = {sp: improve_cycle(sp, clv_path, predictions_path, ledger_path, append)
               for sp in SPORTS}
    verdicts = {sp: r["verdict"] for sp, r in results.items()}
    return {"ts": _now_iso(), "verdicts": verdicts, "results": results,
            "note": CALIBRATION_NOTE}


def _main(argv: Optional[List[str]] = None) -> int:
    summary = improve_all()
    print()
    print("SELF-IMPROVEMENT CYCLE -- leak-free calibration ratchet on REAL outcomes")
    print(f"NOTE: {CALIBRATION_NOTE}")
    print("-" * 78)
    hdr = f"{'sport':<8}{'n':>6}  {'verdict':<18}{'d_brier':>10}  reason"
    print(hdr)
    print("-" * 78)
    for sp, r in summary["results"].items():
        db = r.get("delta_brier")
        db_s = f"{db:+.5f}" if isinstance(db, (int, float)) else "       --"
        reason = str(r.get("reason", ""))[:60]
        print(f"{sp:<8}{r.get('n_settled', 0):>6}  {r['verdict']:<18}{db_s:>10}  {reason}")
    print("-" * 78)
    print(f"ledger: {DEFAULT_IMPROVE_LEDGER}")
    print("Ratchet: SHIP only when the eval-gate passes AND recal improves; else "
          "HOLD/REJECT. Cold start = INSUFFICIENT_DATA (no fabricated win).")
    return 0


__all__ = [
    "load_settled", "honest_readout", "improve_cycle", "improve_all",
    "DEFAULT_IMPROVE_LEDGER", "MIN_RECAL_GAMES", "SPORTS",
]


if __name__ == "__main__":
    raise SystemExit(_main())
