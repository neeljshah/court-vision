"""G368 -- evaluated-tick motion audit of the row producer.

Sealed definitions: docs/evidence/tracking/g368_evaluated_tick_motion_2026-09-09/
g368_prereg_2026-09-09.md. Measures only; never edits src/, data/ or the register.
"""
from __future__ import annotations

import argparse
import hashlib
import math
from pathlib import Path

import pandas as pd

from scripts.platformkit.tracking.g359_held_position import collapse_held

COLS = ["frame", "player_id", "x_position", "y_position", "confidence",
        "bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2"]
BBOX = ["bbox_x1", "bbox_y1", "bbox_x2", "bbox_y2"]
CLASSES = ("UNATTRIBUTED", "COAST_LOST", "BBOX_FROZEN", "CLAMP_OR_SUBPIXEL")
OUTCOMES = ("KEPT", "REMOVED_TAIL", "SPLIT")
FRESH_CONFIDENCE = 1.0
PREMISE_MOTION_MIN = 0.90
ATTRIBUTION_BAR = 0.95
PROPOSAL_TRIGGER = 0.20
_i = "{:06d}".format
_f = "{:.6f}".format


def write(path: Path, rows: list[dict], append: bool) -> None:
    """Write rows as CSV with LF endings; --append concatenates a second corpus."""
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    if append and path.exists():
        frame = pd.concat([pd.read_csv(path, dtype=str, keep_default_na=False), frame])
    frame.to_csv(path, index=False, lineterminator="\n")


def nearest(values: list, quantile: float, default=0.0):
    """Nearest-rank order statistic -- no library-version dependence."""
    if not values:
        return default
    ordered = sorted(values)
    return ordered[min(max(1, math.ceil(quantile * len(ordered))), len(ordered)) - 1]


def section_rows(sections_csv: Path) -> list[tuple[str, str]]:
    """(section_name, recorded tracking sha256) -- eligible rows only when marked."""
    frame = pd.read_csv(sections_csv, dtype=str, keep_default_na=False)
    if "eligible" in frame.columns:
        frame = frame.loc[frame["eligible"] == "1"]
    names = frame["section_name"].tolist()
    digests = (frame["tracking_sha256"].tolist()
               if "tracking_sha256" in frame.columns else [""] * len(names))
    return list(zip(names, digests))


def load(path: Path) -> pd.DataFrame:
    """Sealed load: strings only, numeric tick from the table's own `frame` field."""
    table = pd.read_csv(path, dtype=str, keep_default_na=False, usecols=COLS)
    tick = pd.to_numeric(table["frame"], errors="coerce")
    unparsed, table = int(tick.isna().sum()), table.assign(_tick=tick).dropna(subset=["_tick"])
    table = table.sort_values(["player_id", "_tick"], kind="stable").reset_index(drop=True)
    table = rerank(table)
    table.attrs["unparsed"] = unparsed
    return table


def rerank(table: pd.DataFrame) -> pd.DataFrame:
    """(Re)derive the tick rank so adjacency is computed over the rows present."""
    order = {value: index for index, value in enumerate(sorted(set(table["_tick"].tolist())))}
    return table.assign(_rank=table["_tick"].map(order))


def _shift(table: pd.DataFrame, column: str) -> pd.Series:
    return table.groupby("player_id", sort=False)[column].shift(1)


def held_flag(table: pd.DataFrame) -> pd.Series:
    """A held step: (x, y) byte-identical to the previous row of the same track."""
    return (table["x_position"].eq(_shift(table, "x_position"))
            & table["y_position"].eq(_shift(table, "y_position")))


def motion_of(table: pd.DataFrame) -> dict:
    """Share of consecutive evaluated-tick pairs on which >= 1 shared track moves."""
    n_ticks = int(table["_rank"].nunique())
    moved = _shift(table, "_rank").eq(table["_rank"] - 1) & ~held_flag(table)
    pairs = max(n_ticks - 1, 0)
    moved_pairs = int(table.loc[moved, "_rank"].nunique())
    return {"ticks": n_ticks, "tick_pairs": pairs, "moved_pairs": moved_pairs,
            "motion_share": moved_pairs / pairs if pairs else 0.0}


def run_ids(table: pd.DataFrame) -> pd.Series:
    """Maximal chains of pairwise-held rows within a track; unique across tracks."""
    return (~held_flag(table)).cumsum()


def census(table: pd.DataFrame) -> dict:
    """Held-run distribution and the share of rows lying inside runs of length >= K."""
    sizes = table.assign(_run=run_ids(table)).groupby("_run").size()
    held = sizes.loc[sizes >= 2].tolist()
    rows = len(table)
    out = {"runs_n": _i(len(sizes)), "held_runs_n": _i(len(held)),
           "held_steps_n": _i(int((sizes - 1).clip(lower=0).sum())),
           "run_len_p50": _i(nearest(held, 0.50, "")) if held else "",
           "run_len_p90": _i(nearest(held, 0.90, "")) if held else "",
           "run_len_max": _i(max(held)) if held else ""}
    for minimum in (2, 5, 30):
        inside = int(sizes.loc[sizes >= minimum].sum())
        out["tick_share_in_runs_ge{}".format(minimum)] = _f(inside / rows if rows else 0.0)
    return out


def classify(table: pd.DataFrame) -> pd.Series:
    """Sealed class per HELD step, first match wins in the order C1..C4; else blank."""
    confidence = pd.to_numeric(table["confidence"], errors="coerce")
    prev_known = pd.concat([_shift(table, name).ne("") for name in BBOX], axis=1).all(axis=1)
    bbox_same = pd.concat([table[name].eq(_shift(table, name)) for name in BBOX],
                          axis=1).all(axis=1)
    out = pd.Series(CLASSES[3], index=table.index, dtype=object)
    out = out.mask(confidence.eq(FRESH_CONFIDENCE) & bbox_same, CLASSES[2])
    out = out.mask(confidence.lt(FRESH_CONFIDENCE), CLASSES[1])
    out = out.mask(confidence.isna() | ~prev_known, CLASSES[0])
    return out.where(held_flag(table), "")


def run_class(steps: pd.Series) -> str:
    """Majority class over a run's held steps; ties break to the earliest sealed class."""
    counts = steps.value_counts()
    return max(CLASSES, key=lambda name: (counts.get(name, 0), -CLASSES.index(name)))


def coast_rows(table: pd.DataFrame) -> pd.Series:
    """A row emitted with no detection on that tick: confidence strictly below 1.0."""
    return pd.to_numeric(table["confidence"], errors="coerce").lt(FRESH_CONFIDENCE)


def run_report(table: pd.DataFrame) -> tuple[dict, dict]:
    """Per-class held-run counts and per-class M1 outcomes, measured via collapse_held."""
    marked = table.assign(_run=run_ids(table), _key=range(len(table)))
    adapted = pd.DataFrame({"cls": "player", "track_id": marked["player_id"],
                            "x": marked["x_position"], "y": marked["y_position"],
                            "frame": marked["_tick"], "_key": marked["_key"]})
    collapsed, dropped = collapse_held(adapted)
    survived = set() if collapsed is None else set(collapsed["_key"].tolist())
    classes = classify(marked)
    runs = dict.fromkeys(CLASSES, 0)
    outcome = {name: dict.fromkeys(OUTCOMES, 0) for name in CLASSES}
    for _, run in marked.groupby("_run", sort=False):
        if len(run) < 2:
            continue
        alive = [key in survived for key in run["_key"].tolist()]
        verdict = ("KEPT" if all(alive)
                   else "REMOVED_TAIL" if alive[0] and not any(alive[1:]) else "SPLIT")
        name = run_class(classes.loc[run.index[1:]])
        runs[name] += 1
        outcome[name][verdict] += 1
    return runs, {"outcome": outcome, "dropped": int(dropped)}


def each_section(args):
    """Yield (name, digest, table_or_None, status) for every named section."""
    root = Path(args.tracking_root)
    for name, digest in section_rows(Path(args.sections)):
        path = root / name / "tracking_data.csv"
        if not path.exists():
            print("ABSENT-SECTION {}".format(name))
            yield name, digest, None, "ABSENT"
        else:
            yield name, digest, load(path), "PRESENT"


def cmd_motion(args) -> None:
    from scripts.platformkit.tracking import g368_controls_strips as extra
    rows = []
    root = Path(args.tracking_root)
    records = extra.ledger_records(Path(args.ledger)) if args.ledger else {}
    for name, digest, table, status in each_section(args):
        row = {"section_name": name, "corpus": args.corpus, "status": status}
        if table is not None:
            actual = hashlib.sha256(
                (root / name / "tracking_data.csv").read_bytes()).hexdigest()
            measured = motion_of(table)
            row.update({"rows": _i(len(table)), "tracks": _i(table["player_id"].nunique()),
                        "unparsed_frame_rows": _i(table.attrs.get("unparsed", 0)),
                        "ticks": _i(measured["ticks"]),
                        "tick_pairs": _i(measured["tick_pairs"]),
                        "moved_pairs": _i(measured["moved_pairs"]),
                        "motion_share": _f(measured["motion_share"]),
                        "ledger_evaluated_frames": str(
                            records.get(name, {}).get("evaluated_frames", "")),
                        "sidecar_evaluated_frames": extra.sidecar_evaluated(root / name),
                        "recorded_sha256": digest, "observed_sha256": actual,
                        "sha256_check": "" if not digest else
                        ("MATCH" if digest == actual else "DIFFER")})
        rows.append(row)
    write(Path(args.out), rows, args.append)
    shares = [float(row["motion_share"]) for row in rows if "motion_share" in row]
    median = nearest(shares, 0.50)
    verdict = "PREMISE FALSE" if median >= PREMISE_MOTION_MIN else "PREMISE HOLDS"
    print("{} corpus={} n={} median_motion_share={}".format(
        verdict, args.corpus, len(shares), _f(median)))


def cmd_runs(args) -> None:
    rows = []
    for name, _digest, table, status in each_section(args):
        row = {"section_name": name, "corpus": args.corpus, "status": status}
        if table is not None:
            row.update({"rows": _i(len(table)), "ticks": _i(int(table["_rank"].nunique())),
                        "tracks": _i(table["player_id"].nunique())})
            row.update(census(table))
        rows.append(row)
    write(Path(args.out), rows, args.append)
    print("RUNS corpus={} n={}".format(args.corpus, len(rows)))


def cmd_attribute(args) -> None:
    rows, total, attributed = [], 0, 0
    for name, _digest, table, status in each_section(args):
        if table is None:
            rows.append({"section_name": name, "corpus": args.corpus, "status": status})
            continue
        steps = classify(table)
        steps = steps.loc[steps.ne("")]
        runs, _ = run_report(table)
        n_runs = sum(runs.values())
        coast = _f(int(coast_rows(table).sum()) / len(table) if len(table) else 0.0)
        total += len(steps)
        attributed += int(steps.ne(CLASSES[0]).sum())
        for name_class in CLASSES:
            picked = int((steps == name_class).sum())
            rows.append({"section_name": name, "corpus": args.corpus, "status": status,
                         "class": name_class, "held_steps": _i(picked),
                         "held_step_share": _f(picked / len(steps) if len(steps) else 0.0),
                         "runs": _i(runs[name_class]),
                         "run_share": _f(runs[name_class] / n_runs if n_runs else 0.0),
                         "coast_row_share": coast})
    write(Path(args.out), rows, args.append)
    share = attributed / total if total else 0.0
    print("ATTRIBUTED corpus={} held_steps={} share={} bar={}".format(
        args.corpus, total, _f(share), _f(ATTRIBUTION_BAR)))


def cmd_consequence(args) -> None:
    rows = []
    for name, _digest, table, status in each_section(args):
        row = {"section_name": name, "corpus": args.corpus, "status": status}
        if table is not None:
            _runs, report = run_report(table)
            coast = coast_rows(table)
            fresh = table.loc[~coast]
            row["motion_share"] = _f(motion_of(table)["motion_share"])
            row["motion_share_no_coast"] = _f(
                motion_of(rerank(fresh))["motion_share"] if len(fresh) else 0.0)
            row["coast_row_share"] = _f(int(coast.sum()) / len(table) if len(table) else 0.0)
            row["m1_rows_dropped"] = _i(report["dropped"])
            for name_class in CLASSES:
                for verdict in OUTCOMES:
                    row["{}_{}".format(name_class, verdict)] = _i(
                        report["outcome"][name_class][verdict])
        rows.append(row)
    write(Path(args.out), rows, args.append)
    shares = [float(row["coast_row_share"]) for row in rows if "coast_row_share" in row]
    median = nearest(shares, 0.50)
    print("CONSEQUENCE corpus={} median_coast_row_share={} proposal {}".format(
        args.corpus, _f(median), "FIRES" if median >= PROPOSAL_TRIGGER else "DOES NOT FIRE"))


def main() -> None:
    from scripts.platformkit.tracking import g368_controls_strips as extra
    parser = argparse.ArgumentParser(description="G368 evaluated-tick motion audit")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, handler in (("motion", cmd_motion), ("runs", cmd_runs),
                          ("attribute", cmd_attribute), ("consequence", cmd_consequence),
                          ("strips", extra.cmd_strips)):
        child = sub.add_parser(name)
        child.add_argument("--sections", required=True)
        child.add_argument("--corpus", required=True)
        child.add_argument("--tracking-root", required=True)
        child.add_argument("--ledger", default="")
        child.add_argument("--append", action="store_true")
        child.add_argument("--out", required=True)
        child.set_defaults(handler=handler)
    child = sub.add_parser("controls")
    child.add_argument("--scratch", required=True)
    child.add_argument("--out", required=True)
    child.set_defaults(handler=extra.cmd_controls)
    child = sub.add_parser("summary")
    child.add_argument("--evidence", required=True)
    child.add_argument("--out", required=True)
    child.set_defaults(handler=extra.cmd_summary)
    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
