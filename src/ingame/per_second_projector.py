"""Per-second in-game projection stream — FRONT C (the per-second product).

Built ON TOP of the VALIDATED leak-free SBS v2 player-line head
(``src/ingame/continuous_projection.py::UnifiedPlayerLineProjector`` +
``state_featurizer.py``; eval ``scripts/ingame/eval_sbs_v2.py``). It turns the
per-EVENT point estimate into a CONTINUOUS per-second projection stream.

WHAT IT DOES, per (player, stat), at any wall-clock second of a live game:
  * holds the v2 per-event point estimate (``projected_final``),
  * DECAYS the uncertainty interval (``lo``/``hi``) every second as game-time
    elapses — the band half-width is calibrated from the held-out residual MAE
    curve in ``.planning/ingame/eval_curve_v2.json`` and interpolated
    continuously vs ``game_remaining_min``,
  * the point estimate JUMPS only when a new event arrives (a new state row);
    between events ONLY the clock and the interval move.
Plus, per game tick: ``team`` current/projected score + ``home_win_prob`` from
the ACCEPTED time-and-score logistic baseline (the learned win-prob head was a
net regression and is NOT used — see Second_By_Second_Engine.md §3-5).

HONESTY (stated in code so no writeup can overclaim — HARD HONESTY RULES):
  * **Accuracy updates at EVENTS, not between them.** A "second" with no new
    PBP event carries the previous event's point estimate UNCHANGED. The only
    thing the per-second stream adds between events is (a) the ticking clock and
    (b) a deterministic time-decay of the interval band. There is NO new
    information and NO accuracy gain between events. This is a continuous
    DISPLAY on a per-event accuracy core, not magic between-event accuracy.
  * **Interval calibration is empirical + held-out.** Band half-width at
    game-time T = z(stat,T,nominal) * MAE_resid(stat, T), where MAE_resid is the
    v2 held-out walk-forward MAE from eval_curve_v2.json (linear-interpolated in
    game-remaining-minutes, decaying monotonically to ~0 at the buzzer) and
    ``z`` is a per-(stat, game-time bucket) multiplier CALIBRATED so the band's
    stated NOMINAL coverage (default 80%, also 50%) matches reality on the
    held-out residual set. With a raw residual sample the z is the empirical
    abs-residual quantile over MAE; with only aggregate MAE on disk it is the
    closed-form LAPLACE z (z=-ln(1-nominal): ~1.609 for 80%, ~0.693 for 50%).
    This FIXES the old flat z=1.0 caveat (an MAE band is only ~58% coverage, NOT
    the ~68% a Gaussian-sigma reading implies). ``IntervalCalibrator.
    calibrate_coverage()`` REPORTS achieved coverage per (stat, bucket). We do
    NOT claim a Gaussian sigma we did not fit.
  * **Win-prob = accepted baseline only.** ``sigmoid(0.40*margin/sqrt(rem_min))``
    — identical to ``eval_second_by_second.baseline_winprob`` which beat the
    learned head at all 7 grid points.
  * **Team score = naive pace** (research-only per the verdict; flagged as such).

GATING: any LIVE use must be behind env flag ``CV_INGAME_SBS`` (default OFF),
mirroring ``CV_INGAME_ATLAS``. ``is_enabled()`` reads it; ``stream_*`` helpers
become no-ops (return ``None``) when disabled, so wiring this into the live
engine cannot change a served value unless the flag is explicitly set.

This module is ADDITIVE: it imports the existing v2 projector + featurizer and
adds nothing to the serving default. It does not modify any live serving path.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from src.ingame.continuous_projection import (
    PLAYER_STATS,
    SBS_V2_DIR,
    UnifiedPlayerLineProjector,
    _PLAYER_CURRENT_COL,
)

# --------------------------------------------------------------------------- #
# Paths / flag
# --------------------------------------------------------------------------- #
ROOT = Path(__file__).resolve().parent.parent.parent
EVAL_CURVE_V2 = ROOT / ".planning" / "ingame" / "eval_curve_v2.json"

#: Live-use gate. Mirrors CV_INGAME_ATLAS. Default OFF.
INGAME_SBS_FLAG = "CV_INGAME_SBS"

REG_GAME_SEC = 48 * 60  # 2880


def is_enabled() -> bool:
    """True iff the per-second SBS stream is allowed to affect live serving.

    Reads ``CV_INGAME_SBS`` (default OFF). With the flag unset, callers that
    respect ``stream_*`` no-op behaviour are byte-identical to today.
    Delegates to ``src.ingame.sbs_shadow.is_enabled`` so that all truthy
    spellings (1, true, yes, on, y, t) are accepted consistently.
    """
    from src.ingame.sbs_shadow import is_enabled as _sbs_is_enabled  # avoid cycles
    return _sbs_is_enabled()


# --------------------------------------------------------------------------- #
# Interval calibration: held-out residual-MAE vs game-time, per stat.
# --------------------------------------------------------------------------- #
# The eval grid is keyed by elapsed game-seconds (360=6min ... 2520=42min). We
# read the v2_pace held-out MAE at each grid point and build, per stat, a
# monotone-ish curve of residual MAE vs *remaining* game-minutes. The band at an
# arbitrary live moment is obtained by linear interpolation in remaining-minutes,
# pinned to ~0 at the final buzzer (rem=0) so the interval collapses to the point
# estimate as the game ends.

# Default grid-second -> remaining-minute mapping for a regulation game.
def _grid_sec_to_remaining_min(grid_sec: int) -> float:
    return max(0.0, (REG_GAME_SEC - float(grid_sec)) / 60.0)


# Nominal coverages we calibrate / report. 0.80 = the displayed band; 0.50 = IQR.
DEFAULT_NOMINAL_COVERAGES: Tuple[float, ...] = (0.80, 0.50)


def _laplace_z_for_coverage(coverage: float) -> float:
    """Closed-form z so that ``[mu - z*MAE, mu + z*MAE]`` covers ``coverage`` of
    a *Laplace* residual distribution (MAE == the Laplace scale ``b``).

    For Laplace(0, b): P(|x| <= t) = 1 - exp(-t/b). With half-width t = z*b,
    coverage = 1 - exp(-z)  ->  z = -ln(1 - coverage).

    This is the PRINCIPLED prior we fall back to when no raw residual sample is
    available (the shipped ``eval_curve_v2.json`` stores only aggregate MAE per
    (stat, bucket), not the residual sample). Count-stat residuals are roughly
    Laplace/double-exponential, so an MAE band's true coverage is ~58% (z=1),
    NOT the ~68% a Gaussian-sigma reading would imply. To hit 80% you need
    z = -ln(0.20) ~= 1.609; to hit 50%, z = -ln(0.50) ~= 0.693.
    """
    c = min(max(float(coverage), 1e-6), 1.0 - 1e-9)
    return float(-math.log(1.0 - c))


@dataclass
class IntervalCalibrator:
    """Per-stat residual-MAE band, calibrated from held-out eval, by remaining min.

    For each stat we store sorted (remaining_min, mae) knots. ``band(stat, rem)``
    linearly interpolates MAE in remaining-minutes and multiplies by an EMPIRICAL
    per-(stat, bucket) ``z_mult`` (see ``z_table``), so the band's STATED nominal
    coverage matches reality on the held-out residual set. The band MONOTONICALLY
    DECAYS toward 0 as rem -> 0 (we append a (0.0, 0.0) knot), which is what makes
    the per-second interval shrink as time elapses.

    Coverage calibration (fixes the z_mult=1.0 caveat):
      * If a RAW held-out residual sample is supplied (``fit_z_from_residuals`` /
        ``from_residual_dump``), per (stat, bucket, nominal) we pick the z that
        makes ``[pred - z*MAE, pred + z*MAE]`` cover ~nominal of the actual
        residuals (empirical-quantile / abs-residual quantile over MAE).
      * If only aggregate MAE is available (``from_eval_curve`` on the shipped
        eval_curve_v2.json), we fall back to the closed-form LAPLACE z for the
        nominal coverage (``_laplace_z_for_coverage``) — honest, distribution-
        based, and far better calibrated than the old flat z_mult=1.0 (~58%).

    ``z_mult`` (legacy scalar) is RETAINED for backward-compat: when ``z_table``
    has no entry for a (stat, nominal) it is the multiplier used. Default 1.0
    reproduces the old MAE band exactly, so existing callers are unchanged.
    """

    knots: Dict[str, List[Tuple[float, float]]] = field(default_factory=dict)
    z_mult: float = 1.0
    method_key: str = "v2_pace"
    source: str = "uncalibrated_fallback"
    #: nominal_coverage -> stat -> remaining_min_bucket -> z multiplier.
    #: Buckets keyed by remaining-min knot; lookup snaps to nearest knot.
    z_table: Dict[float, Dict[str, Dict[float, float]]] = field(default_factory=dict)
    #: nominal_coverage used by ``band`` when none is passed explicitly.
    default_nominal: float = 0.80
    z_source: str = "uncalibrated"

    # ------------------------------------------------------------------ #
    @classmethod
    def from_eval_curve(
        cls,
        curve_path: Path = EVAL_CURVE_V2,
        *,
        method_key: str = "v2_pace",
        z_mult: float = 1.0,
        nominal_coverages: Sequence[float] = DEFAULT_NOMINAL_COVERAGES,
        default_nominal: float = 0.80,
    ) -> "IntervalCalibrator":
        """Build from ``eval_curve_v2.json``. Falls back to a coarse default
        curve if the file is absent (so the projector still runs offline).

        The shipped eval curve stores only aggregate MAE per (stat, bucket) — no
        raw residual sample — so the empirical ``z_table`` is filled with the
        closed-form Laplace z for each nominal coverage. This replaces the old
        flat z_mult=1.0 (~58% true coverage) with a distribution-based z that
        targets the STATED nominal. To get TRUE empirical z's, build via
        ``from_residual_dump`` with a held-out residual sample.
        """
        knots: Dict[str, List[Tuple[float, float]]] = {s: [] for s in PLAYER_STATS}
        source = "fallback"
        try:
            data = json.loads(Path(curve_path).read_text(encoding="utf-8"))
            grid_labels = data["meta"]["grid_labels"]  # {"360": "06min(midQ1)", ...}
            curve = data["player_curve"]
            # invert label -> grid_sec
            label_to_sec = {lbl: int(sec) for sec, lbl in grid_labels.items()}
            for label, per_stat in curve.items():
                grid_sec = label_to_sec.get(label)
                if grid_sec is None:
                    continue
                rem_min = _grid_sec_to_remaining_min(grid_sec)
                for stat in PLAYER_STATS:
                    cell = per_stat.get(stat)
                    if not cell:
                        continue
                    mae = cell.get(method_key)
                    if mae is None:
                        mae = cell.get("v2_core")
                    if mae is None:
                        continue
                    knots[stat].append((rem_min, float(mae)))
            source = str(curve_path)
        except FileNotFoundError:
            pass
        except Exception:
            pass

        # finalize per-stat knot lists: dedupe, sort, pin (0,0), ensure non-empty
        for stat in PLAYER_STATS:
            ks = knots.get(stat) or []
            if not ks:
                ks = list(_FALLBACK_MAE_BY_REM.get(stat, _FALLBACK_MAE_BY_REM["pts"]))
            # sort ascending by remaining-min
            ks = sorted({(round(r, 4), m) for r, m in ks})
            # pin a zero-band at the buzzer so the interval collapses to point est
            if ks[0][0] > 0.0:
                ks = [(0.0, 0.0)] + ks
            knots[stat] = ks

        # No raw residuals in eval_curve_v2.json -> Laplace closed-form z_table.
        z_table: Dict[float, Dict[str, Dict[float, float]]] = {}
        for nom in nominal_coverages:
            z = _laplace_z_for_coverage(nom)
            z_table[float(nom)] = {
                stat: {float(r): z for (r, _m) in knots[stat]}
                for stat in PLAYER_STATS
            }
        return cls(
            knots=knots, z_mult=z_mult, method_key=method_key, source=source,
            z_table=z_table, default_nominal=float(default_nominal),
            z_source="laplace_closed_form(no_residual_sample)",
        )

    # ------------------------------------------------------------------ #
    @classmethod
    def from_residual_dump(
        cls,
        residual_path: Path,
        *,
        curve_path: Path = EVAL_CURVE_V2,
        method_key: str = "v2_pace",
        nominal_coverages: Sequence[float] = DEFAULT_NOMINAL_COVERAGES,
        default_nominal: float = 0.80,
    ) -> "IntervalCalibrator":
        """Build the MAE knots from the eval curve AND fit a TRUE empirical
        ``z_table`` from a held-out residual sample on disk.

        ``residual_path`` is a JSON file shaped as::

            {"<bucket_label_or_remmin>": {"<stat>": [resid, resid, ...]}}

        where each ``resid = y_true - projected_final`` on held-out games. The
        bucket key may be an eval grid label ("36min(endQ3)") or a remaining-min
        number. We compute, per (stat, bucket, nominal), the z that yields ~nominal
        empirical coverage of those residuals over the bucket's MAE.
        """
        base = cls.from_eval_curve(
            curve_path, method_key=method_key,
            nominal_coverages=nominal_coverages, default_nominal=default_nominal,
        )
        try:
            residuals = json.loads(Path(residual_path).read_text(encoding="utf-8"))
        except Exception:
            return base  # keep Laplace fallback if the dump is unreadable
        return base.fit_z_from_residuals(
            residuals, nominal_coverages=nominal_coverages,
            source=str(residual_path),
        )

    # ------------------------------------------------------------------ #
    def fit_z_from_residuals(
        self,
        residuals: Dict[str, Dict[str, Sequence[float]]],
        *,
        nominal_coverages: Sequence[float] = DEFAULT_NOMINAL_COVERAGES,
        min_n: int = 30,
        source: str = "in_memory_residuals",
    ) -> "IntervalCalibrator":
        """Return a copy with ``z_table`` fit empirically from a residual sample.

        For each (stat, bucket) with >= ``min_n`` residuals we set
        ``z = quantile(|resid|, nominal) / MAE_bucket`` — the smallest band-scale
        in MAE units whose symmetric interval covers ``nominal`` of the residuals.
        Buckets with too few samples keep the Laplace fallback z. The MAE used is
        the bucket's eval-curve MAE (the same one ``band`` multiplies), so achieved
        coverage at that bucket is exact by construction on the fit sample.
        """
        # map any bucket key -> remaining-min knot
        def _key_to_rem(k: str) -> Optional[float]:
            ks = str(k)
            # eval grid label like "36min(endQ3)" or "36min..."
            m = ks.split("min")[0]
            try:
                grid_min = float(m)
                # label minutes are ELAPSED; convert to remaining
                return max(0.0, (REG_GAME_SEC / 60.0) - grid_min)
            except ValueError:
                pass
            try:
                return max(0.0, float(ks))  # already remaining-min
            except ValueError:
                return None

        new_table = {float(n): {s: dict(self._z_for(n).get(s, {}))
                                for s in PLAYER_STATS}
                     for n in nominal_coverages}

        for bucket_key, per_stat in (residuals or {}).items():
            rem = _key_to_rem(bucket_key)
            if rem is None:
                continue
            knot_rem = self._nearest_knot_rem("pts", rem)
            for stat, vals in (per_stat or {}).items():
                if stat not in PLAYER_STATS:
                    continue
                arr = np.asarray([float(v) for v in vals], dtype=float)
                arr = arr[np.isfinite(arr)]
                if arr.size < min_n:
                    continue
                k_rem = self._nearest_knot_rem(stat, rem)
                mae = self._mae_at(stat, k_rem)
                if mae <= 0:
                    continue
                absr = np.abs(arr)
                for nom in nominal_coverages:
                    q = float(np.quantile(absr, float(nom)))
                    new_table.setdefault(float(nom), {}).setdefault(stat, {})[
                        float(k_rem)
                    ] = q / mae

        return IntervalCalibrator(
            knots=self.knots, z_mult=self.z_mult, method_key=self.method_key,
            source=self.source, z_table=new_table,
            default_nominal=self.default_nominal,
            z_source="empirical_residual_quantile(%s)" % source,
        )

    # ------------------------------------------------------------------ #
    def _z_for(self, nominal: float) -> Dict[str, Dict[float, float]]:
        return self.z_table.get(float(nominal), {})

    def _nearest_knot_rem(self, stat: str, remaining_min: float) -> float:
        ks = self.knots.get(stat) or []
        if not ks:
            return 0.0
        rem = max(0.0, float(remaining_min))
        return min((r for r, _ in ks), key=lambda r: abs(r - rem))

    def _mae_at(self, stat: str, remaining_min: float) -> float:
        """Interpolated raw MAE (NO z) at ``remaining_min`` — the band base."""
        ks = self.knots.get(stat)
        if not ks:
            return 0.0
        rem = max(0.0, float(remaining_min))
        if rem >= ks[-1][0]:
            return float(ks[-1][1])
        for i in range(1, len(ks)):
            r0, m0 = ks[i - 1]
            r1, m1 = ks[i]
            if rem <= r1:
                if r1 == r0:
                    return float(m1)
                w = (rem - r0) / (r1 - r0)
                return float(m0 + w * (m1 - m0))
        return float(ks[-1][1])

    def z_at(self, stat: str, remaining_min: float,
             *, nominal: Optional[float] = None) -> float:
        """The z multiplier in effect for ``stat`` at ``remaining_min``.

        Snaps to the nearest calibrated knot for the requested nominal coverage.
        Falls back to the legacy scalar ``z_mult`` when no table entry exists.
        """
        nom = self.default_nominal if nominal is None else float(nominal)
        table = self._z_for(nom)
        per_stat = table.get(stat)
        if per_stat:
            knot_rem = self._nearest_knot_rem(stat, remaining_min)
            z = per_stat.get(float(knot_rem))
            if z is not None:
                return float(z)
            # nominal table exists but this knot missing: use Laplace for nominal
            return _laplace_z_for_coverage(nom)
        return float(self.z_mult)

    # ------------------------------------------------------------------ #
    def band(self, stat: str, remaining_min: float,
             *, nominal: Optional[float] = None) -> float:
        """Interval HALF-WIDTH for ``stat`` at ``remaining_min`` game-minutes left.

        ``z(stat, rem, nominal) * MAE_resid(stat, rem)`` where MAE is the held-out
        residual MAE (linear-interpolated in remaining-minutes) and z is the
        EMPIRICAL (or Laplace-fallback) multiplier that makes the band's stated
        ``nominal`` coverage match reality. Monotone decay to ~0 at the buzzer
        (rem=0) because of the pinned (0,0) knot.

        Backward-compat: with the default constructor (empty ``z_table``) this
        reduces to ``z_mult * MAE`` exactly as before.
        """
        mae = self._mae_at(stat, remaining_min)
        if mae <= 0.0 and not self.knots.get(stat):
            return 0.0
        z = self.z_at(stat, remaining_min, nominal=nominal)
        return float(z * mae)

    # ------------------------------------------------------------------ #
    def calibrate_coverage(
        self,
        residuals: Dict[str, Dict[str, Sequence[float]]],
        *,
        nominal_coverages: Sequence[float] = DEFAULT_NOMINAL_COVERAGES,
    ) -> Dict:
        """REPORT achieved empirical coverage per (stat, bucket, nominal).

        Applies THIS calibrator's bands to a held-out residual sample and returns,
        per (nominal, stat, bucket): n, the z used, the band half-width, and the
        fraction of |resid| <= band (the achieved coverage). Honest: if a stat
        cannot reach nominal (residual tail heavier than MAE*z), the achieved
        number will be below nominal and is reported as-is.

        ``residuals`` is shaped ``{bucket_key: {stat: [resid, ...]}}`` exactly as
        ``fit_z_from_residuals`` expects (bucket key = grid label or remaining-min).
        """
        def _key_to_rem(k: str) -> Optional[float]:
            ks = str(k)
            m = ks.split("min")[0]
            try:
                return max(0.0, (REG_GAME_SEC / 60.0) - float(m))
            except ValueError:
                pass
            try:
                return max(0.0, float(ks))
            except ValueError:
                return None

        report: Dict = {"z_source": self.z_source, "by_nominal": {}}
        for nom in nominal_coverages:
            nom = float(nom)
            agg: Dict[str, Dict] = {}
            for bucket_key, per_stat in (residuals or {}).items():
                rem = _key_to_rem(bucket_key)
                if rem is None:
                    continue
                for stat, vals in (per_stat or {}).items():
                    if stat not in PLAYER_STATS:
                        continue
                    arr = np.asarray([float(v) for v in vals], dtype=float)
                    arr = arr[np.isfinite(arr)]
                    if arr.size == 0:
                        continue
                    band = self.band(stat, rem, nominal=nom)
                    covered = float(np.mean(np.abs(arr) <= band))
                    agg.setdefault(stat, {})[str(bucket_key)] = {
                        "n": int(arr.size),
                        "z": round(self.z_at(stat, rem, nominal=nom), 4),
                        "mae": round(self._mae_at(stat, rem), 4),
                        "band": round(band, 4),
                        "achieved_coverage": round(covered, 4),
                        "nominal": nom,
                        "hits_nominal": bool(covered + 1e-9 >= nom),
                    }
            # per-stat pooled coverage across buckets (sample-weighted)
            pooled: Dict[str, Dict] = {}
            for stat, buckets in agg.items():
                tot_n = sum(b["n"] for b in buckets.values())
                if tot_n == 0:
                    continue
                w_cov = sum(b["achieved_coverage"] * b["n"]
                            for b in buckets.values()) / tot_n
                pooled[stat] = {
                    "n": tot_n,
                    "pooled_achieved_coverage": round(w_cov, 4),
                    "nominal": nom,
                    "hits_nominal": bool(w_cov + 1e-9 >= nom),
                }
            report["by_nominal"][nom] = {"by_bucket": agg, "pooled_by_stat": pooled}
        return report


# Coarse fallback residual-MAE-by-remaining-min if eval_curve_v2.json is missing.
# (Derived from the shipped v2_pace curve magnitudes; only used when the real
# eval file cannot be read so the module never hard-fails offline.)
_FALLBACK_MAE_BY_REM: Dict[str, List[Tuple[float, float]]] = {
    "pts": [(42.0, 5.27), (36.0, 4.44), (30.0, 3.93), (24.0, 3.43),
            (18.0, 3.06), (12.0, 2.47), (6.0, 1.68)],
    "reb": [(42.0, 2.00), (36.0, 1.75), (30.0, 1.58), (24.0, 1.39),
            (18.0, 1.22), (12.0, 1.01), (6.0, 0.68)],
    "ast": [(42.0, 1.55), (36.0, 1.27), (30.0, 1.13), (24.0, 1.02),
            (18.0, 0.89), (12.0, 0.72), (6.0, 0.49)],
    "fg3m": [(42.0, 0.99), (36.0, 0.84), (30.0, 0.74), (24.0, 0.66),
             (18.0, 0.57), (12.0, 0.44), (6.0, 0.27)],
    "stl": [(42.0, 0.74), (36.0, 0.65), (30.0, 0.57), (24.0, 0.50),
            (18.0, 0.41), (12.0, 0.29), (6.0, 0.19)],
    "blk": [(42.0, 0.59), (36.0, 0.48), (30.0, 0.42), (24.0, 0.36),
            (18.0, 0.30), (12.0, 0.22), (6.0, 0.15)],
    "tov": [(42.0, 0.99), (36.0, 0.85), (30.0, 0.75), (24.0, 0.66),
            (18.0, 0.57), (12.0, 0.44), (6.0, 0.28)],
}


# --------------------------------------------------------------------------- #
# Win-prob (ACCEPTED baseline) + team score (naive pace; research-only)
# --------------------------------------------------------------------------- #
def home_win_prob(margin: float, remaining_min: float, *, k: float = 0.40) -> float:
    """Accepted time-and-score logistic: sigmoid(k*margin/sqrt(rem_min)).

    Identical to ``scripts.ingame.eval_second_by_second.baseline_winprob`` — the
    baseline that beat the learned win-prob head at every grid point. We hold
    this; we do NOT use a learned win-prob head (rejected).
    """
    rem = max(1.0, float(remaining_min))
    z = k * float(margin) / math.sqrt(rem)
    return float(1.0 / (1.0 + math.exp(-z)))


def naive_team_finals(home_score: float, away_score: float,
                      played_share: float) -> Tuple[float, float]:
    """RESEARCH-ONLY linear-pace team-final extrapolation.

    The learned team-score head beats only a strawman pace baseline (not the
    market) — flagged research-only in the verdict. We expose THIS pace estimate
    (not a learned head) and label it as such. At ``played_share<=0`` returns
    current scores.
    """
    if played_share <= 0.0:
        return float(home_score), float(away_score)
    return float(home_score) / played_share, float(away_score) / played_share


# --------------------------------------------------------------------------- #
# The per-second projector
# --------------------------------------------------------------------------- #
@dataclass
class PlayerProjection:
    """One player's per-second projection at a given tick."""

    player_id: object
    stat: str
    current: float           # accumulated so far (floor)
    projected_final: float   # v2 point estimate (event-anchored, floored)
    lo: float                # projected_final - band (clamped >= current)
    hi: float                # projected_final + band
    band: float              # interval half-width (residual-MAE * z)


@dataclass
class GameProjection:
    """A full per-second snapshot: clock + team + win-prob + player lines."""

    game_time_sec: float          # elapsed game-seconds at this tick
    game_remaining_min: float
    home_score: float
    away_score: float
    home_final_proj: float        # naive-pace (research-only)
    away_final_proj: float        # naive-pace (research-only)
    home_win_prob: float          # accepted logistic baseline
    players: List[PlayerProjection] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "game_time_sec": self.game_time_sec,
            "game_remaining_min": self.game_remaining_min,
            "team": {
                "home_score": self.home_score,
                "away_score": self.away_score,
                "home_final_proj_naive_pace": self.home_final_proj,
                "away_final_proj_naive_pace": self.away_final_proj,
                "home_win_prob": self.home_win_prob,
            },
            "players": [
                {
                    "player_id": p.player_id,
                    "stat": p.stat,
                    "current": p.current,
                    "projected_final": p.projected_final,
                    "lo": p.lo,
                    "hi": p.hi,
                    "band": p.band,
                }
                for p in self.players
            ],
            # honesty stamp travels with every payload
            "_resolution": "per-event accuracy; clock+interval move per second; "
                           "win_prob=accepted logistic; team=naive-pace (research)",
        }


@dataclass
class PerSecondProjector:
    """Continuous per-second projection stream over the validated v2 head.

    Usage:
        proj = PerSecondProjector.load()                 # v2 heads + calibrator
        # On each NEW event, push the leak-free state rows for that moment:
        proj.update_event(game_state_row, player_state_rows)
        # Then read a projection at ANY wall-clock second between events:
        snap = proj.project_at(game_time_sec)            # interval decays; point holds

    The point estimate (v2) is recomputed ONLY in ``update_event``. ``project_at``
    NEVER changes the point estimate — it only advances the clock and shrinks the
    interval band. This encodes the honesty rule in the API itself.
    """

    v2: UnifiedPlayerLineProjector
    calib: IntervalCalibrator
    nominal_coverage: float = 0.80
    # last event state (set by update_event)
    _game_row: Dict = field(default_factory=dict)
    _player_rows: List[Dict] = field(default_factory=list)
    # cached v2 point estimates per (player_id) -> {stat: projected_final}
    _point: Dict[object, Dict[str, float]] = field(default_factory=dict)
    _current: Dict[object, Dict[str, float]] = field(default_factory=dict)
    _last_event_game_sec: float = 0.0

    # ------------------------------------------------------------------ #
    @classmethod
    def load(
        cls,
        *,
        model_dir: Path = SBS_V2_DIR,
        curve_path: Path = EVAL_CURVE_V2,
        z_mult: float = 1.0,
        residual_path: Optional[Path] = None,
        nominal_coverage: float = 0.80,
        v2: Optional[UnifiedPlayerLineProjector] = None,
    ) -> "PerSecondProjector":
        """Load the persisted v2 heads + build the held-out interval calibrator.

        The calibrator now targets an EMPIRICAL nominal coverage (default 80%):
        the band is ``z(stat, t, nominal) * residual_MAE(stat, t)`` where z is the
        empirical multiplier (from ``residual_path`` if supplied) or the closed-
        form Laplace z for the nominal (when only aggregate MAE is on disk). This
        replaces the old flat z=1.0 (~58% true coverage).
        """
        proj = v2 if v2 is not None else UnifiedPlayerLineProjector.load(model_dir)
        if residual_path is not None and Path(residual_path).exists():
            calib = IntervalCalibrator.from_residual_dump(
                residual_path, curve_path=curve_path,
                default_nominal=nominal_coverage,
            )
        else:
            calib = IntervalCalibrator.from_eval_curve(
                curve_path, z_mult=z_mult, default_nominal=nominal_coverage,
            )
        return cls(v2=proj, calib=calib, nominal_coverage=float(nominal_coverage))

    # ------------------------------------------------------------------ #
    def update_event(self, game_row: Dict, player_rows: Sequence[Dict]) -> None:
        """Ingest ONE new event's leak-free state. Recompute v2 point estimates.

        This is the ONLY place the point estimate changes — accuracy updates at
        EVENTS. ``game_row`` is a featurizer game-state row; ``player_rows`` are
        per-player state rows (must carry ``player_id`` + the v2 feature columns,
        e.g. ``p_<stat>_so_far``). Call this on each new PBP event (live: from
        ``featurize_live_snapshot`` + per-player rows; offline: from
        ``state_featurizer.featurize_game``).
        """
        self._game_row = dict(game_row)
        self._player_rows = [dict(r) for r in player_rows]
        self._last_event_game_sec = float(game_row.get("game_elapsed_sec", 0.0) or 0.0)
        self._point = {}
        self._current = {}
        for prow in self._player_rows:
            pid = prow.get("player_id")
            if pid is None:
                continue
            self._point[pid] = self.v2.project(prow)
            self._current[pid] = {
                s: float(prow.get(_PLAYER_CURRENT_COL[s], 0.0) or 0.0)
                for s in PLAYER_STATS
            }

    # ------------------------------------------------------------------ #
    def project_at(self, game_time_sec: float,
                   *, stats: Optional[Sequence[str]] = None) -> GameProjection:
        """Return a projection at an arbitrary wall-clock second.

        Between events the POINT estimate is the last event's v2 value (held
        constant — no fake accuracy). Only the clock advances and the interval
        band shrinks (calibrated decay vs remaining game-time). ``game_time_sec``
        is elapsed game-seconds; passing the last event's time reproduces the
        event-time projection (the interval is monotone in elapsed time, so a
        later ``game_time_sec`` yields a band <= the band at the event).
        """
        stats = list(stats) if stats is not None else list(PLAYER_STATS)
        # clamp the displayed clock to >= the last event (clock only moves forward)
        gsec = max(self._last_event_game_sec, float(game_time_sec))
        remaining_min = max(0.0, (REG_GAME_SEC - gsec) / 60.0)

        home_score = float(self._game_row.get("home_score", 0.0) or 0.0)
        away_score = float(self._game_row.get("away_score", 0.0) or 0.0)
        played_share = max(0.0, min(1.0, gsec / REG_GAME_SEC)) if REG_GAME_SEC else 0.0
        h_fin, a_fin = naive_team_finals(home_score, away_score, played_share)
        wp = home_win_prob(home_score - away_score, remaining_min)

        players: List[PlayerProjection] = []
        for pid, point in self._point.items():
            cur = self._current.get(pid, {})
            for s in stats:
                if s not in point:
                    continue
                pf = float(point[s])
                c = float(cur.get(s, 0.0))
                band = self.calib.band(s, remaining_min,
                                       nominal=self.nominal_coverage)
                lo = max(c, pf - band)   # never below what already happened
                hi = pf + band
                players.append(PlayerProjection(
                    player_id=pid, stat=s, current=c,
                    projected_final=pf, lo=lo, hi=hi, band=band,
                ))

        return GameProjection(
            game_time_sec=gsec,
            game_remaining_min=remaining_min,
            home_score=home_score,
            away_score=away_score,
            home_final_proj=h_fin,
            away_final_proj=a_fin,
            home_win_prob=wp,
            players=players,
        )

    # ------------------------------------------------------------------ #
    def stream_between_events(
        self,
        from_game_sec: float,
        to_game_sec: float,
        *,
        step_sec: float = 1.0,
        stats: Optional[Sequence[str]] = None,
    ) -> List[GameProjection]:
        """Emit the per-second stream from one event time to the next.

        Holds the current event's v2 point estimate at every second in
        ``[from_game_sec, to_game_sec)`` and decays the interval each step. This
        is the literal per-second product surface: call ``update_event`` when a
        new event arrives, then ``stream_between_events`` to fill the seconds
        until the next event. The point estimate is identical across the stream
        (accuracy is event-anchored); only clock + band vary.
        """
        out: List[GameProjection] = []
        t = float(from_game_sec)
        end = float(to_game_sec)
        if step_sec <= 0:
            step_sec = 1.0
        while t < end:
            out.append(self.project_at(t, stats=stats))
            t += step_sec
        return out


# --------------------------------------------------------------------------- #
# Flag-gated live entrypoints (no-op when CV_INGAME_SBS is OFF)
# --------------------------------------------------------------------------- #
_SINGLETON: Optional[PerSecondProjector] = None


def stream_player_intervals(
    game_row: Dict,
    player_rows: Sequence[Dict],
    game_time_sec: float,
    *,
    stats: Optional[Sequence[str]] = None,
    projector: Optional[PerSecondProjector] = None,
) -> Optional[Dict]:
    """Flag-gated one-shot: ingest an event's state + return the projection dict.

    Returns ``None`` when ``CV_INGAME_SBS`` is OFF (so wiring this into a live
    path cannot change a served value unless the flag is set). When enabled,
    loads the v2 heads once (process-cached) unless ``projector`` is supplied,
    ingests the event, and returns ``GameProjection.to_dict()`` at
    ``game_time_sec``.
    """
    if not is_enabled():
        return None
    global _SINGLETON
    proj = projector
    if proj is None:
        if _SINGLETON is None:
            _SINGLETON = PerSecondProjector.load()
        proj = _SINGLETON
    proj.update_event(game_row, player_rows)
    return proj.project_at(game_time_sec, stats=stats).to_dict()


__all__ = [
    "INGAME_SBS_FLAG",
    "is_enabled",
    "IntervalCalibrator",
    "DEFAULT_NOMINAL_COVERAGES",
    "home_win_prob",
    "naive_team_finals",
    "PlayerProjection",
    "GameProjection",
    "PerSecondProjector",
    "stream_player_intervals",
    "EVAL_CURVE_V2",
]
