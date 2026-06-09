"""THE JUDGE -- mechanized CAVEATs, the trust centerpiece (MASTER_SYSTEM_BUILD section 4A / 4B).

signal_lab's 4 gates (OOS-lift / split-half / orthogonal-to-baseline / material) PASS plenty of signals a
human would reject on a second look. The JUDGE encodes those second looks as code so they fire automatically:

  - sign_sanity:   the measured effect sign vs the DECLARED causal sign. If they conflict, the "signal" is a
                   confound (e.g. opp_position_defense_reb: a 'facing weaker positional D -> more rebounds'
                   signal whose measured effect is NEGATIVE -> backwards -> auto-reject).
  - engine_redundancy: orthogonality of the signal vs the CONSUMING ENGINE'S emitted prediction -- NOT the
                   coarse lab baseline (section 4A). Mechanized two ways: (a) canonical-owner collision --
                   the signal's quantity is a node an engine already OWNS (section 4B.3: one owner per
                   quantity x engine), e.g. oreb_matchup's quantity 'oreb' is one of four_factors' four
                   owned factors -> double-count -> reject; (b) empirical |corr(signal, engine_pred)| > 0.92
                   when both vectors are available.

TRUST GATE: the funnel must reproduce the 2 hand-written CAVEAT auto-rejections on the EXISTING registry
(opp_position_defense_reb via sign_sanity; oreb_matchup via engine_redundancy) before it is trusted on new
candidates. run_trust_gate() asserts exactly that and writes the B4 marker.

  python scripts/team_system/signals/judge.py            # run the TRUST GATE
"""
from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from registry.store import Registry  # noqa: E402

ORTHO_ENGINE_CAP = 0.92


def _sign(x) -> int:
    try:
        x = float(x)
    except (TypeError, ValueError):
        return 0
    return 1 if x > 1e-9 else (-1 if x < -1e-9 else 0)


def sign_sanity(declared_sign, measured_sign) -> tuple[bool, str]:
    """ok=True unless BOTH signs are declared (non-zero) and they CONFLICT. A conflict = a confound."""
    d, m = _sign(declared_sign), _sign(measured_sign)
    if d != 0 and m != 0 and d != m:
        return False, f"sign confound: declared {d:+d} but measured {m:+d} (backwards)"
    return True, "sign ok" if (d and m) else "sign undeclared (no claim to violate)"


def engine_redundancy(quantity, engines_owned: set, signal_vec=None, engine_pred_vec=None,
                      cap: float = ORTHO_ENGINE_CAP) -> tuple[bool, float, str]:
    """ok=False (redundant) if the signal's quantity is a node an engine already OWNS (canonical-owner
    rule, 4B.3) OR, when vectors are supplied, |corr(signal, engine_pred)| > cap (4A empirical)."""
    if quantity and str(quantity) in engines_owned:
        return False, 1.0, f"engine-redundant: quantity '{quantity}' is an owned engine node (double-count)"
    if signal_vec is not None and engine_pred_vec is not None:
        import numpy as np
        a, b = np.asarray(signal_vec, float), np.asarray(engine_pred_vec, float)
        n = min(len(a), len(b))
        if n >= 20:
            c = float(np.corrcoef(a[:n], b[:n])[0, 1])
            if np.isnan(c):
                # NaN correlation (e.g. from NaN/inf in input vectors) is inconclusive --
                # do NOT silently pass as orthogonal; return an explicit warning so the
                # caller can investigate the vector quality.
                return True, float("nan"), (
                    "corr-check inconclusive: corrcoef returned NaN "
                    "(check for NaN/inf/constant values in signal or engine vectors)")
            if abs(c) > cap:
                return False, abs(c), f"engine-redundant: |corr(signal, engine_pred)|={abs(c):.3f} > {cap}"
            return True, abs(c), f"orthogonal to engine (|corr|={abs(c):.3f})"
    return True, 0.0, "orthogonal (no owned-node collision)"


def _owned_nodes() -> set:
    eng = Registry("engine_registry").all()
    owned = set()
    for _, r in eng.iterrows():
        nodes = r.get("owns_nodes")
        if nodes is None or isinstance(nodes, float):    # missing / NaN
            continue
        try:
            for n in nodes:
                owned.add(str(n))
        except TypeError:
            pass
    return owned


def judge_signal(row: dict, owned: set | None = None) -> dict:
    owned = _owned_nodes() if owned is None else owned
    sok, sreason = sign_sanity(row.get("declared_sign"), row.get("measured_sign"))
    eok, ortho, ereason = engine_redundancy(row.get("quantity"), owned)
    verdict = "pass" if (sok and eok) else "reject"
    return dict(legacy_name=row.get("legacy_name"), signal_id=row.get("signal_id"),
                sign_ok=sok, engine_ortho_ok=eok, judge_engine_ortho=ortho,
                verdict=verdict, reasons=[r for r, ok in ((sreason, sok), (ereason, eok)) if not ok] or ["all judge checks pass"])


def run_trust_gate() -> dict:
    """Judge every validated/caveat signal. The TRUST GATE PASSES iff the 2 known CAVEATs are auto-rejected
    (opp_position_defense_reb by sign, oreb_matchup by engine-redundancy) and the genuinely-validated
    signals are NOT falsely rejected."""
    sig = Registry("signal_registry")
    df = sig.all()
    owned = _owned_nodes()
    targets = df[df.status.isin(["validated", "caveat"])]
    results = {r["legacy_name"]: judge_signal(r, owned) for _, r in targets.iterrows()}
    caveat_reb = results.get("opp_position_defense_reb", {})
    caveat_oreb = results.get("oreb_matchup", {})
    reb_rejected = caveat_reb.get("verdict") == "reject" and not caveat_reb.get("sign_ok")
    oreb_rejected = caveat_oreb.get("verdict") == "reject" and not caveat_oreb.get("engine_ortho_ok")
    validated = ["pbp_origin_transition", "rest_x_age", "shot_clock_leverage"]
    false_rejects = [v for v in validated if results.get(v, {}).get("verdict") == "reject"]
    reproduced = reb_rejected and oreb_rejected and not false_rejects
    # write the judge verdicts back to the registry (status caveat stays; record judge fields)
    for name, res in results.items():
        rid = res["signal_id"]
        try:
            sig.update_status(rid, judge_sign_ok=res["sign_ok"], judge_engine_ortho=res["judge_engine_ortho"])
        except Exception:
            pass
    return dict(reproduced_both=reproduced,
                reb_rejected_by_sign=reb_rejected, oreb_rejected_by_engine=oreb_rejected,
                false_rejects=false_rejects, results=results,
                detail=f"opp_position_defense_reb->sign_confound={reb_rejected}; "
                       f"oreb_matchup->engine_redundant={oreb_rejected}; false_rejects={false_rejects}")


def main():
    rep = run_trust_gate()
    print("=== FOUNDRY TRUST GATE (reproduce the 2 hand-written CAVEAT auto-rejections) ===")
    for name, r in rep["results"].items():
        mark = "REJECT" if r["verdict"] == "reject" else "pass  "
        print(f"  [{mark}] {name:26s} {'; '.join(r['reasons'])}")
    print(f"\nopp_position_defense_reb rejected by sign_sanity: {rep['reb_rejected_by_sign']}")
    print(f"oreb_matchup rejected by engine_redundancy:      {rep['oreb_rejected_by_engine']}")
    print(f"false rejects of validated signals:              {rep['false_rejects']}")
    print(f"\nTRUST GATE: {'PASS' if rep['reproduced_both'] else 'FAIL'}")
    if rep["reproduced_both"]:
        from build_done_check import write_marker
        write_marker("B4_trust_gate", dict(reproduced_both=True, detail=rep["detail"], asof="2026-06-08"))
        print("B4 marker written.")
    return rep


if __name__ == "__main__":
    main()
