"""sell.reproduce -- run the REAL proofs a buyer would check; assemble verdicts.

reproduce_all() is the buyer's due-diligence button: it runs the SAME gates the
stack runs on itself and returns their HONEST verdicts, unmodified. It assembles;
it never upgrades a verdict. A MATCHES_CLOSE / BEHIND / UNPROVEN result is
surfaced exactly as the underlying proof produced it -- the whole point of the
sell layer is that the methodology, not a $ figure, is the asset.

WHAT IT RUNS (each is a separate, already-tested module; this only orchestrates):
  * governance        -- governance.run_governance.run_all (exit 0/1): every
                         honesty/correctness gate clean.
  * eval_gate         -- run_gate --golden in-process: the leak-free walk-forward
                         BSS-vs-Shin-devigged-close scoreboard (BEATS / MATCHES /
                         BEHIND per corpus; blocks on regression / leak only).
  * ingame_proof      -- data/frontend/ingame/proof_nba.json: the in-game
                         CALIBRATION_GAIN_VS_BASERATE verdict, with vs_close still
                         UNPROVEN (no in-play odds captured -- not a market edge).
  * track_record      -- the signed CLV track record verifies under SELL_API_SECRET
                         (is_signed + verify); UNSIGNED when no secret, honestly.

HONESTY: never fabricates a number. Every verdict is the literal string the proof
emitted; absent artifacts are reported as "unavailable", never as a pass.

INVARIANTS: build only under sell/; <=300 LOC; ASCII only; no secrets in code; no
$-edge field; reads only local artifacts; never writes data/registry/; no network.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

REPRODUCE_VERSION = "sell.reproduce.v1"

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent

#: The committed in-game proof verdict (leak-free same-season temporal split).
INGAME_PROOF_PATH = _REPO_ROOT / "data" / "frontend" / "ingame" / "proof_nba.json"
#: The signed CLV track-record artifact (same default as sell.cli).
TRACK_RECORD_PATH = (
    _REPO_ROOT / "data" / "frontend" / "sell" / "track_record.signed.json")

#: The exact one command a buyer runs to reproduce every verdict below.
REPRODUCE_COMMAND = "python -m sell.evidence_pack"


def _load_json(path: Path) -> Optional[Any]:
    """Best-effort read of a JSON artifact. Missing / malformed -> None."""
    try:
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def run_governance_verdict(**kwargs: Any) -> Dict[str, Any]:
    """Run the full governance preflight and surface its 0/1 verdict as-is."""
    from governance import run_governance as _gov

    res = _gov.run_all(**kwargs)
    return {
        "ok": bool(res["ok"]),
        "exit_code": int(res["exit_code"]),
        "verdict": "GOVERNANCE_OK" if res["ok"] else "GOVERNANCE_BLOCKED",
        "version": res.get("version"),
    }


def run_eval_gate_verdict() -> Dict[str, Any]:
    """Run the leak-free golden walk-forward in-process; surface honest per-corpus
    verdicts (BEATS / MATCHES / BEHIND) plus the 0/1 gate exit. Never upgrades."""
    from scripts.platformkit.eval_gate.offline_predict import offline_predict_fn
    from scripts.platformkit.eval_gate.run_gate import (
        gate_exit_code, run_gate_in_process)

    rows = run_gate_in_process(offline_predict_fn)
    corpora = []
    for r in rows:
        corpora.append({
            "corpus": r.get("corpus"),
            # Honest label exactly as the gate produced it; absent -> status.
            "verdict": r.get("verdict") or r.get("status"),
            "regressed": bool(r.get("regressed", False)),
        })
    code = gate_exit_code(rows)
    return {
        "ok": code == 0,
        "exit_code": int(code),
        "verdict": "NO_REGRESSION_NO_LEAK" if code == 0 else "GATE_FAILED",
        "corpora": corpora,
        "note": ("golden fixture is a SYNTHETIC reproducibility anchor; the gate "
                 "blocks on regression / leak only, never on 'fails to beat the "
                 "close'. MATCHES_CLOSE / BEHIND are honest, non-blocking results."),
    }


def ingame_proof_verdict() -> Dict[str, Any]:
    """Surface the committed in-game proof verdict UNCHANGED (vs_close UNPROVEN)."""
    proof = _load_json(INGAME_PROOF_PATH)
    if not isinstance(proof, dict):
        return {"available": False, "verdict": "unavailable",
                "vs_close": "unavailable"}
    return {
        "available": True,
        # The honest in-game calibration verdict, exactly as written on disk.
        "verdict": proof.get("verdict", "unavailable"),
        # vs_close stays UNPROVEN -- in-game gain is calibration, not a market edge.
        "vs_close": proof.get("vs_close", "UNPROVEN -- not a market edge"),
        "baseline": proof.get("baseline"),
        "n": (proof.get("metrics") or {}).get("n"),
    }


def track_record_verdict(*, secret: Optional[str] = None,
                         path: Optional[Path] = None,
                         record: Optional[Dict[str, Any]] = None,
                         ) -> Dict[str, Any]:
    """Load the signed track record and report is_signed + verify (honestly).

    An in-memory *record* may be injected (the pack verifies its OWN freshly
    signed record rather than a possibly-stale on-disk artifact). Else the record
    is read from *path* (default TRACK_RECORD_PATH). UNSIGNED when no
    SELL_API_SECRET was present at build time -- reported as such, never silently
    as verified. Absent artifact -> "unavailable"."""
    from sell import signing as _sig

    if record is None:
        src = Path(path) if path is not None else TRACK_RECORD_PATH
        record = _load_json(src)
    if not isinstance(record, dict):
        return {"available": False, "signed": False, "verified": False,
                "verdict": "unavailable", "edge_claimed": False}
    signed = _sig.is_signed(record)
    verified = bool(signed and _sig.verify(record, secret))
    if not signed:
        verdict = "UNSIGNED (no SELL_API_SECRET at build time)"
    elif verified:
        verdict = "SIGNATURE_VERIFIED"
    else:
        verdict = "SIGNATURE_INVALID (tampered or wrong secret)"
    return {
        "available": True,
        "signed": bool(signed),
        "verified": verified,
        "verdict": verdict,
        # Pinned False on the record by design; surfaced for the buyer's audit.
        "edge_claimed": bool(record.get("edge_claimed", False)),
        "n_settled": record.get("n_settled"),
    }


def reproduce_all(*, secret: Optional[str] = None,
                  track_record_path: Optional[Path] = None,
                  track_record: Optional[Dict[str, Any]] = None,
                  governance_kwargs: Optional[Dict[str, Any]] = None,
                  ) -> Dict[str, Any]:
    """Run every buyer-checkable proof and ASSEMBLE the honest verdicts.

    Returns::

        {
          "version": REPRODUCE_VERSION,
          "command": REPRODUCE_COMMAND,           # the one command to reproduce
          "governance":   {ok, exit_code, verdict, ...},
          "eval_gate":    {ok, exit_code, verdict, corpora:[...], ...},
          "ingame_proof": {available, verdict, vs_close, ...},  # vs_close UNPROVEN
          "track_record": {available, signed, verified, verdict, edge_claimed},
          "edge_claimed": False,                  # the product asserts no $-edge
        }

    No verdict is ever upgraded: MATCHES_CLOSE / BEHIND / UNPROVEN pass through
    exactly as the underlying proof produced them.
    """
    return {
        "version": REPRODUCE_VERSION,
        "command": REPRODUCE_COMMAND,
        "governance": run_governance_verdict(**(governance_kwargs or {})),
        "eval_gate": run_eval_gate_verdict(),
        "ingame_proof": ingame_proof_verdict(),
        "track_record": track_record_verdict(
            secret=secret, path=track_record_path, record=track_record),
        # The product makes no dollar-edge claim anywhere -- pinned False.
        "edge_claimed": False,
    }


__all__ = [
    "REPRODUCE_VERSION",
    "REPRODUCE_COMMAND",
    "INGAME_PROOF_PATH",
    "TRACK_RECORD_PATH",
    "run_governance_verdict",
    "run_eval_gate_verdict",
    "ingame_proof_verdict",
    "track_record_verdict",
    "reproduce_all",
]
