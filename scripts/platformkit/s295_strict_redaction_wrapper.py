"""Run the S295 local strict-redaction construct and write durable evidence."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from scripts.platformkit.eval_gate.cpcv_engine import cpcv_evaluate
from scripts.platformkit.eval_gate.strict_redaction_wrapper import evaluate_isolated
from scripts.platformkit.eval_gate.walkforward import walk_forward


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/harness"
PREREG = EVIDENCE / "S295_strict_redaction_wrapper_prereg_2026-09-04.md"
PREREG_SHA256 = "6e4a9b70c8425d661678c1d3620cc6d7346a511313d943e2be4ec7d7d1478e75"
JSON_PATH = EVIDENCE / "S295_strict_redaction_wrapper_2026-09-04.json"
MEMO_PATH = EVIDENCE / "S295_strict_redaction_wrapper_2026-09-04.md"
MODES = ("walk_forward", "cpcv_evaluate")
MODULE_RAW: dict[tuple[str, str], int] = {}


def _verify_prereg() -> None:
    """Verify the prereg file itself, normalizing CRLF without consulting git."""
    data = PREREG.read_bytes().replace(b"\r\n", b"\n")
    prefix, seal = data.split(b"Seal SHA-256: ", 1)
    assert hashlib.sha256(prefix).hexdigest() == PREREG_SHA256
    assert seal.decode("ascii").strip() == PREREG_SHA256


def _states() -> list[dict[str, Any]]:
    start = datetime(2024, 1, 10, 19, 0, 0)
    states: list[dict[str, Any]] = []
    for index in range(8):
        state_ts = start + timedelta(days=7 * (index // 2), hours=index % 2)
        outcome = index % 2
        states.append({
            "game_id": "game_%d" % (index // 2), "state_ts": state_ts.isoformat(),
            "home": "H%d" % (index // 2), "away": "A%d" % (index // 2),
            "features": {"p": 0.75 if outcome == 0 else 0.25},
            "feature_avail": {"p": (state_ts - timedelta(days=1)).isoformat()},
            "devig_close_prob": 0.5, "outcome": outcome, "settled_plant": outcome,
        })
    return states


def _annotate(mode: str, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    copied = []
    for record in records:
        item = dict(record)
        split = str(item.get("split_id", "wf"))
        item["stable_tick_key"] = "|".join((mode, split, item["game_id"], item["ts"]))
        item["loss"] = (float(item["p_model"]) - int(item["y"])) ** 2
        copied.append(item)
    assert len({item["stable_tick_key"] for item in copied}) == len(copied)
    return copied


def _brier(records: list[dict[str, Any]]) -> float:
    assert records
    return sum(float(record["loss"]) for record in records) / len(records)


def _shared(mode: str, states: list[dict[str, Any]], predictor: Callable[..., float]) -> list[dict[str, Any]]:
    if mode == "walk_forward":
        return _annotate(mode, walk_forward(states, predictor).records)
    return _annotate(mode, cpcv_evaluate(states, predictor, n_groups=4, n_test_groups=1, embargo_days=1))


def _wilson(successes: int, total: int) -> list[float]:
    z = 1.959963984540054
    center = (successes + z * z / 2) / (total + z * z)
    radius = z * math.sqrt(successes * (total - successes) / total + z * z / 4) / (total + z * z)
    return [center - radius, center + radius]


def run_construct() -> dict[str, Any]:
    """Execute the preregistered premise, attacks, and valid replays in memory."""
    _verify_prereg()
    states = _states()
    raw = {(state["game_id"], state["state_ts"]): state["settled_plant"] for state in states}
    seen: list[bool] = []

    def closure_attack(_train: list[dict], test: dict, _inside: bool) -> float:
        seen.append("settled_plant" in test)
        return float(raw[(test["game_id"], test["state_ts"])])

    declared = lambda _train, test, _inside: float(test["features"]["p"])
    before_records = _shared("walk_forward", states, closure_attack)
    declared_records = _shared("walk_forward", states, declared)
    before_brier, declared_brier = _brier(before_records), _brier(declared_records)
    assert all(seen) and before_brier < declared_brier, "S295 premise falsified: planted callback did not alter loss"

    global MODULE_RAW
    MODULE_RAW = dict(raw)

    def module_global_attack(_train: list[dict], test: dict, _inside: bool) -> float:
        return float(MODULE_RAW[(test["game_id"], test["state_ts"])])

    def default_argument_attack(_train: list[dict], test: dict, _inside: bool, planted=raw) -> float:
        return float(planted[(test["game_id"], test["state_ts"])])

    attacks = []
    for mode in MODES:
        for form, attack in (("closure", closure_attack), ("module_global", module_global_attack),
                             ("default_argument", default_argument_attack)):
            try:
                evaluate_isolated(states, attack, mode)  # type: ignore[arg-type]
            except TypeError as exc:
                attacks.append({"mode": mode, "form": form, "rejected": True,
                                "exception_type": type(exc).__name__, "exception": str(exc)})
            else:
                raise AssertionError("S295 attack was accepted: %s/%s" % (mode, form))

    replays = []
    spec = {"kind": "feature_probability", "feature": "p"}
    for mode in MODES:
        baseline = _shared(mode, states, declared)
        isolated_result = evaluate_isolated(states, spec, mode)
        isolated = _annotate(mode, isolated_result.records)
        baseline_brier, isolated_brier = _brier(baseline), _brier(isolated)
        error = abs(baseline_brier - isolated_brier)
        assert error <= 1e-12
        replays.append({"mode": mode, "baseline_records": baseline, "isolated_records": isolated,
                        "baseline_brier": baseline_brier, "isolated_brier": isolated_brier,
                        "replay_error": error,
                        "rss": {"before_bytes": isolated_result.rss_before_bytes,
                                "after_bytes": isolated_result.rss_after_bytes}})
    assert len(attacks) == 6 and all(attack["rejected"] for attack in attacks)
    return {"schema": "S295_strict_redaction_wrapper_v1", "prereg_path": PREREG.relative_to(ROOT).as_posix(),
            "prereg_sha256": PREREG_SHA256, "input": {"kind": "generated_local_construct",
            "external_files_opened": [], "raw_states": states}, "before_condition": {
            "strict_redaction_default": False, "callback_readable": all(seen),
            "oracle_records": before_records, "declared_records": declared_records,
            "oracle_brier": before_brier, "declared_brier": declared_brier}, "attacks": attacks,
            "detection": {"successes": 6, "total": 6, "wilson_95": _wilson(6, 6)}, "replays": replays,
            "sign_convention": "improvement = baseline loss minus candidate loss; positive = candidate better"}


def _memo(result: dict[str, Any]) -> str:
    lines = ["# S295 Strict Redaction Wrapper", "", "## Result", "",
             "ACCEPT: all six fixed callback attacks were rejected before scoring, and both valid shared-evaluator replays have error at most 1e-12.",
             "", "## Preregistration", "", "- Path: `%s`" % result["prereg_path"],
             "- Seal SHA-256: `%s`" % result["prereg_sha256"],
             "- Sign convention: improvement = baseline loss minus candidate loss; positive = candidate better.",
             "", "## Premise binding", "",
             "Default `strict_redaction` was false. The planted closure was readable and produced Brier %.12f versus %.12f for the declared-feature fixture over %d scored evaluator states." % (result["before_condition"]["oracle_brier"], result["before_condition"]["declared_brier"], len(result["before_condition"]["oracle_records"])),
             "", "## Metric table", "", "| Metric | Result | 95 percent CI |", "|---|---:|---|",
             "| Planted leak detections | 6/6 | [%.12f, %.12f] |" % tuple(result["detection"]["wilson_95"])]
    for replay in result["replays"]:
        rss = replay["rss"]
        lines.append("| %s valid replay error | %.12f | n/a; RSS before/after %s/%s bytes |" % (
            replay["mode"], replay["replay_error"], rss["before_bytes"], rss["after_bytes"]))
    lines += ["", "## Durability and reproduction", "",
              "The JSON beside this memo archives the generated raw construct, declared evaluator payload basis, all rejection exceptions, every evaluator record, stable tick key, and per-record loss. Each game has two distinct state timestamps; records are keyed per tick, not per game.",
              "", "- Test: `python -m pytest scripts/platformkit/eval_gate/test_s295_strict_redaction_wrapper.py -q`", "",
              "## NOT VERIFIED", "", "- No external corpus, pod execution, deployment, or live caller migration was exercised.",
              "- No calibration-ahead claim is made; the frozen +0.004 bar was not evaluated by this security construct.", ""]
    return "\n".join(lines)


def main() -> None:
    result = run_construct()
    JSON_PATH.open("x", encoding="ascii", newline="\n").write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    MEMO_PATH.open("x", encoding="ascii", newline="\n").write(_memo(result))
    print("S295 ACCEPT 6/6 detections; artifacts: %s %s" % (JSON_PATH, MEMO_PATH))


if __name__ == "__main__":
    main()
