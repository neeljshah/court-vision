"""Pre-registered baselines for the eval gate (blueprint N1).

load_baseline(name) reads a frozen baselines/<name>.json; freeze_baseline writes one. The
gate blocks ONLY on regression-vs-THIS-baseline or a leak-guard assertion -- NEVER on
"fails to beat the close" (BSS<=0 / MATCHES_CLOSE is an HONEST success).

Committed baselines are a SYNTHETIC reproducibility/regression ANCHOR ("_synthetic": true),
frozen FROM THE ACTUAL offline run (gen_golden + offline_predict_fn + walk_forward), so the
gate is non-regressing by construction on the first clean run; a human re-blesses on any
intentional change. They are NOT a real calibration claim.

DEVIATION (noted in README): per-game model loss is embedded INLINE as an ASCII float list,
not a binary _pergame.npy -- keeping the baseline git-diffable + stdlib-only. ASCII + stdlib
json only.  Run once:  python baseline.py --freeze
"""
from __future__ import annotations
import json
from pathlib import Path

_DIR = Path(__file__).resolve().parent / "baselines"
SCHEMA, FROZEN_AT, TOLERANCE_BRIER = 1, "2026-06-16", 0.005
_NOTE = ("SYNTHETIC anchor. BSS<=0 is the HONEST result (near-oracle close). Gate blocks "
         "REGRESSION vs THIS baseline + LEAK, never the non-beat.")


def baseline_path(name: str) -> str:
    """Absolute path to baselines/<name>.json (whether or not it exists yet)."""
    return str(_DIR / f"{name}.json")


def load_baseline(name: str) -> dict:
    """Load a frozen baseline. Registered-but-absent slots load fine; run_gate marks them
    CORPUS_ABSENT/skip and never counts them toward the measured set."""
    p = _DIR / f"{name}.json"
    if not p.exists():
        raise FileNotFoundError(f"baseline {name} not frozen: {p}")
    with open(p, encoding="ascii") as fh:
        return json.load(fh)


def _r6(x) -> float:
    return round(float(x), 6)


def _write(name: str, payload: dict) -> None:
    _DIR.mkdir(parents=True, exist_ok=True)
    with open(_DIR / f"{name}.json", "w", encoding="ascii") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=True)
        fh.write("\n")


def freeze_baseline(name: str, metrics: dict, pergame_loss=None) -> None:
    """Write baselines/<name>.json from measured numbers (floats 6dp). Embeds per-game loss
    inline; adds frozen_at + schema + note + _synthetic:true + tolerance_brier."""
    _write(name, {
        "corpus": name, "schema": SCHEMA, "frozen_at": FROZEN_AT, "_synthetic": True,
        "n": int(metrics["n"]), "brier_model": _r6(metrics["brier_model"]),
        "brier_close": _r6(metrics["brier_close"]), "bss": _r6(metrics["bss"]),
        "verdict": str(metrics.get("verdict", "MATCHES_CLOSE")),
        "tolerance_brier": TOLERANCE_BRIER,
        "per_game_model_loss": [_r6(v) for v in (pergame_loss or [])], "note": _NOTE,
    })


def register_skip(name: str, until: str = "X2") -> None:
    """Write a registered-but-skipped slot (e.g. MLB until X2 in-game lands)."""
    _write(name, {"corpus": name, "status": f"REGISTERED_SKIP_UNTIL_{until}",
                  "_synthetic": True})


# --- offline freeze: byte-exact with the gate by construction ---
# Freezes from the SAME path run_gate runs: the committed golden fixture (load_golden),
# season-filtered exactly as _load_states does, scored with the SAME offline_predict_fn
# via walk_forward. This guarantees a re-freeze reproduces baselines that match the live
# gate (n + per-game loss vectors), so the DM-vs-baseline regression check stays exercised.

def _freeze_from_offline() -> None:
    import numpy as np
    try:                                   # bare run from the eval_gate cwd
        from golden_loader import load_golden
        from walkforward import walk_forward
        from scoring import brier, brier_skill_score
        from offline_predict import offline_predict_fn
    except ImportError:                    # python -m package run
        from .golden_loader import load_golden
        from .walkforward import walk_forward
        from .scoring import brier, brier_skill_score
        from .offline_predict import offline_predict_fn
    states = load_golden(None)             # the committed fixture (same as the gate)
    for name, season in (("nba_2023_24", "2023-24"), ("nba_2024_25", "2024-25")):
        st = [s for s in states if s.get("season") == season] or states   # == _load_states
        res = walk_forward(st, offline_predict_fn, select_inside=True)
        pm = np.array([r["p_model"] for r in res.records], dtype=float)
        pc = np.array([r["p_close"] for r in res.records], dtype=float)
        y = np.array([r["y"] for r in res.records], dtype=float)
        freeze_baseline(name, {"n": len(res.records), "brier_model": brier(pm, y),
                               "brier_close": brier(pc, y),
                               "bss": brier_skill_score(pm, pc, y), "verdict": "MATCHES_CLOSE"},
                        ((pm - y) ** 2).tolist())
        print(f"  froze {name}: n={len(res.records)} brier_model={brier(pm, y):.6f}")
    register_skip("mlb_2024", "X2")
    print("  registered mlb_2024 (skip-until-X2)")


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description="freeze eval-gate baselines from the offline run")
    ap.add_argument("--freeze", action="store_true", help="run golden gate; write baselines/*.json")
    if not ap.parse_args().freeze:
        ap.print_help()
        return 0
    print("freezing eval-gate baselines from the offline golden run (SYNTHETIC anchor)...")
    _freeze_from_offline()
    print("done. commit baselines/*.json; human re-blesses on intentional change.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
