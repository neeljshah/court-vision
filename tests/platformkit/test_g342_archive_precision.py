"""G342 fix 1d archive reconstruction checks."""
from __future__ import annotations

from collections import defaultdict

import numpy as np

from scripts.platformkit.court_templates import g342_synthetic_run as runner
from scripts.platformkit.court_templates.template_select import _frame_cost, _project
from scripts.platformkit.court_templates.templates import load_template


def test_full_precision_archive_recomputes_ten_stored_costs(monkeypatch) -> None:
    """The additive repr fields restore each float32 input exactly enough for cost replay."""
    def fast_refit(rng, template, observed, n=1):
        return runner._sample_H(rng, template["feet"]["length"], template["feet"]["width"])

    monkeypatch.setattr(runner, "_best_refit", fast_refit)
    _, _, archive, observed, _ = runner.run(n=5)
    markings: dict[tuple[str, int, int], list[tuple[int, str, str, np.ndarray]]] = defaultdict(list)
    for true_name, frame_id, subset, marking_index, semantic_id, family, point_index, point in observed:
        if subset == "validation":
            markings[(true_name, frame_id, marking_index)].append((point_index, semantic_id, family, point))
    for arm, true_name, frame_id, shot_id, scored_name, H_source, stored_cost in archive[:10]:
        row = runner._archive_row(arm, true_name, frame_id, shot_id, scored_name, H_source, stored_cost)
        frame_markings = []
        prefix = (true_name, frame_id)
        for key, points in markings.items():
            if key[:2] == prefix:
                ordered = sorted(points)
                frame_markings.append({"semantic_id": ordered[0][1], "family": ordered[0][2], "points": np.array([point for _, _, _, point in ordered], dtype=np.float32)})
        H = np.array([[float(row[15 + r * 3 + c]) for c in range(3)] for r in range(3)], dtype=np.float32)
        template = load_template(scored_name)
        actual, _ = _frame_cost(frame_markings, _project(template, H))
        assert abs(actual - float(row[24])) <= 1e-9
