"""Full member matrix and reconstructible Q9 series; Q5 survivors are never promoted.
Only the member-allowance interval decides; Romano-Wolf is secondary.
"""
from __future__ import annotations
import csv
import io
import math
from decimal import Decimal
from numbers import Real
from typing import Dict, List, Sequence, Tuple
import numpy as np
import pandas as pd
from scripts.platformkit.eval_gate.signal_audit_family import (
    EVALUABLE, MEMBER_FIELDS, strict_int,
)
from scripts.platformkit.ingame.gate_a0_ingame_vs_market import (
    N_BOOT, N_MIN_GAMES, SEED, cluster_bootstrap, logloss, verdict as gate_verdict,
)
from scripts.platformkit.eval_gate.romano_wolf import romano_wolf_stepdown
EPS_FAMILY = 0.05
AHEAD = "AHEAD(SINGLE-WINDOW)"
BEHIND = "BEHIND"
UNDERPOWERED = "UNDERPOWERED"
COVERAGE = "UNDERPOWERED:feature_coverage"
NOT_EVALUABLE = "NOT_EVALUABLE"
REFUSED = "REFUSED"
VERDICTS = (AHEAD, BEHIND, UNDERPOWERED, NOT_EVALUABLE, REFUSED)
SURVIVOR_NOTE = ("requires its own sealed prereg on a second corpus and min_corpora_eff "
                 "at the launch K before any statement")
STEP_FIELDS = ("x_feature", "beta", "mu", "sd", "n_train", "train_ids_sha256")
TEXT_FIELDS = ("game_id", "ts", "train_ids_sha256")
SERIES_FIELDS = ("game_id", "ts", "p_candidate", "p_reference", "y") + STEP_FIELDS + ("loss_candidate", "loss_reference", "d")
ROW_FIELDS = MEMBER_FIELDS + (
    "n_games", "n_states", "n_states_at_min_train", "point", "ci95", "verdict",
    "ci_member_allowance", "rw_adjusted_p", "rw_adjusted_reject", "tail_rank",
    "largest_single_game_share", "leave_one_game_out_range", "logloss_point",
    "tail_unresolved", "logloss_ci95", "paired_loss_series", "coverage", "note",
)

def label_verdict(raw: str) -> str:
    """Map the landed gate_a0 word onto this row's vocabulary. AHEAD is single-window."""
    text = str(raw)
    if text == "AHEAD":
        return AHEAD
    if text not in (BEHIND, UNDERPOWERED):
        raise ValueError("unexpected landed verdict %r" % raw)
    return text

def _clusters(series: Sequence[dict]) -> List[Tuple[str, float, float, int]]:
    """Collapse to (game_id, sum_a, sum_b, n) clusters, sorted so state order never leaks."""
    grouped: Dict[str, List[float]] = {}
    for row in series:
        acc = grouped.setdefault(str(row["game_id"]), [0.0, 0.0, 0])
        acc[0] += float(row["loss_candidate"])
        acc[1] += float(row["loss_reference"])
        acc[2] += 1
    return [(key, grouped[key][0], grouped[key][1], int(grouped[key][2]))
            for key in sorted(grouped)]

def point_estimate(series: Sequence[dict]) -> float:
    """The cluster-weighted point, identical in form to the landed cluster_bootstrap."""
    clusters = _clusters(series)
    total = sum(item[3] for item in clusters)
    if total <= 0:
        raise ValueError("an empty paired-loss series has no point")
    return float((sum(i[1] for i in clusters) - sum(i[2] for i in clusters)) / total)

def largest_single_game_share(series: Sequence[dict]) -> float:
    """Share of the absolute cluster differential carried by the single largest game."""
    magnitudes = [abs(a - b) for _key, a, b, _n in _clusters(series)]
    total = sum(magnitudes)
    if total <= 0.0:
        return 0.0
    return float(max(magnitudes) / total)

def leave_one_game_out_range(series: Sequence[dict]) -> List[float]:
    """[min, max] of the point recomputed with each game dropped in turn."""
    clusters = _clusters(series)
    if len(clusters) < 2:
        raise ValueError("leave-one-game-out needs at least two game clusters")
    sum_a = sum(i[1] for i in clusters)
    sum_b = sum(i[2] for i in clusters)
    total = sum(i[3] for i in clusters)
    points = []
    for _key, a, b, n in clusters:
        remaining = total - n
        if remaining <= 0:
            raise ValueError("dropping one game left no states")
        points.append((sum_a - a - (sum_b - b)) / remaining)
    return [float(min(points)), float(max(points))]


def render_series(series: Sequence[dict], identity: Sequence[Tuple[str, str]] = ()) -> str:
    """Q9: the paired-loss series beside the summary. The header carries the point (the rows
    alone reproduce it) and the digests naming the manifest and corpus a moved CSV came from."""
    buffer = io.StringIO()
    buffer.write("# point=%.17g n_states=%d%s\n" % (point_estimate(series), len(series), "".join(" %s=%s" % kv for kv in identity)))
    writer = csv.DictWriter(buffer, fieldnames=list(SERIES_FIELDS), lineterminator="\n")
    writer.writeheader()
    for row in series:
        writer.writerow({name: row[name] for name in SERIES_FIELDS})
    return buffer.getvalue()


def parse_series(text: str) -> List[dict]:
    """Read back a rendered series (the reconstruction tests' only input)."""
    lines = [line for line in text.splitlines() if not line.startswith("#")]
    return [{key: (value if key in TEXT_FIELDS or value == "" else float(value))
             for key, value in row.items()}
            for row in csv.DictReader(io.StringIO("\n".join(lines) + "\n"))]


def member_row(member: dict, **fields: object) -> dict:
    """One full-matrix row: the member's sealed identity plus the scored columns."""
    row = {name: member[name] for name in MEMBER_FIELDS}
    defaults = {name: None for name in ROW_FIELDS if name not in MEMBER_FIELDS}
    row.update(defaults)
    unknown = sorted(set(fields) - set(ROW_FIELDS))
    if unknown:
        raise ValueError("unknown member row field(s) %s" % unknown)
    row.update(fields)
    return validate_member(row)


def not_evaluable_row(member: dict) -> dict:
    """A NOT_EVALUABLE member is listed with its reason and consumes nothing."""
    if member["evaluability"] == EVALUABLE:
        raise ValueError("%r is EVALUABLE; it must be scored, not listed"
                         % member["member_key"])
    return member_row(member, verdict=NOT_EVALUABLE, note=member["evaluability"])


def refused_row(member: dict, reason: str) -> dict:
    """A declared-EVALUABLE member whose feature could not be built: counted, not zeroed."""
    return member_row(member, verdict=REFUSED, note=str(reason))


def _finite_real(value: object, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
        raise ValueError("%s must be a finite non-bool real, got %r" % (field, value))

def _coverage_counts(counts: dict, prefix: str = "coverage") -> None:
    for name, value in counts.items():
        field = "%s.%s" % (prefix, name)
        if isinstance(value, dict):
            _coverage_counts(value, field)
        else:
            strict_int(value, field)

def validate_member(row: dict) -> dict:
    """Refuse a row with the wrong fields, a non-strict-int count or a bad interval."""
    if set(row) != set(ROW_FIELDS):
        raise ValueError("member row fields must be exactly %s, got %s"
                         % (list(ROW_FIELDS), sorted(row)))
    if row["verdict"] not in VERDICTS:
        raise ValueError("verdict must be one of %s, got %r" % (list(VERDICTS), row["verdict"]))
    for name in ("n_games", "n_states", "n_states_at_min_train", "tail_rank"):
        if row[name] is not None:
            strict_int(row[name], name)
    if row["coverage"] is not None:
        _coverage_counts(row["coverage"])
    for name in ("point", "logloss_point", "largest_single_game_share", "rw_adjusted_p"):
        if row[name] is not None:
            _finite_real(row[name], name)
    for name in ("ci95", "ci_member_allowance", "leave_one_game_out_range", "logloss_ci95"):
        bounds = row[name]
        if bounds is None:
            continue
        if not isinstance(bounds, list) or len(bounds) != 2:
            raise ValueError("%s must be a [lo, hi] pair, got %r" % (name, bounds))
        for bound in bounds:
            _finite_real(bound, name)
        if bounds[0] > bounds[1]:
            raise ValueError("%s is inverted: %r" % (name, bounds))
    if row["rw_adjusted_reject"] is not None and not isinstance(row["rw_adjusted_reject"], bool):
        raise TypeError("rw_adjusted_reject must be a bool or None")
    if row["ci_member_allowance"] is None and (
            row["verdict"] in (AHEAD, BEHIND)
            or (row["verdict"] == UNDERPOWERED and not str(row["note"] or "").startswith(COVERAGE))):
        raise ValueError("%r was scored without a member-allowance interval" % row["member_key"])
    return row


def underpowered_row(member: dict, note: str, coverage: dict) -> dict:
    """Under the landed n_min games with a finite feature: UNDERPOWERED, never scored.

    No interval exists because nothing was scored -- the coverage census IS the result.
    """
    if not str(note).startswith(COVERAGE):
        raise ValueError("a coverage row must carry the %s reason, got %r" % (COVERAGE, note))
    return member_row(member, verdict=UNDERPOWERED, coverage=dict(coverage), note=str(note))

def survivors(rows: Sequence[dict]) -> List[dict]:
    """Name every AHEAD(SINGLE-WINDOW) member. This tool NEVER promotes one (Q5)."""
    return [{"member_key": row["member_key"], "signal_id": row["signal_id"],
             "source": row["source"], "verdict": AHEAD,
             "hypothesis": row["hypothesis"], "requirement": SURVIVOR_NOTE}
            for row in rows if row["verdict"] == AHEAD]
def census(rows: Sequence[dict]) -> Dict[str, int]:
    """Strict-int counts of the full matrix, one bucket per verdict word."""
    counts = {name: 0 for name in VERDICTS}
    for row in rows:
        counts[row["verdict"]] += 1
    counts["n_rows"] = len(rows)
    return counts
def bootstrap_draws(frame: pd.DataFrame, col_a: str, col_b: str, n_boot: int = N_BOOT,
                    seed: int = SEED) -> Tuple[float, np.ndarray]:
    """The landed cluster_bootstrap's own draws, kept so BOTH intervals share them.
    Identical in construction to it (same groupby, generator, per-draw integers and ratio);
    `score_member` asserts the 0.05 pair off these draws IS cluster_bootstrap's output.
    """
    rng = np.random.default_rng(seed)
    g = frame.groupby("game_id").agg(sa=(col_a, "sum"), sb=(col_b, "sum"), n=(col_a, "size"))
    sa, sb, nn = g["sa"].to_numpy(), g["sb"].to_numpy(), g["n"].to_numpy()
    n_games = len(g)
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        pick = rng.integers(0, n_games, n_games)
        diffs[i] = (sa[pick].sum() - sb[pick].sum()) / nn[pick].sum()
    return float((sa.sum() - sb.sum()) / nn.sum()), diffs
def interval(diffs: np.ndarray, allowance: float) -> List[float]:
    """The two-sided interval at `allowance` over already-drawn game-clustered draws."""
    if not 0.0 < float(allowance) < 1.0:
        raise ValueError("allowance %r must lie in (0,1)" % allowance)
    half = float(allowance) * 100.0 / 2.0
    lo, hi = np.percentile(diffs, [half, 100.0 - half])
    return [float(lo), float(hi)]
def paired_series(candidate: Sequence[dict], reference: Sequence[dict],
                  trace: Sequence[dict] = ()) -> Tuple[List[dict], List[dict]]:
    """Per-state paired Brier and log-loss series (candidate minus reference), Q9.
    Sorted by (game_id, ts), so the archive and everything derived from it are independent
    of the order the arms' records arrived in. Each row also carries the MODEL side of its
    step -- both probabilities, the label, the feature, the fitted beta and z-scaling, and
    the training slice it was fitted on (size + id digest) -- so p_candidate rebuilds from
    the archive alone. A step the trace does not cover leaves those columns empty.
    """
    ref_by_key = {(r["game_id"], r["ts"]): r for r in reference}
    steps = {(str(s["game_id"]), str(s["ts"])): s for s in trace}
    if len(ref_by_key) != len(reference):
        raise ValueError("duplicate (game_id, ts) in the reference arm; refusing to merge")
    brier_rows, logloss_rows = [], []
    for row in sorted(candidate, key=lambda r: (str(r["game_id"]), str(r["ts"]))):
        key = (row["game_id"], row["ts"])
        if key not in ref_by_key:
            raise ValueError("candidate state %r is absent from the reference arm" % (key,))
        base = ref_by_key[key]
        y = float(strict_int(row["y"], "y"))
        step = steps.get((str(row["game_id"]), str(row["ts"])), {})
        pair = {"game_id": str(row["game_id"]), "ts": str(row["ts"]), "y": y,
                "p_candidate": float(row["p_model"]), "p_reference": float(base["p_model"]),
                **{name: step.get(name) for name in STEP_FIELDS}}
        cand_b, ref_b = (float(row["p_model"]) - y) ** 2, (float(base["p_model"]) - y) ** 2
        losses = logloss(np.array([row["p_model"], base["p_model"]], float),
                         np.array([y, y], float))
        brier_rows.append({**pair, "loss_candidate": cand_b, "loss_reference": ref_b,
                           "d": cand_b - ref_b})
        logloss_rows.append({**pair, "loss_candidate": float(losses[0]),
                             "loss_reference": float(losses[1]),
                             "d": float(losses[0] - losses[1])})
    return brier_rows, logloss_rows
def score_member(brier_rows: Sequence[dict], logloss_rows: Sequence[dict],
                 allowance: Decimal, n_boot: int, seed: int, n_min: int) -> dict:
    """Same draws for both intervals; tail_rank counts complete draws in one tail.
    Zero complete draws means unresolved nominal coverage; percentiles still interpolate.
    """
    frame = pd.DataFrame(list(brier_rows))
    point, diffs = bootstrap_draws(frame, "loss_candidate", "loss_reference", n_boot, seed)
    ci95 = interval(diffs, EPS_FAMILY)
    landed = cluster_bootstrap(frame, "loss_candidate", "loss_reference", n_boot=n_boot, seed=seed)
    if (point, ci95[0], ci95[1]) != landed:
        raise AssertionError("draws diverge from cluster_bootstrap: %r != %r"
                             % ((point, ci95[0], ci95[1]), landed))
    if abs(point - point_estimate(brier_rows)) > 1e-9:
        raise AssertionError("the archived series does not reconstruct the point")
    ci_member = interval(diffs, float(allowance))
    n_games = int(frame["game_id"].nunique())
    ll_point, ll_diffs = bootstrap_draws(pd.DataFrame(list(logloss_rows)), "loss_candidate",
                                         "loss_reference", n_boot, seed)
    tail_rank = int(allowance * strict_int(n_boot, "n_boot") / Decimal(2))
    return {"n_games": n_games, "n_states": int(len(frame)), "point": point, "ci95": ci95,
            "ci_member_allowance": ci_member, "logloss_point": ll_point,
            "tail_rank": tail_rank, "tail_unresolved": bool(tail_rank < 1.0),
            "logloss_ci95": interval(ll_diffs, EPS_FAMILY),
            "verdict": label_verdict(gate_verdict(ci_member[0], ci_member[1], n_games,
                                                  n_min=n_min)),
            "largest_single_game_share": largest_single_game_share(brier_rows),
            "leave_one_game_out_range": leave_one_game_out_range(brier_rows)}
def common_romano_wolf(payloads: Sequence[dict], n_bootstrap: int | None, n_min: int) -> dict:
    """Secondary stepdown: identical state keys and shared game resampling for all arms."""
    if not payloads:
        return {}
    maps = [{(r["game_id"], r["ts"]): r for r in p["brier"]} for p in payloads]
    keys = sorted(set.intersection(*(set(m) for m in maps)))
    if any(set(m) != set(maps[0]) for m in maps[1:]) and len({k[0] for k in keys}) < n_min:
        raise ValueError("unequal_coverage: common games below minimum")
    result = romano_wolf_stepdown([[-m[k]["d"] for k in keys] for m in maps],
                                  [[k[0] for k in keys] for _ in maps],
                                  **({} if n_bootstrap is None else {"n_bootstrap": int(n_bootstrap)}))
    return {"adjusted_p": result.adjusted_p, "rejected": result.rejected,
            "n_bootstrap": int(result.n_bootstrap), "n_states_common": len(keys)}
