"""Immutable G390 candidate token and final receipt writer."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

TOKEN_STATES = {"CHARGED_BEFORE_INFERENCE", "INFERENCE_COMPLETE", "SCORING_STARTED", "CLOSED"}


def _read(path: Path) -> dict[str, object]:
    with Path(path).open(encoding="ascii") as handle:
        return json.load(handle)


def _write(path: Path, payload: Mapping[str, object]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n",
                          encoding="ascii", newline="\n")


def charge_candidate_token(path: Path, *, source_hashes: Mapping[str, str]) -> dict[str, object]:
    """Charge the sole candidate allowance before inference; never replace it."""
    path = Path(path)
    if path.exists():
        raise ValueError("second-candidate-inference-refused")
    token = {"candidate_heldout_executions": 1, "state": "CHARGED_BEFORE_INFERENCE",
             "source_hashes": dict(sorted(source_hashes.items()))}
    _write(path, token)
    return token


def advance_token(path: Path, expected: str, target: str) -> dict[str, object]:
    """Advance the one token once; a second scoring pass is a hard refusal."""
    token = _read(path)
    if token.get("candidate_heldout_executions") != 1 or token.get("state") != expected:
        raise ValueError("second-scoring-pass-refused")
    if target not in TOKEN_STATES:
        raise ValueError("invalid-token-state")
    token["state"] = target
    _write(path, token)
    return token


def begin_scoring(path: Path) -> dict[str, object]:
    """Close the ability to launch another scoring pass before scorer work begins."""
    return advance_token(path, "INFERENCE_COMPLETE", "SCORING_STARTED")


def write_receipt(path: Path, *, verdict: str, token_path: Path,
                  artifacts: Mapping[str, str]) -> dict[str, object]:
    """Write the final prepare-run receipt with the charged token state explicit."""
    token = _read(token_path)
    if token.get("candidate_heldout_executions") != 1:
        raise ValueError("invalid-candidate-accounting")
    receipt = {"verdict": verdict, "candidate_heldout_executions": 1,
               "token_state": token.get("state"), "artifacts": dict(sorted(artifacts.items()))}
    target = Path(path)
    if target.exists():
        raise ValueError("receipt-immutable")
    _write(target, receipt)
    return receipt
