"""ERROR-MINER + INTEL-SCANNER -- the hypothesis source for ARM A.

Two emitters (both leak-safe -- residuals are computed on logged OOF/holdout
predictions only, never on future games):

  1. RESIDUAL MINER -- ``load_residuals`` reads logged (pred, actual, line,
     context) rows; ``bucket_residuals`` slices them by ``stat x game-state
     (blowout/clutch/normal) x pace x rest x home/road x fav/dog x quarter`` and
     keeps buckets with a SYSTEMATIC bias (mean residual far from 0, n>=min_n,
     small p_value via a one-sample t-test). Each biased bucket -> a
     :class:`~src.loop.signal.Hypothesis`.
  2. INTEL-SCANNER -- ``intel_scan`` reads the atlas sections in the point-in-time
     store x the residual buckets to emit ATLAS-DERIVED signal hypotheses (the
     reinforcement edge: intelligence proposes new signals). A biased residual
     bucket whose context maps to an atlas section -> a candidate signal that
     reads that section as a feature.

Reuses (all optional / degrades to empty when offline): prediction JSONs +
``scored/`` files under ``data/predictions/`` (``prediction_tracker`` schema),
``data/models/bet_log.json``. The synthetic unit test exercises
``bucket_residuals`` + ``mine`` + ``intel_scan`` directly with injected rows so it
needs no live data.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .signal import Hypothesis, SCOPES, TARGETS
from .store import PointInTimeStore, entity_key

ROOT = Path(__file__).resolve().parents[2]
_PRED_DIR = ROOT / "data" / "predictions"
_SCORED_DIR = _PRED_DIR / "scored"
_BET_LOG = ROOT / "data" / "models" / "bet_log.json"

_STATS = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")

# How a context dimension value maps to an atlas section the intel-scanner can
# propose reading (dim_name -> {dim_value: (atlas_section, scope)}). This is the
# reinforcement map: a biased bucket on this dim suggests reading that section.
_DIM_TO_ATLAS: Dict[str, Dict[str, str]] = {
    "game_state": {
        "blowout": "on_off_impact",
        "clutch": "clutch",
    },
    "quarter": {  # any quarter bias -> the quarter-shape descriptive section
        "1": "quarter_shape", "2": "quarter_shape",
        "3": "quarter_shape", "4": "quarter_shape",
    },
    "pace": {"fast": "scoring_usage", "slow": "scoring_usage"},
    "fav_dog": {"fav": "on_off_impact", "dog": "on_off_impact"},
    "rest": {"b2b": "hustle", "rested": "hustle"},
    "home_road": {"home": "scoring_usage", "road": "scoring_usage"},
}


@dataclass
class ResidualBucket:
    """A residual slice with a measured systematic bias.

    Attributes:
        stat:       target stat (one of :data:`~src.loop.signal.TARGETS`).
        dims:       the bucket coordinates, e.g. ``{"game_state":"blowout","quarter":4}``.
        n:          sample size in the bucket.
        mean_resid: mean ``(pred - actual)`` -- the bias direction/magnitude.
        std_resid:  residual std (for the variance / interval angle).
        p_value:    significance of the bias vs 0 (one-sample t-test; feeds FDR).
    """

    stat: str
    dims: Dict[str, Any]
    n: int
    mean_resid: float
    std_resid: float
    p_value: float = 1.0

    def severity(self) -> float:
        """A priority score: standardised bias magnitude (|mean| / SE)."""
        if self.n <= 1 or self.std_resid <= 0:
            return abs(self.mean_resid)
        return abs(self.mean_resid) / (self.std_resid / math.sqrt(self.n))


# --------------------------------------------------------------------------- #
# 1. residual loading                                                          #
# --------------------------------------------------------------------------- #
def _coerce_quarter(val: Any) -> Optional[str]:
    """Normalise a snapshot/period field to a quarter label '1'..'4' (or None)."""
    if val is None:
        return None
    s = str(val).lower()
    for q in ("1", "2", "3", "4"):
        if q in s:
            return q
    return None


def _row_context(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the bucketing dims from a logged row (best-effort, all optional)."""
    dims: Dict[str, Any] = {}
    gs = raw.get("game_state")
    if gs is None:
        if raw.get("is_blowout") or raw.get("blowout"):
            gs = "blowout"
        elif raw.get("is_clutch") or raw.get("clutch"):
            gs = "clutch"
        else:
            gs = "normal"
    dims["game_state"] = str(gs)
    if (q := _coerce_quarter(raw.get("quarter")
                             or raw.get("snapshot_period")
                             or raw.get("period"))) is not None:
        dims["quarter"] = q
    if (hr := raw.get("home_road")) is not None:
        dims["home_road"] = str(hr)
    elif raw.get("is_home") is not None:
        dims["home_road"] = "home" if raw.get("is_home") else "road"
    if (fd := raw.get("fav_dog")) is not None:
        dims["fav_dog"] = str(fd)
    if (pace := raw.get("pace")) is not None:
        dims["pace"] = str(pace)
    if (rest := raw.get("rest")) is not None:
        dims["rest"] = str(rest)
    elif raw.get("is_b2b") or raw.get("b2b"):
        dims["rest"] = "b2b"
    return dims


def load_residuals(*, last_n_days: Optional[int] = None,
                   stats: Optional[List[str]] = None,
                   pred_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load logged ``(pred, actual, line, context)`` rows for residual analysis.

    Leak-safe: only reads ALREADY-SETTLED logged predictions (the prediction was
    made before the game; the actual is the realised box score). Reads the
    ``data/predictions/`` JSONs (``prediction_tracker`` schema -- ``props`` with
    ``predictions``/``confidence``) joined against ``scored/`` actuals when
    present. Returns a flat list of dicts ``{stat, pred, actual, resid, line,
    player_id, ...context}``. Degrades to ``[]`` when offline / no data.

    Args:
        last_n_days: if set, only include dates within this many days of the
            newest scored date found (coarse recency filter).
        stats: restrict to these target stats (default all 7).
        pred_dir: override the predictions directory (for tests).
    """
    want = tuple(stats) if stats else _STATS
    pdir = Path(pred_dir) if pred_dir else _PRED_DIR
    if not pdir.exists():
        return []
    rows: List[Dict[str, Any]] = []

    # actuals are most reliably found in scored/<date>_scored.json (clv_entries)
    # but those only carry edge plays; the richer signed-residual source is a
    # paired prediction JSON + box score. We read whatever signed pairs exist.
    scored_dir = pdir / "scored"
    actuals_by_date: Dict[str, Dict[str, Dict[str, float]]] = {}
    if scored_dir.exists():
        for f in sorted(scored_dir.glob("*_scored.json")):
            try:
                d = json.loads(f.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            date = d.get("date", f.name[:10])
            per_player: Dict[str, Dict[str, float]] = {}
            for e in d.get("clv_entries", []):
                pid = str(e.get("player_id", ""))
                stat = e.get("stat", "")
                if pid and stat and e.get("actual") is not None:
                    per_player.setdefault(pid, {})[stat] = float(e["actual"])
            if per_player:
                actuals_by_date[date] = per_player

    # iterate prediction JSONs, pair preds against any known actual
    for f in sorted(pdir.glob("*.json")):
        try:
            pred = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        gdate = pred.get("game_date", f.name[:10])
        actuals = actuals_by_date.get(gdate, {})
        for entry in pred.get("props", []):
            pid = str(entry.get("player_id", ""))
            preds = entry.get("predictions", {})
            actual_map = actuals.get(pid, {})
            base_ctx = _row_context({**pred, **entry})
            for stat in want:
                pv, av = preds.get(stat), actual_map.get(stat)
                if pv is None or av is None:
                    continue
                rows.append({
                    "stat": stat, "pred": float(pv), "actual": float(av),
                    "resid": float(pv) - float(av), "player_id": pid,
                    "game_date": gdate,
                    "line": entry.get("lines", {}).get(stat) if isinstance(
                        entry.get("lines"), dict) else None,
                    **base_ctx,
                })

    if last_n_days and rows:
        dates = sorted({r["game_date"] for r in rows if r.get("game_date")})
        if dates:
            keep = set(dates[-last_n_days:])
            rows = [r for r in rows if r.get("game_date") in keep]
    return rows


# --------------------------------------------------------------------------- #
# 2. bucketing                                                                 #
# --------------------------------------------------------------------------- #
# the dims we slice on, in priority order (most actionable first)
_BUCKET_DIMS = ("game_state", "quarter", "fav_dog", "rest",
                "home_road", "pace")


def _student_t_p(mean: float, std: float, n: int) -> float:
    """Two-sided p-value for H0: mean residual == 0 (normal approx of t-test)."""
    if n <= 1 or std <= 0:
        return 1.0 if mean == 0 else 0.0
    t = abs(mean) / (std / math.sqrt(n))
    # survival of standard normal *2 (large-n approx; conservative for the gate)
    z = t
    p = math.erfc(z / math.sqrt(2.0))
    return max(0.0, min(1.0, p))


def bucket_residuals(rows: List[Dict[str, Any]], *, min_n: int = 50
                     ) -> List[ResidualBucket]:
    """Bucket residuals across ``stat x`` each available context dim; keep buckets
    with ``n >= min_n`` and flag the systematic-bias magnitude / significance.

    Buckets are formed per single dimension (stat x one dim value) -- this keeps
    sample sizes meaningful and the emitted hypothesis interpretable. Returns
    buckets sorted by descending severity (standardised bias).
    """
    if not rows:
        return []
    # accumulate per (stat, dim_name, dim_value)
    acc: Dict[tuple, List[float]] = {}
    for r in rows:
        stat = r.get("stat")
        resid = r.get("resid")
        if stat is None or resid is None:
            continue
        try:
            resid = float(resid)
        except (TypeError, ValueError):
            continue
        for dim in _BUCKET_DIMS:
            if dim in r and r[dim] is not None:
                acc.setdefault((stat, dim, str(r[dim])), []).append(resid)

    buckets: List[ResidualBucket] = []
    for (stat, dim, val), resids in acc.items():
        n = len(resids)
        if n < min_n:
            continue
        mean = sum(resids) / n
        var = sum((x - mean) ** 2 for x in resids) / (n - 1) if n > 1 else 0.0
        std = math.sqrt(var)
        buckets.append(ResidualBucket(
            stat=stat, dims={dim: val}, n=n,
            mean_resid=round(mean, 4), std_resid=round(std, 4),
            p_value=round(_student_t_p(mean, std, n), 6),
        ))
    buckets.sort(key=lambda b: b.severity(), reverse=True)
    return buckets


def _is_systematic(b: ResidualBucket, *, min_abs_bias: float = 0.25,
                   max_p: float = 0.05) -> bool:
    """A bucket is a SYSTEMATIC bias if its mean is materially off 0 AND significant."""
    return abs(b.mean_resid) >= min_abs_bias and b.p_value <= max_p


def _bucket_slug(b: ResidualBucket) -> str:
    """Stable signal-slug for a bucket-derived hypothesis."""
    dim, val = next(iter(b.dims.items()))
    return f"{b.stat}_{dim}_{val}_bias".lower().replace(" ", "_")


def _bucket_hypothesis(b: ResidualBucket, *, source: str = "error_miner"
                       ) -> Hypothesis:
    """Build a :class:`Hypothesis` from a biased residual bucket."""
    dim, val = next(iter(b.dims.items()))
    direction = "over-predicts" if b.mean_resid > 0 else "under-predicts"
    scope = "live" if dim == "quarter" else "pregame"
    target = b.stat if b.stat in TARGETS else "pts"
    atlas_fields: List[str] = []
    sec = _DIM_TO_ATLAS.get(dim, {}).get(val)
    if sec:
        atlas_fields.append(sec)
    return Hypothesis(
        name=_bucket_slug(b),
        target=target,
        scope=scope if scope in SCOPES else "pregame",
        statement=(f"The model {direction} {b.stat} by {abs(b.mean_resid):.2f} "
                   f"on average when {dim}={val} (n={b.n})."),
        rationale=(f"Residual bucket {dim}={val}: mean_resid={b.mean_resid:+.3f}, "
                   f"p={b.p_value:.4f}, std={b.std_resid:.2f}. A correction feature "
                   f"keyed on {dim} should remove this systematic bias."),
        source=source,
        atlas_fields=atlas_fields,
        priority="P1" if b.severity() >= 4.0 else "P2",
    )


# --------------------------------------------------------------------------- #
# 3. intel-scanner (atlas x residuals -> atlas-derived hypotheses)             #
# --------------------------------------------------------------------------- #
def intel_scan(buckets: List[ResidualBucket], store: PointInTimeStore,
               *, top_k: int = 10) -> List[Hypothesis]:
    """Read atlas sections x residual buckets to emit atlas-derived signal
    hypotheses (the reinforcement path: intelligence proposes signals).

    For each biased bucket whose context dim maps to an atlas section
    (:data:`_DIM_TO_ATLAS`), and for which the store actually has at least one
    entity carrying that section, emit a hypothesis for a signal that READS that
    section as a feature (atlas x opponent-scheme = interaction feature). Buckets
    whose mapped section is absent from the store are skipped (DEFER -- the
    descriptive arm has not built it yet).
    """
    if store is None or not buckets:
        return []
    # which atlas sections currently exist in the store (cheap scan of fields)
    present_sections = set()
    try:
        for (_, fld) in list(store._index.keys()):  # noqa: SLF001 (introspection)
            present_sections.add(fld)
    except Exception:  # pragma: no cover - defensive
        present_sections = set()

    hyps: List[Hypothesis] = []
    seen = set()
    for b in buckets:
        if not _is_systematic(b):
            continue
        dim, val = next(iter(b.dims.items()))
        sec = _DIM_TO_ATLAS.get(dim, {}).get(val)
        if not sec or sec not in present_sections:
            continue
        slug = f"{b.stat}_{sec}_atlas_signal".lower()
        if slug in seen:
            continue
        seen.add(slug)
        target = b.stat if b.stat in TARGETS else "pts"
        hyps.append(Hypothesis(
            name=slug,
            target=target,
            scope="live" if dim == "quarter" else "pregame",
            statement=(f"Players with a strong '{sec}' atlas profile show a "
                       f"systematic {b.stat} residual when {dim}={val}; the atlas "
                       f"section predicts the bias."),
            rationale=(f"intel-scan: bucket {dim}={val} mean_resid="
                       f"{b.mean_resid:+.3f} (n={b.n}) x atlas section '{sec}' "
                       f"present in store -> read '{sec}' (and its opponent-scheme "
                       f"interaction) as a leak-safe correction feature."),
            source="intel_scanner",
            atlas_fields=[sec],
            priority="P1",
        ))
    hyps.sort(key=lambda h: 0 if h.priority == "P1" else 1)
    return hyps[:top_k]


# --------------------------------------------------------------------------- #
# 4. top-level mine                                                            #
# --------------------------------------------------------------------------- #
def mine(*, store: Optional[PointInTimeStore] = None, top_k: int = 20,
         rows: Optional[List[Dict[str, Any]]] = None,
         min_n: int = 50) -> List[Hypothesis]:
    """Return a prioritised hypothesis queue from residual buckets + the
    intel-scanner, deduped against already-tested signals via the ledger.

    Args:
        store: the point-in-time store (enables the intel-scanner). If None, only
            residual-bucket hypotheses are returned.
        top_k: cap on returned hypotheses.
        rows: pre-loaded residual rows (else ``load_residuals`` is called).
        min_n: minimum bucket size passed to :func:`bucket_residuals`.
    """
    resid_rows = rows if rows is not None else load_residuals()
    buckets = bucket_residuals(resid_rows, min_n=min_n)

    hyps: List[Hypothesis] = [
        _bucket_hypothesis(b) for b in buckets if _is_systematic(b)
    ]
    if store is not None:
        hyps.extend(intel_scan(buckets, store, top_k=top_k))

    # dedup by slug against the ledger's already-tested set (best-effort import)
    tested: set = set()
    try:
        from .ledger import already_tested  # local import: avoid cycle / skeleton
        hyps = [h for h in hyps if not (already_tested(h.name, kind="signal"))]
    except Exception:  # ledger may be a skeleton mid-build
        pass

    # dedup within this batch by name, keep first (higher priority sorts first)
    _PRIO = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    hyps.sort(key=lambda h: _PRIO.get(h.priority, 2))
    out: List[Hypothesis] = []
    seen: set = set()
    for h in hyps:
        if h.name in seen:
            continue
        seen.add(h.name)
        out.append(h)
    return out[:top_k]
