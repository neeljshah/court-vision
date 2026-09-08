"""S328 external as-of replay primitives; the finisher supplies the landed arm callbacks."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

import pandas as pd

from scripts.platformkit.eval_gate.adapter_contract import require_accepted

Arm = Callable[[pd.DataFrame, Mapping[str, object], "RecordingLoader"], float]
FrameBuilder = Callable[[pd.DataFrame, Mapping[str, object]], tuple[list[dict], list[dict]]]
DELAYS_SECONDS = (0, 30, 60, 120)


class AccessViolation(AssertionError):
    """Raised when a callback asks its recording loader for unjoined source rows."""


class RecordingLoader:
    """Permit callback reads only from the externally joined, per-state frame."""

    def __init__(self, allowed: pd.DataFrame) -> None:
        self._allowed = self._keys(allowed)
        self._frame = allowed.copy()
        self.violations: list[str] = []

    @staticmethod
    def _keys(rows: pd.DataFrame) -> set[tuple[str, int]]:
        return {(str(row.game_id), int(row.ts)) for row in rows[["game_id", "ts"]].itertuples(index=False)}

    def read(self, rows: pd.DataFrame | None = None) -> pd.DataFrame:
        """Return a copy of an allowed frame or reject every out-of-frame source row."""
        if rows is None:
            return self._frame.copy()
        requested = self._keys(rows)
        outside = requested - self._allowed
        if outside:
            self.violations.append("outside_frame_rows=%d" % len(outside))
            raise AccessViolation(self.violations[-1])
        return rows.copy()


@dataclass(frozen=True)
class ReplayRecord:
    """One arm/state/delay replay record, including its external-access audit."""

    state_id: int
    game_id: str
    state_ts_s: int
    delay_seconds: int
    arm: str
    p_full_prefix_probability: float | None
    p_deleted_prefix_probability: float | None
    p_delay_probability: float | None
    prefix_changed: int
    delay_changed: int
    absolute_delay_change_probability: float | None
    delay_window_records: int
    access_violations: int
    verdict: str


def external_asof_frame(source: pd.DataFrame, state: Mapping[str, object], delay_seconds: int) -> pd.DataFrame:
    """Build one game-local frame outside the arm, excluding rows after its as-of cutoff."""
    if delay_seconds < 0:
        raise ValueError("delay_seconds must be nonnegative")
    cutoff = int(state["ts"]) - delay_seconds
    game = source.loc[source["game_id"].astype(str).eq(str(state["game_id"]))]
    return game.loc[game["ts"].astype(int).le(cutoff)].sort_values("ts", kind="stable").copy()


def _call(arm: Arm, frame: pd.DataFrame, state: Mapping[str, object]) -> tuple[float | None, int]:
    loader = RecordingLoader(frame)
    try:
        value = float(arm(frame.copy(), state, loader))
        if not 0.0 <= value <= 1.0:
            raise ValueError("arm returned probability outside [0, 1]")
    except AccessViolation:
        value = None
    return value, len(loader.violations)


def _validated(frame: pd.DataFrame, state: Mapping[str, object], builder: FrameBuilder) -> None:
    features, labels = builder(frame, state)
    require_accepted(features, labels)


def replay_state(source: pd.DataFrame, state: Mapping[str, object], arm_name: str, arm: Arm,
                 builder: FrameBuilder) -> list[ReplayRecord]:
    """Replay one sealed state for every S328 delay with an independent external join."""
    zero = external_asof_frame(source, state, 0)
    deleted_source = source.loc[source["ts"].astype(int).le(int(state["ts"]))].copy()
    deleted = external_asof_frame(deleted_source, state, 0)
    _validated(zero, state, builder)
    _validated(deleted, state, builder)
    p_zero, zero_access = _call(arm, zero, state)
    p_deleted, deleted_access = _call(arm, deleted, state)
    prefix_changed = int(p_zero is None or p_deleted is None or p_zero != p_deleted)
    game = source.loc[source["game_id"].astype(str).eq(str(state["game_id"]))]
    output: list[ReplayRecord] = []
    for delay in DELAYS_SECONDS:
        frame = external_asof_frame(source, state, delay)
        _validated(frame, state, builder)
        p_delay, access = _call(arm, frame, state)
        window = game.loc[(game["ts"].astype(int) > int(state["ts"]) - delay) &
                          (game["ts"].astype(int) <= int(state["ts"]))]
        change = None if p_zero is None or p_delay is None else abs(p_zero - p_delay)
        changed = int(change is None or change != 0.0)
        violations = zero_access + deleted_access + access
        bad_delay = delay > 0 and changed and window.empty
        verdict = "VIOLATION" if prefix_changed or violations or bad_delay else "ACCEPTED"
        output.append(ReplayRecord(
            int(state["state_id"]), str(state["game_id"]), int(state["ts"]), delay, arm_name,
            p_zero, p_deleted, p_delay,
            prefix_changed, changed, change, len(window), violations, verdict,
        ))
    return output


def replay(source: pd.DataFrame, states: pd.DataFrame, arms: Mapping[str, Arm], builder: FrameBuilder) -> pd.DataFrame:
    """Run all arms on nonterminal states; source reads stay outside every arm callback."""
    required = {"state_id", "game_id", "ts"}
    missing = required - set(states.columns)
    if missing:
        raise ValueError("states missing %s" % ",".join(sorted(missing)))
    details = source.loc[:, ["game_id", "ts", "period", "game_clock_s"]].copy()
    details["game_id"] = details["game_id"].astype(str)
    if details.duplicated(["game_id", "ts"]).any():
        raise ValueError("source has duplicate game_id/ts state rows")
    joined = states.drop(columns=["period", "game_clock_s"], errors="ignore").copy()
    joined["game_id"] = joined["game_id"].astype(str)
    joined = joined.merge(details, on=["game_id", "ts"], how="left", validate="many_to_one")
    if joined[["period", "game_clock_s"]].isna().any().any():
        raise ValueError("sealed state absent from source")
    active = joined.loc[~((joined["period"].astype(int) >= 4) & (joined["game_clock_s"].astype(float) == 0))]
    records: list[dict[str, object]] = []
    for state in active.to_dict(orient="records"):
        for arm_name, arm in arms.items():
            records.extend(item.__dict__ for item in replay_state(source, state, arm_name, arm, builder))
    return pd.DataFrame(records)


def summary(records: pd.DataFrame) -> pd.DataFrame:
    """Return the required arm-by-delay table from replay records only."""
    grouped = records.groupby(["arm", "delay_seconds"], sort=True)
    return grouped.agg(
        n_states=("state_id", "size"), n_changed=("delay_changed", "sum"),
        n_prefix_changed=("prefix_changed", "sum"), n_access_violations=("access_violations", "sum"),
        max_probability_change=("absolute_delay_change_probability", lambda values: float(values.max()) if len(values) else 0.0),
        n_delay_window_records=("delay_window_records", "sum"),
    ).reset_index()


def write_replay(records: pd.DataFrame, path: str) -> None:
    """Write replay rows with ASCII and zero-padded integer cells for the S328 archive."""
    output = records.copy()
    for column in ("state_id", "state_ts_s", "delay_seconds", "prefix_changed", "delay_changed",
                   "delay_window_records", "access_violations"):
        output[column] = output[column].astype(int).map("%06d".__mod__)
    output.to_csv(path, index=False, encoding="ascii", lineterminator="\n")


def losses_from_evaluator(records: Sequence[Mapping[str, object]], baseline: str, candidate: str) -> pd.DataFrame:
    """Archive paired Brier losses from shared-evaluator records, never raw callback output."""
    needed = {"state_key", "game_id", "ts", "y", baseline, candidate}
    rows = list(records)
    if any(needed - set(row) for row in rows):
        raise ValueError("evaluator record missing required field")
    result = pd.DataFrame(rows)
    if not result["state_key"].is_unique:
        raise ValueError("one evaluator state is required for each scored tick")
    y = result["y"].astype(float)
    result["baseline_brier_loss"] = (result[baseline].astype(float) - y) ** 2
    result["candidate_brier_loss"] = (result[candidate].astype(float) - y) ** 2
    return result[["state_key", "game_id", "ts", "baseline_brier_loss", "candidate_brier_loss"]]
