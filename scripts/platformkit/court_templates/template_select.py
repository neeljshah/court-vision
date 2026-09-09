"""Conservative multi-frame selection among court-rule template hypotheses."""
from __future__ import annotations

from collections import Counter
from typing import Any

import cv2
import numpy as np

from scripts.platformkit.court_templates.templates import segments

_GROUPS = {"ARC_3": "arc_radius", "LANE_L": "lane_width", "LANE_R": "lane_width", "SIDELINE": "court_length", "CORNER_3": "corner_straight"}


def _project(template: dict[str, Any], H: np.ndarray) -> list[dict[str, Any]]:
    output = []
    for item in segments(template):
        item = item.copy()
        item["points"] = cv2.perspectiveTransform(item["points"].reshape(-1, 1, 2), H).reshape(-1, 2)
        output.append(item)
    return output


def _directed(a: np.ndarray, b: np.ndarray) -> float:
    """Median, over points of a, of each point's nearest-neighbour distance in b."""
    return float(np.median(np.min(np.linalg.norm(a[:, None] - b[None, :], axis=2), axis=1)))


def _distance(a: np.ndarray, b: np.ndarray) -> float:
    """Symmetric distance: mean of the two directed median distances (sealed fix 1b)."""
    return 0.5 * (_directed(a, b) + _directed(b, a))


def _frame_cost(observed: list[dict[str, Any]], predicted: list[dict[str, Any]]) -> tuple[float, dict[str, float]]:
    costs, groups = [], {}
    for obs in observed:
        choices = [p["points"] for p in predicted if p["family"] == obs["family"]]
        if not choices:
            continue
        value = min(_distance(obs["points"], choice) for choice in choices)
        length = max(1.0, float(np.linalg.norm(np.diff(obs["points"], axis=0), axis=1).sum()))
        costs.append(value / length)
        group = _GROUPS.get(obs["semantic_id"])
        if group:
            groups[group] = min(groups.get(group, float("inf")), value / length)
    unsupported = sum(all(_distance(p["points"], o["points"]) > 4.0 for o in observed if o["family"] == p["family"]) for p in predicted)
    return float(np.median(costs) + unsupported / max(1, len(predicted))), groups


def select_template(frames: list[dict[str, Any]], templates: dict[str, dict[str, Any]], homographies: dict[str, list[np.ndarray]], seed: int = 34220260908) -> dict[str, Any]:
    """Return a winner only when the preregistered multi-frame rule is met."""
    assert len(frames) >= 5 and len({frame["shot_id"] for frame in frames}) >= 2
    assert any(o["family"] == "ARC" for f in frames for o in f["segments"]), "quadrilateral alone cannot identify a template"
    names = sorted(templates); costs = {name: [] for name in names}; groups = {name: Counter() for name in names}
    for index, frame in enumerate(frames):
        # ponytail: cache each name's _frame_cost once per frame (was recomputed inside the
        # min() below for every group x name); same values, ~17x fewer calls -- no output change.
        per_name = {name: _frame_cost(frame["segments"], _project(templates[name], homographies[name][index])) for name in names}
        for name in names:
            value, group_cost = per_name[name]
            costs[name].append(value)
            for group, score in group_cost.items():
                groups[name][group] += score == min(per_name[n][1].get(group, float("inf")) for n in names)
    ranked = sorted(names, key=lambda name: float(np.median(costs[name])))
    winner, runner = ranked[:2]; ratio = np.median(costs[winner]) / max(np.median(costs[runner]), 1e-12)
    rng = np.random.default_rng(seed); wins = 0
    for _ in range(100):
        sampled = rng.integers(0, len(frames), len(frames))
        best = min(names, key=lambda name: float(np.median(np.asarray(costs[name])[sampled])))
        wins += best == winner
    distinctive = sum(groups[winner][group] > groups[runner][group] for group in set(_GROUPS.values()))
    plausible = [name for name in names if np.median(costs[name]) <= np.median(costs[winner]) / 0.8]
    return {"winner": winner if ratio <= .8 and distinctive >= 2 and wins >= 90 else "UNKNOWN", "plausible": plausible, "costs": {n: float(np.median(costs[n])) for n in names}, "group_wins": {n: dict(groups[n]) for n in names}, "bootstrap_wins": wins, "distinctive_groups": distinctive}
