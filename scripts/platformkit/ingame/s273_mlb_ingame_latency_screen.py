"""S273 sealed MLB state-timestamp latency sensitivity measurement."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Sequence

import pandas as pd

from scripts.platformkit import hedge_trial_arms as arms
from scripts.platformkit.ingame import s254_mlb_phase_recal_fwer_sealed as s254
from scripts.platformkit.ingame import s88_phase_recal as s88
from scripts.platformkit.ingame_replay_scoreboard import discover_store

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "docs/evidence/harness"
PREREG = OUT / "S273_mlb_ingame_latency_screen_2026-09-04_PREREG.md"
SUMMARY_PATH = OUT / "S273_mlb_ingame_latency_screen_2026-09-04_summary.json"
MEMO_PATH = OUT / "S273_mlb_ingame_latency_screen_2026-09-04.md"
S254_SUMMARY = OUT / "S254_mlb_phase_recal_fwer_sealed_2026-09-04_summary_attempt2.json"
S213_SUMMARY = OUT / "S213_ingame_latency_summary_2026-09-04.json"
ARMS = (("none", 0.0), ("p50", 41.0), ("p90", 102.0))


def shift_records(records: Sequence[Dict[str, Any]], delay_seconds: float) -> List[dict]:
    """Return records whose state-build timestamp is later by the named delay."""
    shifted = []
    for row in records:
        updated = dict(row)
        updated["ts"] = (s254._stamp(row["ts"]) + timedelta(seconds=delay_seconds)).isoformat()
        shifted.append(updated)
    return shifted


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _input(path: Path, resolution: str) -> dict:
    return {"path": path.relative_to(ROOT).as_posix(), "bytes": path.stat().st_size,
            "resolution": resolution}


def _largest(summary: dict) -> dict:
    row = max(summary["buckets"], key=lambda item: item["delta"])
    return {"bucket": row["bucket"], "delta": row["delta"], "ci95": row["ci95"]}


def _run_arm(records: Sequence[Dict[str, Any]], store: Path, prereg: dict,
             arm: str, delay_seconds: float) -> dict:
    source_states = s254.states(shift_records(records, delay_seconds))
    first_score = datetime.now(timezone.utc).isoformat()
    predictions, evaluated = s254.callback_predictions(source_states)
    purge = s254.purge_log(source_states, evaluated)
    frame = pd.DataFrame([dict(row, recal_prob=predictions[index])
                          for index, row in enumerate(records)])
    frame["state_ts"] = [state["state_ts"] for state in source_states]
    frame["delay_seconds"] = delay_seconds
    frame["arm"] = arm
    frame["incumbent_loss"] = (frame["model_prob"] - frame["outcome"]) ** 2
    frame["candidate_loss"] = (frame["recal_prob"] - frame["outcome"]) ** 2
    result = s254.summarize(frame, prereg, purge, first_score, store)
    result["arm"] = arm
    result["delay_seconds"] = delay_seconds
    result["largest_single_bucket"] = _largest(result)
    assert result["denominator"]["n_informative_game_clusters"] >= 30
    pair_path = OUT / ("S273_mlb_ingame_latency_screen_2026-09-04_%s_paired_loss.csv" % arm)
    frame.to_csv(pair_path, index=False)
    result["paired_loss_path"] = pair_path.relative_to(ROOT).as_posix()
    return result


def _table(arm_result: dict) -> List[str]:
    lines = ["### %s (delay %.1f s)" % (arm_result["arm"], arm_result["delay_seconds"]), "",
             "| bucket | delta | CI95 | raw p | BH p | BH survivor | clusters |",
             "|---|---:|---|---:|---:|---|---:|"]
    for row in arm_result["buckets"]:
        lines.append("| %s | %+.6f | [%+.6f, %+.6f] | %.6f | %.6f | %s | %d |" % (
            row["bucket"].replace("|", "\\|"), row["delta"], row["ci95"][0], row["ci95"][1],
            row["raw_p"], row["bh_p"], str(row["bh_survivor"]).lower(), row["n_game_clusters"]))
    return lines


def _memo(summary: dict) -> str:
    lines = ["# S273 MLB in-game latency screen (2026-09-04)", "", "## Premise", "",
             "S213 reports MLB GUMBO captured_at minus ts p50 41.0 s and p90 102.0 s.",
             "S254 committed denominator is 47104 evaluated ticks, 14611 informative ticks, and 158 informative game clusters.",
             "The resolved local input store was readable before scoring.", "", "## Seal, route, and inputs", "",
             "Preregistration: `%s`; seal SHA-256 `%s`." % (summary["prereg"]["path"], summary["prereg"]["sha256"]),
             "S254 route SHA-256: `%s`; S273 runner SHA-256: `%s`." % (summary["route_sha256"], summary["runner_sha256"]),
             "CPCV used the inherited purge and symmetric 1-day embargo in every arm. No flags, registry, ledger, or serving artifact changed.",
             "Inputs:", ""]
    for item in summary["inputs"]:
        lines.append("- `%s` (%d bytes; %s)." % (item["path"], item["bytes"], item["resolution"]))
    lines += ["", "## Three-arm results", ""]
    for arm_result in summary["arms"]:
        lines.extend(_table(arm_result))
        lines.append("")
    lines += ["## Largest-delta comparison", "",
              "| arm | delay s | BH survivors | largest bucket | largest delta | CI95 | informative game clusters |",
              "|---|---:|---:|---|---:|---|---:|"]
    for arm_result in summary["arms"]:
        largest, d = arm_result["largest_single_bucket"], arm_result["denominator"]
        lines.append("| %s | %.1f | %d | %s | %+.6f | [%+.6f, %+.6f] | %d |" % (
            arm_result["arm"], arm_result["delay_seconds"], len(arm_result["bh_survivors"]),
            largest["bucket"].replace("|", "\\|"), largest["delta"], largest["ci95"][0],
            largest["ci95"][1], d["n_informative_game_clusters"]))
    lines += ["", "The comparison is a calibration measurement only. The per-arm paired-loss CSV archives game id, source ts, shifted state_ts, both losses, and arm delay for recomputation.",
              "", "## Self-check", "", "- Q1: preregistration was committed and its LF staged-byte seal was verified from HEAD before the first score.",
              "- Q4: all three arms use cpcv_evaluate with the inherited purge and symmetric nonzero embargo.",
              "- Q9: each arm archives its paired-loss series and its shifted state timestamp."]
    return "\n".join(lines) + "\n"


def run(cache_root: Path = ROOT / "data/cache") -> dict:
    prereg = s254.prereg_identity(PREREG)
    store = discover_store(cache_root)
    if store is None:
        raise ValueError("no parseable MLB store")
    files = list(store.rglob("*.jsonl"))
    assert files and sum(path.stat().st_size for path in files) <= 300 * 1024 * 1024
    ticks, features = arms.load_corpus(store, "mlb")
    records = s88.build_records(ticks, features)
    assert (len(records), len({row["game_id"] for row in records})) == (47104, 158)
    results = [_run_arm(records, store, prereg, arm, delay) for arm, delay in ARMS]
    summary = {"gap": "S273", "prereg": prereg, "route_sha256": _sha(Path(s254.__file__)),
               "runner_sha256": _sha(Path(__file__)), "inputs": [
                   _input(S213_SUMMARY, "structured JSON latency summary"),
                   _input(S254_SUMMARY, "structured JSON CPCV summary"),
                   {"path": store.relative_to(ROOT).as_posix(), "bytes": sum(path.stat().st_size for path in files),
                    "file_count": len(files), "resolution": "structured JSONL tick store"}], "arms": results}
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="ascii")
    MEMO_PATH.write_text(_memo(summary), encoding="ascii")
    return summary


def main() -> int:
    summary = run()
    for arm in summary["arms"]:
        largest = arm["largest_single_bucket"]
        print("S273 arm=%s delay=%.1f clusters=%d bh_survivors=%d largest=%s delta=%+.6f" % (
            arm["arm"], arm["delay_seconds"], arm["denominator"]["n_informative_game_clusters"],
            len(arm["bh_survivors"]), largest["bucket"], largest["delta"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
