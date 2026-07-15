"""Room builder: graveyard.json -- rejected hypotheses, gate verdicts, retractions.

rejects: data/frontend/reject_ledger.jsonl (signal graveyard).
gate_verdicts: data/frontend/ingame/ladder_*.json + *_gate_*.json.
retractions: hardcoded documented retraction set (no literal banned numbers --
see docs/JOB_EVIDENCE_PACKET.md for the numbers themselves).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from scripts.platformkit.showcase import common

REJECT_LEDGER = common.REPO / "data" / "frontend" / "reject_ledger.jsonl"
INGAME_DIR = common.REPO / "data" / "frontend" / "ingame"

REJECT_CAP = 1500

# ponytail: field names vary a lot across ladder_*/​*_gate_*.json files (brier_base
# vs brier_best vs brier_m0, etc). One tolerant lookup table beats a bespoke
# parser per file.
_BRIER_BASE_KEYS = ("brier_base", "brier_best", "brier_m0")
_BRIER_LAYER_KEYS = ("brier_layer", "brier_m1", "brier_cand")
_BRIER_DELTA_KEYS = ("brier_delta",)
_N_GAMES_KEYS = ("n_test_games", "n_games", "n_states", "n_test_states", "n_clusters")
_SUBDICTS = ("a_to_b", "b_to_a", "gate", "metrics")


def _find(d: dict, keys: tuple[str, ...]):
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    for sub in _SUBDICTS:
        s = d.get(sub)
        if isinstance(s, dict):
            for k in keys:
                if k in s and s[k] is not None:
                    return s[k]
    return None


RETRACTIONS = [
    {
        "story": "Pregame return percentage figure -- later identified as a "
                 "market-follow artifact, not a model edge.",
        "where_documented": "docs/JOB_EVIDENCE_PACKET.md",
    },
    {
        "story": "endQ3 win-probability Brier figure -- traced to a Q4 label "
                 "leak into the evaluation window.",
        "where_documented": "docs/JOB_EVIDENCE_PACKET.md",
    },
    {
        "story": "In-play win-rate ceiling percentage -- an L5-proxy artifact, "
                 "not a realized edge.",
        "where_documented": "docs/JOB_EVIDENCE_PACKET.md",
    },
    {
        "story": "In-play accuracy figure -- same L5-proxy ceiling as the "
                 "win-rate figure above, not a live result.",
        "where_documented": "docs/JOB_EVIDENCE_PACKET.md",
    },
]


def _build_rejects(asof: str) -> dict | list:
    if not REJECT_LEDGER.exists():
        return common.unavailable("data/frontend/reject_ledger.jsonl missing")

    rows = common.read_jsonl(REJECT_LEDGER)
    total = len(rows)
    rows.sort(key=lambda r: str(r.get("ts", "")))
    newest = rows[-REJECT_CAP:]

    rejects = []
    for r in newest:
        metrics = r.get("metrics") or {}
        gate_bits = ", ".join(f"{k}={v}" for k, v in list(metrics.items())[:4])
        rejects.append({
            "hypothesis": r.get("signal"),
            "sport": r.get("sport"),
            "why_killed": r.get("reason"),
            "gate": gate_bits,
            "asof": r.get("ts"),
            "receipt": common.receipt(
                f"Signal '{r.get('signal')}' rejected: {r.get('reason')}",
                r.get("verdict"), "MEASURED", REJECT_LEDGER, asof,
            ),
        })
    return {"total": total, "rejects": rejects}


def _build_gate_verdicts(asof: str) -> list[dict]:
    if not INGAME_DIR.is_dir():
        return []

    verdicts: list[dict] = []
    for path in sorted(INGAME_DIR.glob("ladder_*.json")):
        data = common.read_json(path)
        if not isinstance(data, dict):
            continue
        for item in data.get("ladder", []):
            if not isinstance(item, dict) or "verdict" not in item:
                continue
            verdicts.append({
                "name": item.get("layer") or path.stem,
                "verdict": item.get("verdict"),
                "why": data.get("vs_close") or data.get("note"),
                "brier_base": _find(item, _BRIER_BASE_KEYS),
                "brier_layer": _find(item, _BRIER_LAYER_KEYS),
                "brier_delta": _find(item, _BRIER_DELTA_KEYS),
                "n_games": _find(item, _N_GAMES_KEYS),
                "receipt": common.receipt(
                    f"Gate ladder entry '{item.get('layer')}' verdict "
                    f"{item.get('verdict')}.", item.get("verdict"), "MEASURED",
                    path, asof,
                ),
            })

    for path in sorted(INGAME_DIR.glob("*_gate_*.json")):
        data = common.read_json(path)
        if not isinstance(data, dict) or "verdict" not in data:
            continue
        name = data.get("layer") or data.get("feature") or path.stem
        verdicts.append({
            "name": name,
            "verdict": data.get("verdict"),
            "why": data.get("vs_close") or data.get("reason"),
            "brier_base": _find(data, _BRIER_BASE_KEYS),
            "brier_layer": _find(data, _BRIER_LAYER_KEYS),
            "brier_delta": _find(data, _BRIER_DELTA_KEYS),
            "n_games": _find(data, _N_GAMES_KEYS),
            "receipt": common.receipt(
                f"Gate '{name}' verdict {data.get('verdict')}.",
                data.get("verdict"), "MEASURED", path, asof,
            ),
        })
    return verdicts


def build() -> dict:
    asof = datetime.now(timezone.utc).date().isoformat()
    result = _build_rejects(asof)
    if isinstance(result, dict) and result.get("status") == "unavailable":
        return {"rejects": result, "rejects_total": 0,
                "gate_verdicts": _build_gate_verdicts(asof), "retractions": RETRACTIONS}

    return {
        "rejects": result["rejects"],
        "rejects_total": result["total"],
        "gate_verdicts": _build_gate_verdicts(asof),
        "retractions": RETRACTIONS,
    }


if __name__ == "__main__":
    print(json.dumps(build(), indent=1, default=str)[:2000])
