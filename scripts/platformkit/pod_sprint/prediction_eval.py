"""Fail-closed prediction_eval.json composer.

Assembles the honest "how good are the predictions today" artifact from the
sprint's real outputs: the cross-sport OOS scoreboard (Brier/RMSE vs baseline),
the eval-gate rc recorded by the sprint driver, and any crps_market last-run
receipts on disk.  Never fabricates: missing/errored inputs -> status "blocked"
with the reason, and per-sport error rows are carried through verbatim.

CLI: python -m scripts.platformkit.pod_sprint.prediction_eval
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from scripts.platformkit.pod_sprint.driver import REPO, STATE_PATH

OUT_PATH = REPO / "data" / "cache" / "prediction_eval" / "prediction_eval.json"
_CRPS_DIR = REPO / "scripts" / "platformkit" / "benchmarks" / "crps_market"
_NOTE = ("Calibration, not edge. OOS leak-free walk-forward; reference = tuned "
         "baseline / naive mean / devigged close. No $ or ROI claim anywhere.")


def _eval_gate_receipt() -> dict:
    if not STATE_PATH.exists():
        return {"status": "missing", "reason": "no sprint state file"}
    rec = json.loads(STATE_PATH.read_text()).get("eval_gate")
    if not rec:
        return {"status": "missing", "reason": "eval_gate job not run"}
    return {"status": "green" if rec.get("rc") == 0 else "red",
            "rc": rec.get("rc"), "ran": rec.get("ended"),
            "source": "scripts/platformkit/eval_gate/run_all.py"}


def _crps_receipts() -> list[dict]:
    out = []
    for p in sorted(_CRPS_DIR.glob("last_run*.json")):
        try:
            d = json.loads(p.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        out.append({"source": str(p.relative_to(REPO)),
                    "keys": sorted(d)[:12]})
    return out


def compose() -> dict:
    from scripts.platformkit.platform_scoreboard import build_scoreboard
    try:
        board = build_scoreboard()
    except Exception as exc:  # fail closed, never fabricate
        board = {"rows": [], "error": f"{type(exc).__name__}: {exc}"}
    rows = board.get("rows", [])
    scored = [r for r in rows if "error" not in r]
    gate = _eval_gate_receipt()
    blocked = (not scored) or "error" in board
    return {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "status": "blocked" if blocked else "ok",
        "blocked_reason": (board.get("error") or "no sport produced a score")
        if blocked else None,
        "eval_gate": gate,
        "scoreboard": rows,
        "n_sports_scored": len(scored),
        "n_sports_validated": len([r for r in scored if r.get("validated")]),
        "receipts": _crps_receipts(),
        "note": _NOTE,
    }


def main() -> int:
    rep = compose()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(rep, indent=1))
    print(f"prediction_eval -> {OUT_PATH} status={rep['status']} "
          f"scored={rep['n_sports_scored']} validated={rep['n_sports_validated']}")
    return 0 if rep["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
