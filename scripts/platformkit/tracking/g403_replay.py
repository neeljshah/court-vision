"""G403 raw-answer replay over the landed G400 archives (no new rating)."""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Sequence

from scripts.platformkit.tracking.g403_contract import answer_status, binding_issues

STATES = ("VISIBLE", "ABSENT", "UNKNOWN")


@dataclass(frozen=True)
class Answer:
    """One parsed archived answer, keeping label validity separate from geometry."""

    archive: str
    line: int
    rater: str
    round_id: int
    position: int
    frame_key: str
    label: str
    box: Optional[tuple[float, float, float, float]]
    cx: Optional[float]
    cy: Optional[float]
    diameter: Optional[float]
    width: int
    height: int
    reason: str
    label_status: str
    box_status: str
    in_frame: bool

    @property
    def usable_visible(self) -> bool:
        """A VISIBLE judgement whose box parses and lands inside the native frame."""
        return self.label == "VISIBLE" and self.box_status == "VALID_BOX" and self.in_frame


def read_rows(path: Path) -> list[dict[str, str]]:
    """Read a delivered CSV table with its header intact."""
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def native_dims(manifest: Path) -> dict[str, tuple[int, int]]:
    """Map every sealed frame key to its native pixel width and height."""
    return {row["frame_key"]: (int(row["width"]), int(row["height"])) for row in read_rows(manifest)}


def plan_order(batch_plan: Path) -> dict[str, tuple[int, int]]:
    """Map every sealed frame key to its (round, position) in the sealed batch order."""
    return {row["frame_key"]: (int(row["round"]), int(row["position"])) for row in read_rows(batch_plan)}


def parse_archive(path: Path, rater: str, round_id: int, dims: dict[str, tuple[int, int]],
                  order: dict[str, tuple[int, int]]) -> list[Answer]:
    """Parse one archived answer file by explicit frame key, retaining every field."""
    short = {key[:12]: key for key in dims}
    answers: list[Answer] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        fields = (line.split(",", 6) + [""] * 7)[:7]
        frame_key = short.get(fields[0], fields[0])
        width, height = dims.get(frame_key, (0, 0))
        box = None
        if fields[2].strip():
            try:
                left, top, box_w, box_h = (float(value) for value in fields[2:6])
                box = (left, top, box_w, box_h)
            except ValueError:
                box = None
        status = answer_status(fields[1], None if box is None else (box[0], box[1], box[0] + box[2], box[1] + box[3]))
        cx = cy = diameter = None
        in_frame = False
        if box is not None:
            cx, cy = box[0] + box[2] / 2.0, box[1] + box[3] / 2.0
            diameter = (box[2] + box[3]) / 2.0
            in_frame = 0 <= cx < width and 0 <= cy < height
        answers.append(Answer(
            archive=path.name, line=line_no, rater=rater, round_id=round_id,
            position=order.get(frame_key, (0, 0))[1], frame_key=frame_key, label=fields[1],
            box=box, cx=cx, cy=cy, diameter=diameter, width=width, height=height, reason=fields[6],
            label_status=status.label_status, box_status=status.box_status, in_frame=in_frame))
    return answers


def load_all(raw_dir: Path, dims: dict[str, tuple[int, int]],
             order: dict[str, tuple[int, int]]) -> list[Answer]:
    """Parse all 20 archives in a stable order and return every raw answer."""
    answers: list[Answer] = []
    for path in sorted(raw_dir.glob("*.txt")):
        stem = path.stem.split("_")
        rater, round_id = stem[-2], int(stem[-1])
        answers.extend(parse_archive(path, rater, round_id, dims, order))
    return answers


def archive_binding(answers: Sequence[Answer], order: dict[str, tuple[int, int]]) -> dict[str, dict[str, list[str]]]:
    """Report duplicate, missing and unexpected ids per rater against the sealed plan."""
    report: dict[str, dict[str, list[str]]] = {}
    for rater in sorted({answer.rater for answer in answers}):
        observed = [answer.frame_key for answer in answers if answer.rater == rater]
        report[rater] = binding_issues(order.keys(), observed)
    return report


def paired_labels(answers: Sequence[Answer]) -> dict[str, dict[str, Answer]]:
    """Index answers as frame_key -> rater -> answer."""
    index: dict[str, dict[str, Answer]] = {}
    for answer in answers:
        index.setdefault(answer.frame_key, {})[answer.rater] = answer
    return index


def _scored_label(answer: Optional[Answer]) -> Optional[str]:
    """Return the state a rater contributed, dropping a VISIBLE with no usable box."""
    if answer is None or answer.label not in STATES:
        return None
    if answer.label == "VISIBLE" and not answer.usable_visible:
        return None
    return answer.label


def confusion(pairs: Sequence[tuple[str, str]]) -> dict[str, float]:
    """Return the 3x3 counts, marginals, observed/expected agreement and kappa."""
    total = len(pairs)
    out: dict[str, float] = {"paired_n": total}
    for left in STATES:
        for right in STATES:
            out["n_%s_%s" % (left[:3], right[:3])] = sum(1 for a, b in pairs if a == left and b == right)
    for state in STATES:
        out["terra_%s" % state[:3]] = sum(1 for a, _ in pairs if a == state)
        out["sol_%s" % state[:3]] = sum(1 for _, b in pairs if b == state)
    observed = sum(1 for a, b in pairs if a == b) / total
    expected = sum((out["terra_%s" % s[:3]] / total) * (out["sol_%s" % s[:3]] / total) for s in STATES)
    out["observed_agreement"] = observed
    out["expected_agreement"] = expected
    out["kappa"] = (observed - expected) / (1 - expected)
    return out


def round_pairs(index: dict[str, dict[str, Answer]], order: dict[str, tuple[int, int]],
                round_id: Optional[int]) -> tuple[list[tuple[str, str]], int, int]:
    """Return the scored pairs for one round (or all rounds) plus per-rater missingness."""
    pairs: list[tuple[str, str]] = []
    terra_missing = sol_missing = 0
    for key in sorted(order, key=lambda k: order[k]):
        if round_id is not None and order[key][0] != round_id:
            continue
        raters = index.get(key, {})
        terra, sol = _scored_label(raters.get("terra")), _scored_label(raters.get("sol"))
        terra_missing += terra is None
        sol_missing += sol is None
        if terra and sol:
            pairs.append((terra, sol))
    return pairs, terra_missing, sol_missing


def centre_gaps(index: dict[str, dict[str, Answer]], order: dict[str, tuple[int, int]]) -> list[dict[str, object]]:
    """Return every raw both-VISIBLE pair with its gap; no pair is ever excluded."""
    rows: list[dict[str, object]] = []
    for key in sorted(order, key=lambda k: order[k]):
        raters = index.get(key, {})
        terra, sol = raters.get("terra"), raters.get("sol")
        if not (terra and sol and terra.usable_visible and sol.usable_visible):
            continue
        rows.append({
            "frame_key": key, "round": order[key][0], "position": order[key][1],
            "width": terra.width, "height": terra.height,
            "terra_cx": terra.cx, "terra_cy": terra.cy, "terra_d": terra.diameter,
            "sol_cx": sol.cx, "sol_cy": sol.cy, "sol_d": sol.diameter,
            "gap_px": round(math.hypot(terra.cx - sol.cx, terra.cy - sol.cy), 3),
        })
    return rows


def percentile(values: Iterable[float], quantile: float, method: str = "nearest_rank") -> float:
    """Return a percentile under the named convention; both are reported, never mixed."""
    ordered = sorted(values)
    if not ordered:
        raise ValueError("empty-population")
    if method == "nearest_rank":
        rank = max(1, math.ceil(quantile * len(ordered)))
        return ordered[rank - 1]
    index = (len(ordered) - 1) * quantile
    low, high = math.floor(index), math.ceil(index)
    return ordered[low] + (ordered[high] - ordered[low]) * (index - low)
