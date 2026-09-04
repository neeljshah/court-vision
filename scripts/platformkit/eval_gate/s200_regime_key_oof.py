"""S200 helpers for assigning confidence keys from prior rows only."""
from __future__ import annotations
import json
from typing import Any, Mapping, Sequence
from pathlib import Path
from sklearn.isotonic import IsotonicRegression
from scripts.platformkit.recalibration import walk_forward_recalibrate
from scripts.platformkit.regime_calibration import buckets
from scripts.platformkit.regime_calibration import fit_per_regime
_GLOBAL_OOF_CACHE: dict[tuple[tuple[float, ...], tuple[float, ...], int, int], tuple[float, ...]] = {}
class _Node:
    __slots__ = ("key", "priority", "count", "size", "left", "right")
    def __init__(self, key: float, priority: int) -> None:
        self.key, self.priority = key, priority
        self.count, self.size = 1, 1
        self.left: _Node | None = None
        self.right: _Node | None = None
def _size(node: _Node | None) -> int:
    return node.size if node else 0
def _refresh(node: _Node) -> _Node:
    node.size = node.count + _size(node.left) + _size(node.right)
    return node
def _right(node: _Node) -> _Node:
    child = node.left
    assert child is not None
    node.left = child.right
    child.right = _refresh(node)
    return _refresh(child)
def _left(node: _Node) -> _Node:
    child = node.right
    assert child is not None
    node.right = child.left
    child.left = _refresh(node)
    return _refresh(child)
class _OrderStatistics:
    """Incremental ordered multiset; no future score enters its state."""
    def __init__(self) -> None:
        self.root: _Node | None = None
        self._state = 1
    def _priority(self) -> int:
        self._state = (1103515245 * self._state + 12345) & 0x7FFFFFFF
        return self._state
    def add(self, value: float) -> None:
        def insert(node: _Node | None) -> _Node:
            if node is None:
                return _Node(value, self._priority())
            if value == node.key:
                node.count += 1
                return _refresh(node)
            if value < node.key:
                node.left = insert(node.left)
                if node.left and node.left.priority < node.priority:
                    node = _right(node)
            else:
                node.right = insert(node.right)
                if node.right and node.right.priority < node.priority:
                    node = _left(node)
            return _refresh(node)
        self.root = insert(self.root)
    def kth(self, index: int) -> float:
        node = self.root
        while node is not None:
            left_size = _size(node.left)
            if index < left_size:
                node = node.left
            elif index < left_size + node.count:
                return node.key
            else:
                index -= left_size + node.count
                node = node.right
        raise IndexError("order statistic outside the train window")
    @property
    def count(self) -> int:
        return _size(self.root)
    def label(self, value: float) -> str:
        """Use train-rank tercile endpoints; T1 is the empty-history fallback."""
        n = self.count
        if n == 0:
            return "T1"
        lower = self.kth((n - 1) // 3)
        upper = self.kth((2 * n - 1) // 3)
        return "T1" if value <= lower else "T2" if value <= upper else "T3"
def confidence_label(key: str) -> str:
    """Extract a confidence label from a complete regime key."""
    return key.rsplit("confidence=", 1)[-1]
def stable_date_order(rows: Sequence[Mapping[str, Any]]) -> list[int]:
    """Return the required stable (date, corpus unit, row id) sequential order."""
    if any(row.get("event_date") is None for row in rows):
        raise ValueError("S200 train keys require event_date on every scored row")
    positions = sorted(range(len(rows)), key=lambda index: (
        str(rows[index]["event_date"]), str(rows[index].get("corpus_unit", "")),
        str(rows[index].get("event_id", index)), index))
    dates = [str(rows[index]["event_date"]) for index in positions]
    assert all(left <= right for left, right in zip(dates, dates[1:]))
    return positions
def _date_groups(rows: Sequence[Mapping[str, Any]]) -> list[list[int]]:
    dates = [str(row.get("event_date", index)) for index, row in enumerate(rows)]
    assert all(left <= right for left, right in zip(dates, dates[1:]))
    groups: list[list[int]] = []
    for index, date in enumerate(dates):
        if not groups or date != dates[groups[-1][0]]:
            groups.append([])
        groups[-1].append(index)
    return groups
def train_only_keys(rows: Sequence[Mapping[str, Any]], probs: Sequence[float],
                    *, by_date_group: bool = True) -> list[str]:
    """Return regime keys whose confidence tercile uses prior scores only.
    ``buckets([row])`` supplies only the row-local phase/rest/month prefix; its
    singleton confidence is discarded. The ordered state is updated after the
    query, so no scored probability contributes to its own cut points.
    """
    if len(rows) != len(probs):
        raise ValueError("rows and probs must have equal length")
    prefixes = [buckets([row])[0].rsplit("|confidence=", 1)[0] for row in rows]
    state, keys = _OrderStatistics(), [""] * len(rows)
    groups = _date_groups(rows) if by_date_group else [[index] for index in range(len(rows))]
    for positions in groups:
        for index in positions:
            keys[index] = "%s|confidence=%s" % (prefixes[index], state.label(float(probs[index])))
        for index in positions:
            state.add(float(probs[index]))
    return keys
def changed_label_count(default_keys: Sequence[str], train_keys: Sequence[str]) -> int:
    """Count all confidence-label changes without excluding any scored row."""
    if len(default_keys) != len(train_keys):
        raise ValueError("key vectors must have equal length")
    return sum(
        confidence_label(default) != confidence_label(train)
        for default, train in zip(default_keys, train_keys)
    )
def oof_per_regime(
    probs: list[float], outcomes: list[float], keys: list[str], min_n: int,
    *, rows: Sequence[Mapping[str, Any]] | None = None,
    fallback_source: str = "full_sample",
    refit_every: int = 1,
) -> list[float]:
    """Return expanding outputs with declared full-sample or AS-OF routing."""
    if fallback_source not in ("full_sample", "prior_date"):
        raise ValueError("fallback_source must be 'full_sample' or 'prior_date'")
    cache_key = (tuple(probs), tuple(outcomes), min_n, refit_every)
    cached = _GLOBAL_OOF_CACHE.get(cache_key)
    if cached is None:
        cached = tuple(walk_forward_recalibrate(
            probs, outcomes, min_history=min_n, refit_every=refit_every))
        _GLOBAL_OOF_CACHE[cache_key] = cached
    # The cache is a pristine global walk. Every arm below gets its own list.
    calibrated = list(cached)
    if fallback_source == "prior_date":
        if rows is None:
            raise ValueError("prior-date fallback requires scored rows")
        history: dict[str, tuple[list[float], list[float]]] = {}
        for positions in _date_groups(rows):
            for index in positions:
                old_probs, old_outcomes = history.get(keys[index], ([], []))
                if len(old_probs) >= min_n:
                    fit = IsotonicRegression(out_of_bounds="clip").fit(old_probs, old_outcomes)
                    calibrated[index] = float(fit.transform([probs[index]])[0])
            for index in positions:
                old_probs, old_outcomes = history.setdefault(keys[index], ([], []))
                old_probs.append(probs[index])
                old_outcomes.append(outcomes[index])
        return calibrated
    fits = fit_per_regime(probs, outcomes, keys, min_n=min_n)
    global_fit = fits["GLOBAL"]
    for key in sorted(set(keys)):
        if fits[key] is global_fit:
            continue
        indices = [index for index, candidate in enumerate(keys) if candidate == key]
        local = walk_forward_recalibrate(
            [probs[index] for index in indices],
            [outcomes[index] for index in indices],
            min_history=min_n,
            refit_every=refit_every,
        )
        for index, value in zip(indices, local):
            calibrated[index] = float(value)
    return calibrated
_SPORTS = ("nba", "mlb", "soccer", "tennis")
_PREREG_PATH = "docs/evidence/harness/S200_regime_key_oof_prereg_2026-09-04.md"
_PREREG_SEAL = "BCDF43B637B3735078033ED47D9A1A21B1612FBB45BE5C694B72AB64AB4B4AFC"
def _paired_rows(default: Mapping[str, Any], train: Mapping[str, Any]) -> list[dict[str, Any]]:
    paired: list[dict[str, Any]] = []
    honest_rows = {row["row_index"]: row for row in train["s200_rows"]}
    if len(honest_rows) != len(train["s200_rows"]):
        raise ValueError("train row indices are not unique")
    for baseline in default["s200_rows"]:
        honest = honest_rows.get(baseline["row_index"])
        if honest is None:
            raise ValueError("default and train rows do not align")
        paired.append({
            "row_index": baseline["row_index"], "event_id": baseline["event_id"],
            "cluster_id": baseline["cluster_id"],
            "timestamp": None if baseline["timestamp"] is None else str(baseline["timestamp"]),
            "outcome": baseline["outcome"],
            "default_prediction": baseline["calibrated_prediction"],
            "train_prediction": honest["calibrated_prediction"],
            "default_squared_loss": baseline["squared_loss"],
            "train_squared_loss": honest["squared_loss"],
            "default_confidence": baseline["confidence_label"],
            "train_confidence": honest["confidence_label"],
            "label_changed": baseline["confidence_label"] != honest["confidence_label"],
        })
    return paired
def build_sport_summary(records: Any, sport: str, reference: Mapping[str, Any],
                        min_n: int = 200) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Score one preloaded corpus under both declared key sources."""
    from scripts.platformkit.eval_gate.calibration_report import build_report
    default = build_report(records, sport, min_n=min_n, include_rows=True)
    row_position = build_report(
        records, sport, min_n=min_n, key_source="train", include_rows=True,
        key_timing="row_position", fallback_source="full_sample")
    date_group_full = build_report(
        records, sport, min_n=min_n, key_source="train", include_rows=True,
        key_timing="date_group", fallback_source="full_sample")
    train = build_report(
        records, sport, min_n=min_n, key_source="train", include_rows=True,
        key_timing="date_group", fallback_source="prior_date")
    if default["scored_rows"] != train["scored_rows"]:
        raise ValueError("train path changed the scored denominator")
    paired = _paired_rows(default, train)
    changes = sum(row["label_changed"] for row in paired)
    if changes != train["confidence_label_change_count"]:
        raise ValueError("paired change count does not match the train report")
    return {
        "sport": sport,
        "input_rows": default["input_rows"], "scored_rows": default["scored_rows"],
        "dropped_rows": default["dropped_rows"],
        "ece_before": default["ece_before"],
        "default_ece_after": default["ece_after"],
        "row_position_key_ece_after": row_position["ece_after"],
        "date_group_key_ece_after": train["ece_after"],
        "date_group_minus_row_position_ece": train["ece_after"] - row_position["ece_after"],
        "train_ece_after": train["ece_after"],
        "train_minus_default_ece": train["ece_after"] - default["ece_after"],
        "label_change_count": changes,
        "default_path_abs_diff": abs(default["ece_after"] - reference["ece_after"]),
        "default_reproduction_max_abs_diff": default["reproduction_max_abs_diff"],
        "train_reproduction_max_abs_diff": train["reproduction_max_abs_diff"],
        "default_bins": default["reliability_bins_after"],
        "train_bins": train["reliability_bins_after"],
        "future_support_sensitivity": {
            "full_sample_support": {"ece_before": date_group_full["ece_before"],
                                    "ece_after": date_group_full["ece_after"]},
            "prior_date_support": {"ece_before": train["ece_before"],
                                   "ece_after": train["ece_after"]},
        },
        "default_verdict": default["verdict"], "train_verdict": train["verdict"],
    }, paired
def write_evidence(repo: Path | None = None) -> dict[str, Any]:
    """Write S212 evidence while loading exactly one corpus per iteration."""
    from scripts.platformkit.combo.corpus_cache import load_gate_corpus
    root = repo or Path(__file__).resolve().parents[3]
    evidence = root / "docs" / "evidence"
    entries: list[dict[str, Any]] = []
    paired_paths: list[str] = []
    for sport in _SPORTS:
        reference_path = evidence / "calibration" / (sport + "_reliability_2026-09-03.json")
        reference = json.loads(reference_path.read_text(encoding="utf-8"))
        records = load_gate_corpus(sport, portable=True)
        paired_path = evidence / ("S212_regime_key_clean_rerun_" + sport + "_paired_2026-09-04.json")
        summary, paired = build_sport_summary(records, sport, reference)
        paired_path.write_text(json.dumps({"sport": sport, "rows": paired}, indent=2) + "\n", encoding="utf-8")
        entries.append(summary)
        paired_paths.append(paired_path.relative_to(root).as_posix())
    artifact = {
        "prereg_path": _PREREG_PATH, "prereg_seal_sha256": _PREREG_SEAL,
        "method": "default global keys versus train-only confidence terciles",
        "zero_rows_dropped_required": True,
        "default_path_max_abs_diff": max(item["default_path_abs_diff"] for item in entries),
        "sports": entries, "paired_loss_artifacts": paired_paths,
    }
    output = evidence / "S212_regime_key_clean_rerun_2026-09-04.json"
    output.write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
    return artifact
def main() -> int:
    artifact = write_evidence()
    for item in artifact["sports"]:
        print("%s n=%d train_ece=%.6f label_changes=%d" % (
            item["sport"], item["scored_rows"], item["train_ece_after"], item["label_change_count"]))
    print("default_path_max_abs_diff=%.1f" % artifact["default_path_max_abs_diff"])
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
