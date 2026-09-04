"""Isolated, declarative wrapper for redaction-sensitive eval-gate callers."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


_SAFE_STATE_KEYS = (
    "game_id", "state_ts", "home", "away", "season", "sport", "game_date", "regime",
    "outcome", "devig_close_prob",
)
_REQUIRED_STATE_KEYS = ("game_id", "state_ts", "home", "away", "outcome", "devig_close_prob")
_MODES = ("walk_forward", "cpcv_evaluate")


@dataclass(frozen=True)
class IsolatedEvaluation:
    """Records and parent RSS measurements emitted by the fresh evaluator process."""

    records: list[dict[str, Any]]
    rss_before_bytes: int | None
    rss_after_bytes: int | None


def _rss_bytes() -> int | None:
    try:
        import psutil
    except ImportError:
        return None
    return int(psutil.Process(os.getpid()).memory_info().rss)


def _feature_spec(spec: Mapping[str, Any]) -> str:
    if not isinstance(spec, Mapping):
        raise TypeError("S295 requires a declarative predictor specification; callbacks are forbidden")
    if set(spec) != {"kind", "feature"} or spec["kind"] != "feature_probability":
        raise ValueError("S295 supports only {'kind': 'feature_probability', 'feature': <name>}")
    feature = spec["feature"]
    if not isinstance(feature, str) or not feature:
        raise ValueError("S295 predictor feature must be a nonempty string")
    return feature


def declared_payload(states: Sequence[Mapping[str, Any]], spec: Mapping[str, Any]) -> dict[str, Any]:
    """Serialize only evaluator essentials plus the sole declared predictor feature."""
    feature = _feature_spec(spec)
    safe_states: list[dict[str, Any]] = []
    for state in states:
        missing = [key for key in _REQUIRED_STATE_KEYS if key not in state]
        if missing:
            raise ValueError("S295 state missing required key(s): " + ", ".join(missing))
        features, availability = state.get("features"), state.get("feature_avail")
        if not isinstance(features, Mapping) or not isinstance(availability, Mapping):
            raise ValueError("S295 state must carry feature maps")
        if feature not in features or feature not in availability:
            raise ValueError("S295 declared feature is absent from a state")
        clean = {key: state[key] for key in _SAFE_STATE_KEYS if key in state}
        clean["features"] = {feature: features[feature]}
        clean["feature_avail"] = {feature: availability[feature]}
        safe_states.append(clean)
    return {"states": safe_states, "predictor_spec": dict(spec)}


def _child_main() -> None:
    """Read a safe payload and produce all probabilities through the shared evaluator."""
    payload = json.load(sys.stdin)
    feature = _feature_spec(payload["predictor_spec"])
    mode = payload["mode"]
    if mode not in _MODES:
        raise ValueError("unknown S295 evaluator mode")
    from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate
    from scripts.platformkit.eval_gate.walkforward import walk_forward

    def predictor(_train: list[dict], test: dict, _inside: bool) -> float:
        return float(test["features"][feature])

    if mode == "walk_forward":
        records = walk_forward(payload["states"], predictor, strict_redaction=True).records
    else:
        records = cpcv_evaluate(
            payload["states"], predictor, n_groups=4, n_test_groups=1,
            embargo_days=1, strict_redaction=True,
        )
    for record in records:
        split = str(record.get("split_id", "wf"))
        record["stable_tick_key"] = "|".join((mode, split, record["game_id"], record["ts"]))
    assert len({record["stable_tick_key"] for record in records}) == len(records)
    json.dump({"records": records}, sys.stdout, sort_keys=True, separators=(",", ":"))


def evaluate_isolated(states: Sequence[Mapping[str, Any]], spec: Mapping[str, Any], mode: str) -> IsolatedEvaluation:
    """Run a declared-feature predictor in a fresh, isolated Python subprocess."""
    if mode not in _MODES:
        raise ValueError("unknown S295 evaluator mode")
    payload = declared_payload(states, spec)
    payload["mode"] = mode
    root = Path(__file__).resolve().parents[3]
    child = (
        "import sys; sys.path.insert(0, %r); "
        "from scripts.platformkit.eval_gate.strict_redaction_wrapper import _child_main; _child_main()"
    ) % str(root)
    before = _rss_bytes()
    completed = subprocess.run(
        [sys.executable, "-I", "-c", child], input=json.dumps(payload, separators=(",", ":")),
        text=True, capture_output=True, check=False, cwd=str(root), close_fds=True,
    )
    after = _rss_bytes()
    if completed.returncode != 0:
        raise RuntimeError("S295 isolated evaluator failed: " + completed.stderr.strip())
    output = json.loads(completed.stdout)
    records = output.get("records")
    if not isinstance(records, list):
        raise RuntimeError("S295 isolated evaluator emitted no record list")
    return IsolatedEvaluation(records, before, after)


if __name__ == "__main__":
    _child_main()
