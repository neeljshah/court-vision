"""prediction_quality resolver -- fail-closed readout of the honest
prediction-eval artifact (data/cache/prediction_eval/prediction_eval.json,
written by scripts.platformkit.pod_sprint.prediction_eval).

Quotes the artifact verbatim: OOS scoreboard rows (Brier/RMSE vs each sport's
reference), eval-gate receipt, and the no-edge note.  Artifact absent or
blocked -> no_data with the reason; never recomputes, never improvises.
"""
from __future__ import annotations

import json
from pathlib import Path

CATEGORY = "prediction_quality"
_REPO = Path(__file__).resolve().parents[3]
_ARTIFACT_REL = "data/cache/prediction_eval/prediction_eval.json"
# wnba before nba so "wnba" isn't swallowed by the "nba" substring test.
_SPORT_TOKENS = ("wnba", "tennis", "soccer", "mlb", "nba")


def sport_in_query(query: str) -> str | None:
    """Sport filter ONLY when the query names one -- the artifact is
    cross-sport, so a bare 'prediction quality?' returns every row."""
    low = query.lower()
    for s in _SPORT_TOKENS:
        if s in low:
            return s
    return None


def resolve(sport: str | None = None) -> dict:
    path = _REPO / _ARTIFACT_REL
    base = {"category": CATEGORY, "sport": sport or "all",
            "source_artifact": _ARTIFACT_REL}
    if not path.exists():
        return {**base, "status": "no_data",
                "note": ("prediction_eval.json not generated yet -- run "
                         "python -m scripts.platformkit.pod_sprint.prediction_eval")}
    try:
        d = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        return {**base, "status": "no_data", "note": f"artifact unreadable: {exc}"}
    if d.get("status") != "ok":
        return {**base, "status": "no_data", "as_of": d.get("generated"),
                "note": f"artifact blocked: {d.get('blocked_reason')}"}
    rows = d.get("scoreboard", [])
    if sport:
        rows = [r for r in rows if r.get("sport") == sport]
        if not rows:
            return {**base, "status": "no_data", "as_of": d.get("generated"),
                    "note": f"no scoreboard row for sport '{sport}'"}
    return {**base, "status": "ok", "as_of": d.get("generated"),
            "eval_gate": d.get("eval_gate"), "scoreboard": rows,
            "n_sports_scored": d.get("n_sports_scored"),
            "n_sports_validated": d.get("n_sports_validated"),
            "note": d.get("note")}
