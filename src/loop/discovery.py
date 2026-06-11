"""src/loop/discovery.py — the deterministic, LLM-FREE feature-discovery engine (closes the loop).

The autonomous loop went idle (held_out_spent + every seed hypothesis tested to max defer_attempts) because
it had no INEXHAUSTIBLE source of new candidates: a human/Claude had to author each ``signals/<name>.py``.
This engine is that source. It ENUMERATES candidate feature transforms over the existing leak-safe pergame
feature matrix, CHEAP-SCREENS them by target correlation + an orthogonality filter, and feeds the top-K to the
EXISTING honest gate (``src.loop.gate.evaluate``) which validates each with walk-forward + null-shuffle +
ablation + calibration + FDR. **No LLM anywhere** — candidates are pure deterministic transforms; the honest
gate (not a model) decides what ships.

WHY IT IS LEAK-SAFE: every candidate column is a PURE FUNCTION of the base columns, and
``build_pergame_dataset`` already computed those leak-free (as-of). A function of leak-safe inputs is leak-safe.
The candidate column is injected as ``signal._gate_matrix`` (the gate's fast path), so no per-row build / store
read happens — there is no surface through which post-decision info could enter.

WHY IT CANNOT SHIP NOISE: the gate's all-folds-improve + null-shuffle (z>=3) + ablation-vs-FULL + FDR
(Benjamini-Hochberg) reject spurious lift; the planted-null test (signals/gates.py) proves FWER control. The
cheap pre-screen only RANKS candidates to bound compute — the honest gate is the sole decider. A pure-noise
candidate REJECTs.

DEFAULT-OFF: nothing imports this on the prediction path. The orchestrator calls ``discover`` only when the
loop's discovery step is enabled; running this module changes no served value.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .gate import FeatureBundle, evaluate
from .signal import AsOfContext, GateResult, Hypothesis, Signal, SignalValue

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DISCOVERED_LEDGER = os.path.join(_REPO_ROOT, ".planning", "loop", "discovered_signals.jsonl")

# Unary + binary transform families. Each is a pure, deterministic function of base columns.
_BINARY = ("interact", "ratio", "diff")
_UNARY = ("square", "log1p_abs", "zscore")
_ORTHO_CAP = 0.92          # drop a candidate already ~collinear with a base column (gate would reject anyway)
_SCREEN_TOP_FEATURES = 24  # cap the binary combinatorics: pair only the top-K base cols by |corr(target)|
_MIN_FINITE_FRAC = 0.5     # a candidate must be finite on at least this fraction of rows


# --------------------------------------------------------------------------- specs

@dataclass(frozen=True)
class TransformSpec:
    """A deterministic feature transform over named base columns."""
    kind: str
    cols: Tuple[str, ...]

    @property
    def name(self) -> str:
        toks = "__".join(c.replace(" ", "_") for c in self.cols)
        return f"disc_{self.kind}__{toks}"[:120]

    def family_key(self) -> str:
        """Stable dedup key: kind + sorted column set (window/param-free, anti-re-roll)."""
        canon = self.kind + "|" + "|".join(sorted(self.cols))
        return "df_" + hashlib.blake2b(canon.encode(), digest_size=8).hexdigest()


def _apply(spec: TransformSpec, cols: Dict[str, np.ndarray]) -> np.ndarray:
    """Compute the candidate column for ``spec`` from a {name: column} dict. NaN-safe, no leakage."""
    if spec.kind == "interact":
        a, b = cols[spec.cols[0]], cols[spec.cols[1]]
        return a * b
    if spec.kind == "ratio":
        a, b = cols[spec.cols[0]], cols[spec.cols[1]]
        return a / (np.abs(b) + 1e-6)
    if spec.kind == "diff":
        return cols[spec.cols[0]] - cols[spec.cols[1]]
    if spec.kind == "square":
        return cols[spec.cols[0]] ** 2
    if spec.kind == "log1p_abs":
        return np.log1p(np.abs(cols[spec.cols[0]]))
    if spec.kind == "zscore":
        a = cols[spec.cols[0]]
        mu, sd = np.nanmean(a), np.nanstd(a)
        return (a - mu) / (sd + 1e-9)
    raise ValueError(f"unknown transform kind {spec.kind!r}")


def enumerate_specs(fc: List[str], base: np.ndarray, target: np.ndarray,
                    *, seen_families: Optional[set] = None,
                    top_features: int = _SCREEN_TOP_FEATURES) -> List[TransformSpec]:
    """Deterministically enumerate candidate transforms, family-deduped.

    To bound the pairwise combinatorics, binary transforms pair only the ``top_features`` base columns most
    correlated with the target; unary transforms cover those columns too. Order is fully deterministic.
    """
    seen_families = seen_families or set()
    fc_idx = {c: i for i, c in enumerate(fc)}
    # rank base columns by |corr(col, target)| (finite-safe) -> the screened pairing set
    corrs = []
    finite_t = np.isfinite(target)
    for c in fc:
        col = base[:, fc_idx[c]]
        m = finite_t & np.isfinite(col)
        if m.sum() < 30 or np.nanstd(col[m]) < 1e-9:
            corrs.append((c, 0.0)); continue
        r = abs(float(np.corrcoef(col[m], target[m])[0, 1]))
        corrs.append((c, 0.0 if not np.isfinite(r) else r))
    ranked = [c for c, _ in sorted(corrs, key=lambda t: (-t[1], t[0]))][:top_features]

    specs: List[TransformSpec] = []
    for c in ranked:                                   # unary
        for k in _UNARY:
            specs.append(TransformSpec(k, (c,)))
    for a, b in itertools.combinations(ranked, 2):     # binary (sorted pair => deterministic)
        for k in _BINARY:
            specs.append(TransformSpec(k, (a, b)))
    # family dedup (anti-re-roll) + stable order
    out, used = [], set(seen_families)
    for s in sorted(specs, key=lambda s: s.name):
        fk = s.family_key()
        if fk in used:
            continue
        used.add(fk)
        out.append(s)
    return out


# --------------------------------------------------------------------------- screen

def _screen_score(candidate: np.ndarray, target: np.ndarray, base: np.ndarray) -> float:
    """Cheap rank score: |corr(candidate, target)|, or -1 if degenerate / collinear with a base column."""
    m = np.isfinite(candidate) & np.isfinite(target)
    if m.sum() < 30 or (m.mean() < _MIN_FINITE_FRAC) or np.nanstd(candidate[m]) < 1e-9:
        return -1.0
    rt = float(np.corrcoef(candidate[m], target[m])[0, 1])
    if not np.isfinite(rt):
        return -1.0
    # orthogonality: drop if ~collinear with ANY base column (gate's ablation would reject it)
    cm = candidate[m]
    for j in range(base.shape[1]):
        bj = base[m, j]
        if np.nanstd(bj) < 1e-9:
            continue
        rb = float(np.corrcoef(cm, bj)[0, 1])
        if np.isfinite(rb) and abs(rb) > _ORTHO_CAP:
            return -1.0
    return abs(rt)


# --------------------------------------------------------------------------- signal wrapper

class DiscoveredSignal(Signal):
    """A Signal whose value is a precomputed transform column, injected via ``_gate_matrix``.

    The gate uses the injected :class:`FeatureBundle` directly (its fast path), so ``build`` is never called by
    the gate; we implement it as a neutral no-op for contract completeness.
    """

    scope = "pregame"

    def __init__(self, spec: TransformSpec, target: str, bundle: FeatureBundle) -> None:
        super().__init__(store=None)
        self.name = spec.name
        self.target = target
        self.spec = spec
        self._gate_matrix = bundle          # gate fast-path: evaluate on this bundle directly

    def build(self, ctx: AsOfContext) -> SignalValue:  # pragma: no cover - gate uses _gate_matrix
        return None

    def hypothesis(self) -> Hypothesis:
        return Hypothesis(
            name=self.name, target=self.target, scope=self.scope,
            statement=f"{self.spec.kind} of {' , '.join(self.spec.cols)} adds marginal signal for {self.target}",
            rationale=f"deterministic enumerated transform (family {self.spec.family_key()})",
            source="discovery", priority="P2")


# --------------------------------------------------------------------------- engine

@dataclass
class DiscoveryResult:
    spec: TransformSpec
    target: str
    screen_score: float
    gate: GateResult


def discover_from_matrix(base: np.ndarray, target: np.ndarray, fc: List[str], dates: List[str],
                         target_name: str, *, top_k: int = 12, device: str = "auto",
                         seen_families: Optional[set] = None) -> List[DiscoveryResult]:
    """Enumerate -> cheap-screen -> run the honest gate on the top-K candidates for one target.

    Returns a DiscoveryResult per gated candidate (verdict in ``.gate.verdict``). Pure: no I/O.
    """
    cols = {c: base[:, i] for i, c in enumerate(fc)}
    specs = enumerate_specs(fc, base, target, seen_families=seen_families)
    scored: List[Tuple[TransformSpec, float, np.ndarray]] = []
    for s in specs:
        try:
            cand = _apply(s, cols)
        except Exception:
            continue
        sc = _screen_score(cand, target, base)
        if sc > 0:
            scored.append((s, sc, cand))
    scored.sort(key=lambda t: (-t[1], t[0].name))     # rank by |corr|, deterministic tiebreak
    out: List[DiscoveryResult] = []
    for spec, sc, cand in scored[:top_k]:
        bundle = FeatureBundle(base=base, signal_col=cand, target=target, dates=dates)
        sig = DiscoveredSignal(spec, target_name, bundle)
        res = evaluate(sig, device=device)
        out.append(DiscoveryResult(spec=spec, target=target_name, screen_score=sc, gate=res))
    return out


# --------------------------------------------------------------------------- production data path

_MATRIX_CACHE: Dict[str, Any] = {}


def load_pergame_matrix() -> Tuple[np.ndarray, List[str], List[str], Dict[str, np.ndarray]]:
    """Load + cache the leak-safe pergame matrix (base, feature_cols, dates, {stat: target_vec}). Heavy."""
    if "base" in _MATRIX_CACHE:
        c = _MATRIX_CACHE
        return c["base"], c["fc"], c["dates"], c["targets"]
    try:
        from src.prediction.prop_pergame import build_pergame_dataset
    except Exception:  # pragma: no cover - dual import for the loop runtime
        from prediction.prop_pergame import build_pergame_dataset  # type: ignore
    rows, fc = build_pergame_dataset(min_prior=0)
    if not rows:
        raise RuntimeError("build_pergame_dataset returned no rows (the loop's DEFER condition)")
    rows.sort(key=lambda r: r["date"])
    base = np.array([[r.get(c, np.nan) for c in fc] for r in rows], dtype=float)
    dates = [r["date"] for r in rows]
    stats = ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov")
    targets = {s: np.array([r.get(f"target_{s}", np.nan) for r in rows], dtype=float) for s in stats}
    _MATRIX_CACHE.update(base=base, fc=fc, dates=dates, targets=targets)
    return base, fc, dates, targets


def discover(target: str = "pts", *, top_k: int = 12, device: str = "auto",
             seen_families: Optional[set] = None) -> List[DiscoveryResult]:
    """Production entry: load the real pergame matrix and discover transforms for ``target``."""
    base, fc, dates, targets = load_pergame_matrix()
    if target not in targets:
        raise ValueError(f"unknown target {target!r}; one of {sorted(targets)}")
    return discover_from_matrix(base, targets[target], fc, dates, target,
                                top_k=top_k, device=device, seen_families=seen_families)


# --------------------------------------------------------------------------- discovered-signal ledger

def load_discovered_families(path: str = _DISCOVERED_LEDGER) -> set:
    """Family-keys already tried by the discovery engine (anti-re-roll across loop iterations)."""
    fams: set = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    fams.add(json.loads(line)["family_key"])
                except Exception:
                    continue
    return fams


def record_discovered(dr: "DiscoveryResult", *, date: str, path: str = _DISCOVERED_LEDGER) -> None:
    """Append one discovery verdict to the discovered-signals ledger (the autonomous-discovery record)."""
    rec = {
        "name": dr.spec.name, "family_key": dr.spec.family_key(), "target": dr.target,
        "kind": dr.spec.kind, "cols": list(dr.spec.cols), "verdict": dr.gate.verdict.value,
        "screen_score": round(float(dr.screen_score), 4),
        "wf_all_improve": bool(dr.gate.wf_all_improve),
        "null_z": round(float(dr.gate.metrics.get("null_z", 0.0)), 3), "date": date,
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")
