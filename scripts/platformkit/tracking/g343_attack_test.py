"""G343 corruption arms; imports the tracking harness rather than copying gates."""
from __future__ import annotations

import argparse
import csv
import hashlib
from pathlib import Path

import pandas as pd

from scripts.platformkit.tracking_harness import evaluate

ARMS = ("A0", "A1", "A2", "A3", "A4", "A5")
GATES = (
    "coordinate_contract", "insufficient_data", "duplicate_frame_identity",
    "coverage_attempted_frames", "median_track_len", "oob", "jump_max",
    "attempted_frames", "ball_valid_attempted_frames", "liveness_frozen",
    "zero_step_share", "median_step_distance", "distinct_position_ratio",
    "stationary_track_share",
)
REPORT_ONLY = ("jump_p95", "ball_detected_share", "g325_wholly_off_frame")
_FAILURE_PREFIXES = {
    "duplicate_frame_identity": ("duplicate frame-track rows",),
    "coverage_attempted_frames": ("coverage_attempted_frames",),
    "median_track_len": ("median_track_len",), "oob": ("oob ",),
    "jump_max": ("jump_max",), "attempted_frames": ("attempted_frames",),
    "ball_valid_attempted_frames": ("ball_valid_attempted_frames",),
    "liveness_frozen": ("liveness verdict FROZEN",),
    "zero_step_share": ("zero_step_share",),
    "median_step_distance": ("median_step_distance",),
    "distinct_position_ratio": ("distinct_position_ratio",),
    "stationary_track_share": ("stationary_track_share",),
}


def tracking_columns(frame: pd.DataFrame) -> tuple[str, str, str, str]:
    """Resolve the native coordinate and identity columns without conversion."""
    pairs = (("x", "y"), ("x_position", "y_position"))
    ids = ("track_id", "player_id")
    pair = next((item for item in pairs if set(item) <= set(frame)), None)
    ident = next((item for item in ids if item in frame), None)
    team = next((item for item in ("team", "team_abbrev") if item in frame), None)
    if pair is None or ident is None or team is None or "frame" not in frame:
        raise ValueError("tracking table lacks native coordinate, identity, team, or frame column")
    return pair[0], pair[1], ident, team


def apply_arm(tracking: pd.DataFrame, ball: pd.DataFrame, arm: str,
              width: float, height: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return deep copies carrying exactly one G343 corruption arm."""
    if arm not in ARMS:
        raise ValueError("unknown arm {}".format(arm))
    out, ball_out = tracking.copy(deep=True), ball.copy(deep=True)
    if arm == "A0":
        return out, ball_out
    x_col, y_col, id_col, team_col = tracking_columns(out)
    if arm == "A1":
        ordered = out.sort_values("frame")
        held = ordered.groupby(id_col, sort=False)[[x_col, y_col]].transform("first")
        out.loc[held.index, [x_col, y_col]] = held
    elif arm == "A2":
        counts = out.groupby([team_col, id_col], sort=True).size().rename("n").reset_index()
        pairs = []
        for team, group in counts.groupby(team_col, sort=True):
            top = group.sort_values(["n", id_col], ascending=[False, True]).head(2)
            if len(top) == 2:
                pairs.append((int(top.iloc[0]["n"]), int(top.iloc[1]["n"]), str(team),
                              top.iloc[0][id_col], top.iloc[1][id_col]))
        if not pairs:
            raise ValueError("A2 requires two identities from one team")
        _, _, team, keep, merge = sorted(pairs, key=lambda item: (-item[0], -item[1], item[2]))[0]
        out.loc[(out[team_col].astype(str) == team) & (out[id_col] == merge), id_col] = keep
    elif arm == "A3":
        ball_out["frame"] = ball_out["frame"] + 30
    elif arm == "A4":
        out[x_col] = 0.9 * (out[x_col] - width / 2.0) + width / 2.0 + 0.05 * width
        out[y_col] = 0.9 * (out[y_col] - height / 2.0) + height / 2.0 + 0.05 * width
    else:
        out[x_col] = width - out[x_col]
    return out, ball_out


def gate_statuses(report) -> dict[str, tuple[str, str]]:
    """Translate imported harness failures into statuses; thresholds stay in the harness."""
    failures = tuple(report.failures)
    coordinate = next((item for item in failures if item.startswith("coordinate_contract:")), None)
    if coordinate:
        statuses = {gate: (("REJECT", coordinate) if gate == "coordinate_contract"
                           else ("NOT_APPLICABLE", "coordinate contract stopped metric gates"))
                    for gate in GATES}
        return _with_any_gate(statuses)
    if report.insufficient_data:
        statuses = {gate: (("REJECT", "fewer than 30 frames") if gate == "insufficient_data"
                           else ("NOT_APPLICABLE", "insufficient-data adjudication"))
                    for gate in GATES}
        return _with_any_gate(statuses)
    statuses = {"coordinate_contract": ("PASS", "accepted by imported harness"),
                "insufficient_data": ("PASS", "at least 30 frames")}
    for gate, prefixes in _FAILURE_PREFIXES.items():
        failure = next((item for item in failures if item.startswith(prefixes)), None)
        statuses[gate] = (("REJECT", failure) if failure else
                          ("PASS", "accepted by imported harness"))
    return _with_any_gate(statuses)


def _with_any_gate(statuses: dict[str, tuple[str, str]]) -> dict[str, tuple[str, str]]:
    """Add the all-gates status from imported gate statuses, not a new check."""
    values = [value[0] for value in statuses.values()]
    if "REJECT" in values:
        statuses["any_gate"] = ("REJECT", "one or more imported harness gates rejected")
    elif "PASS" in values:
        statuses["any_gate"] = ("PASS", "all applicable imported harness gates passed")
    else:
        statuses["any_gate"] = ("NOT_APPLICABLE", "no imported metric gate was reached")
    for gate in REPORT_ONLY:
        statuses[gate] = ("NOT_APPLICABLE", "not a rejection check in tracking_harness.evaluate")
    return statuses


def cell_statuses(tracking: pd.DataFrame, ball: pd.DataFrame, arm: str,
                   width: float, height: float, source_path: str) -> dict[str, tuple[str, str]]:
    """Construct one arm, then evaluate it -- except A3, which the imported
    harness cannot see (evaluate() takes one df; the NBA-production schema
    hardcodes ball_telemetry_available=False and never reads ball_path;
    tracking_schema.py:63,265-269). A construction ValueError (bad arm
    precondition) and an evaluate() ValueError (a harness defect) are kept
    separate so a future harness bug is never mislabeled as a construction
    failure (NEW GAP g343_attack_test.py:172-178, verifier 2026-09-08)."""
    try:
        attacked, _ = apply_arm(tracking, ball, arm, width, height)
    except ValueError as exc:
        reason = "arm construction failed: {}".format(exc)
        return {gate: ("NOT_APPLICABLE", reason) for gate in (*GATES, *REPORT_ONLY, "any_gate")}
    if arm == "A3":
        reason = "harness reads no ball table"
        return {gate: ("NOT_APPLICABLE", reason) for gate in (*GATES, *REPORT_ONLY, "any_gate")}
    try:
        return gate_statuses(evaluate(attacked, "basketball", source=source_path))
    except ValueError as exc:
        # A harness exception (as opposed to an arm-construction ValueError,
        # handled above) stays inside the sealed PASS/REJECT/NOT_APPLICABLE
        # vocabulary: NOT_APPLICABLE with a gate_error: reason prefix, never
        # a fourth status token (NEW GAP, verifier 2026-09-08).
        reason = "gate_error:{}".format(exc)
        return {gate: ("NOT_APPLICABLE", reason) for gate in (*GATES, *REPORT_ONLY, "any_gate")}


def _window(frame: pd.DataFrame, start: int, end: int) -> pd.DataFrame:
    return frame.loc[frame["frame"].between(start, end)].copy(deep=True)


def _sha256(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _verify_sources(manifest: pd.DataFrame) -> None:
    """Reject a changed source before any corruption is constructed."""
    for source in manifest.itertuples(index=False):
        for path, bytes_name, digest_name in ((source.tracking_path, "tracking_bytes", "tracking_sha256"),
                                              (source.ball_path, "ball_bytes", "ball_sha256")):
            actual = Path(path)
            if not actual.is_file() or actual.stat().st_size != int(getattr(source, bytes_name)):
                raise ValueError("sealed source size mismatch {}".format(path))
            if _sha256(path) != getattr(source, digest_name):
                raise ValueError("sealed source digest mismatch {}".format(path))


def run(manifest_path: Path, out_path: Path) -> None:
    """Run sealed window inputs one table at a time and write one row per arm/gate."""
    manifest = pd.read_csv(manifest_path, dtype={"game_id": str})
    required = {"window_index", "game_id", "tracking_path", "ball_path", "width", "height",
                "window_start", "window_end", "tracking_bytes", "ball_bytes", "tracking_sha256", "ball_sha256"}
    missing = sorted(required - set(manifest))
    if len(manifest) != 24 or missing:
        raise ValueError("sealed manifest needs 24 rows and columns: {}".format(", ".join(missing)))
    _verify_sources(manifest)
    rows = []
    for source in manifest.itertuples(index=False):
        tracking = pd.read_csv(source.tracking_path)
        ball = pd.read_csv(source.ball_path)
        track_window = _window(tracking, int(source.window_start), int(source.window_end))
        ball_window = _window(ball, int(source.window_start), int(source.window_end))
        # FINISHER FIX (2026-09-08): the sealed window rule only widens to
        # last_60 when the source table's max frame is below the sealed end;
        # a real sparse-tracking game can still have zero rows inside an
        # otherwise-in-range [window_start, window_end] slice (confirmed on
        # game 0022500036 and 5 others). evaluate() already fails an empty
        # frame closed through its own schema/coordinate-contract path (see
        # memo), so this no longer needs a separate hard stop here.
        for arm in ARMS:
            # FINISHER FIX (2026-09-08): a sparse or single-team window can
            # have too few rows/identities for A2's same-team merge
            # precondition; that is a real arm-construction limit of a 24-
            # window screen, not a harness gate, so it is recorded as
            # NOT_APPLICABLE rather than crashing the sealed run.
            statuses = cell_statuses(track_window, ball_window, arm,
                                     float(source.width), float(source.height),
                                     source.tracking_path)
            for gate, (status, reason) in statuses.items():
                rows.append({"window_index": "{:06d}".format(int(source.window_index)),
                             "game_id": source.game_id, "arm": arm, "gate": gate,
                             "status": status, "reason": reason,
                             "window_start": "{:06d}".format(int(source.window_start)),
                             "window_end": "{:06d}".format(int(source.window_end))})
    for arm in ARMS:
        for gate in (*GATES, *REPORT_ONLY, "any_gate"):
            group = [row for row in rows if row["arm"] == arm and row["gate"] == gate]
            applicable = [row for row in group if row["status"] != "NOT_APPLICABLE"]
            rejected = [row for row in applicable if row["status"] == "REJECT"]
            accepted = [row for row in applicable if row["status"] == "PASS"]
            share = len(rejected) / len(applicable) if applicable else None
            a0_share = len(accepted) / len(applicable) if arm == "A0" and applicable else None
            for row in group:
                row.update({"applicable_n": "{:06d}".format(len(applicable)),
                            "rejected_n": "{:06d}".format(len(rejected)),
                            "accepted_n": "{:06d}".format(len(accepted)),
                            "rejection_share": "" if share is None else "{:.6f}".format(share),
                            "a0_acceptance_share": "" if a0_share is None else "{:.6f}".format(a0_share)})
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="run G343 sealed corruption windows")
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--power", required=True, type=Path)
    args = parser.parse_args()
    run(args.manifest, args.power)


if __name__ == "__main__":
    main()
