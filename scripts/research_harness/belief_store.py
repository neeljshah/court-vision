"""belief_store.py — Family-level Beta-Binomial ship-rate priors.

Prior Beta(1,9), mean~10% (markets efficient; most families REJECT).
SHIP→alpha+=w; REJECT→beta+=w; DEFER→both+=0.1*w; w=exp(-ln2*age/hl).
Sparse families pool to sport aggregate then global.  No edge is claimed.
CLI: python -m scripts.research_harness.belief_store [--ledger PATH] [--save]
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STORE = ROOT / "data" / "research" / "beliefs.json"

_PRIOR_ALPHA: float = 1.0
_PRIOR_BETA: float = 9.0
_CI_MASS: float = 0.95
_MIN_OBS_THRESHOLD: float = 3.0
_DEFAULT_HALF_LIFE: float = 180.0
_VERDICT_WEIGHT: Dict[str, Tuple[float, float]] = {
    "SHIP": (1.0, 0.0), "REJECT": (0.0, 1.0), "DEFER": (0.1, 0.1),
    "VARIANCE_ONLY": (0.5, 0.0),  # partial-SHIP: alpha+=0.5*w, beta unchanged
}
FamilyKey = Tuple[str, str]


def _beta_mean(a: float, b: float) -> float: return a / (a + b)
def _log_beta(a: float, b: float) -> float:
    return math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)


def _beta_cdf(x: float, a: float, b: float) -> float:
    """Regularised incomplete beta I_x(a,b) via Lentz continued fraction."""
    if x <= 0.0: return 0.0
    if x >= 1.0: return 1.0
    flip = x > (a + 1.0) / (a + b + 2.0)
    xx, aa, bb = (1.0 - x, b, a) if flip else (x, a, b)
    front = math.exp(aa * math.log(xx) + bb * math.log(1.0 - xx) - _log_beta(a, b))
    T, C = 1e-30, 1.0
    D = 1.0 - (aa + bb) * xx / (aa + 1.0)
    D = T if abs(D) < T else D
    D, cf, delta = 1.0 / D, D, 1.0
    for m in range(1, 300):
        for even in (True, False):
            num = (m * (bb - m) * xx / ((aa+2*m-1) * (aa+2*m)) if even
                   else -(aa+m) * (aa+bb+m) * xx / ((aa+2*m) * (aa+2*m+1)))
            D = 1.0 + num * D; C = 1.0 + num / C
            D = T if abs(D) < T else D; C = T if abs(C) < T else C
            D = 1.0 / D; delta = D * C; cf *= delta
        if abs(delta - 1.0) < 3e-10: break
    val = front * cf / aa
    return max(0.0, 1.0 - val) if flip else min(1.0, val)

def _beta_ppf(p: float, a: float, b: float) -> float:
    """Beta PPF: 60-step bisection then 5-step Newton polish."""
    p = max(1e-12, min(1.0 - 1e-12, p))
    lo, hi = 1e-12, 1.0 - 1e-12
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if _beta_cdf(mid, a, b) < p: lo = mid
        else: hi = mid
        if hi - lo < 1e-13: break
    x, lb = (lo + hi) / 2.0, _log_beta(a, b)
    for _ in range(5):
        lp = (a-1)*math.log(x) + (b-1)*math.log(1.0-x) - lb
        pdf = math.exp(lp) if lp > -700 else 0.0
        if pdf < 1e-30: break
        step = (_beta_cdf(x, a, b) - p) / pdf
        x = max(1e-12, min(1.0-1e-12, x - step))
        if abs(step) < 1e-13: break
    return x

def _beta_ci(a: float, b: float, mass: float = _CI_MASS) -> Tuple[float, float]:
    """Equal-tailed credible interval for Beta(a, b)."""
    if a + b < 2.0: return (0.0, 1.0)
    t = (1.0 - mass) / 2.0
    return (_beta_ppf(t, a, b), _beta_ppf(1.0 - t, a, b))


@dataclass
class FamilyBelief:
    """Posterior state for one (sport, family) pair."""
    sport: str
    family: str
    alpha: float = field(default=_PRIOR_ALPHA)
    beta: float = field(default=_PRIOR_BETA)
    effective_obs: float = field(default=0.0)
    last_updated: str = field(default="")

    @property
    def posterior_mean(self) -> float:
        return _beta_mean(self.alpha, self.beta)

    def credible_interval(self, mass: float = _CI_MASS) -> Tuple[float, float]:
        """Equal-tailed credible interval."""
        return _beta_ci(self.alpha, self.beta, mass)

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> "FamilyBelief":
        return cls(**{k: d[k] for k in
                      ("sport", "family", "alpha", "beta", "effective_obs", "last_updated")})


class BeliefStore:
    """Beta-Binomial ship-rate memory (time-decay + hierarchical pooling).

    half_life_days: decay hl (inf=none). prior_alpha/beta: Beta shape (default 1/9).
    min_obs_threshold: below this effective-obs pooling kicks in. reference_date: "today".
    """

    def __init__(self, half_life_days: float = _DEFAULT_HALF_LIFE,
                 prior_alpha: float = _PRIOR_ALPHA, prior_beta: float = _PRIOR_BETA,
                 min_obs_threshold: float = _MIN_OBS_THRESHOLD,
                 reference_date: Optional[str] = None) -> None:
        self._half_life = half_life_days; self._a0 = prior_alpha; self._b0 = prior_beta
        self._min_obs = min_obs_threshold; self._ref_date = reference_date
        self._beliefs: Dict[FamilyKey, FamilyBelief] = {}

    def _today(self) -> datetime:
        if self._ref_date:
            return datetime.fromisoformat(self._ref_date).replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc)

    def _age_weight(self, dated: str) -> float:
        if self._half_life == math.inf or not dated:
            return 1.0
        try:
            dt = datetime.fromisoformat(dated).replace(tzinfo=timezone.utc)
        except ValueError:
            return 1.0
        age = max(0.0, (self._today() - dt).total_seconds() / 86400.0)
        return math.exp(-math.log(2.0) * age / self._half_life)

    def _fresh(self, sport: str, family: str) -> FamilyBelief:
        return FamilyBelief(sport=sport, family=family, alpha=self._a0, beta=self._b0)

    def update_from_finding(self, sport: str, family: str,
                            verdict: str, dated: str = "") -> None:
        """Incorporate one research finding verdict into (sport, family) posterior."""
        key: FamilyKey = (sport, family)
        if key not in self._beliefs:
            self._beliefs[key] = self._fresh(sport, family)
        b = self._beliefs[key]
        w = self._age_weight(dated)
        da, db = _VERDICT_WEIGHT.get(verdict, (0.0, 0.0))
        b.alpha += da * w
        b.beta += db * w
        b.effective_obs += w
        b.last_updated = dated or self._today().strftime("%Y-%m-%d")

    def update_from_findings(self, findings: List[Dict]) -> None:
        """Bulk-update from list of dicts with keys sport/family/verdict/dated."""
        for f in findings:
            self.update_from_finding(f["sport"], f["family"],
                                     f["verdict"], f.get("dated", ""))

    def update_from_ledger(self, ledger: object) -> None:  # type: ignore[type-arg]
        """Update from a research_ledger.Ledger instance."""
        for f in ledger.all_findings():  # type: ignore[attr-defined]
            self.update_from_finding(f.sport, f.family, f.verdict, f.dated)

    def get_belief(self, sport: str, family: str) -> FamilyBelief:
        """Return posterior for (sport, family); returns prior if unseen."""
        return self._beliefs.get((sport, family), self._fresh(sport, family))

    def _sport_agg(self, sport: str) -> Tuple[float, float]:
        a, b = self._a0, self._b0
        for (s, _), bel in self._beliefs.items():
            if s == sport:
                a += bel.alpha - self._a0
                b += bel.beta - self._b0
        return a, b

    def _global_agg(self) -> Tuple[float, float]:
        a, b = self._a0, self._b0
        for bel in self._beliefs.values():
            a += bel.alpha - self._a0
            b += bel.beta - self._b0
        return a, b

    def _sport_obs(self, sport: str) -> float:
        return sum(bel.effective_obs for (s, _), bel in self._beliefs.items()
                   if s == sport)

    def posterior_mean(self, sport: str, family: str, pool: bool = True) -> float:
        """Posterior mean P(ship), with sport/global pooling for sparse families."""
        bel = self.get_belief(sport, family)
        if not pool or bel.effective_obs >= self._min_obs:
            return bel.posterior_mean
        if self._sport_obs(sport) >= self._min_obs:
            return _beta_mean(*self._sport_agg(sport))
        return _beta_mean(*self._global_agg())

    def credible_interval(self, sport: str, family: str,
                          mass: float = _CI_MASS, pool: bool = True) -> Tuple[float, float]:
        """Equal-tailed credible interval with pooling fallback."""
        bel = self.get_belief(sport, family)
        if not pool or bel.effective_obs >= self._min_obs:
            return bel.credible_interval(mass)
        if self._sport_obs(sport) >= self._min_obs:
            return _beta_ci(*self._sport_agg(sport), mass)
        return _beta_ci(*self._global_agg(), mass)

    def all_beliefs(self) -> List[FamilyBelief]:
        return list(self._beliefs.values())

    def calibration_summary(self) -> Dict:
        """Reliability surface {observed_ship_rate, mean_posterior, n, is_overconfident}.
        No edge claimed.  alpha>prior+0.3 → SHIP-like; overconfident if gap>0.05."""
        bb = list(self._beliefs.values()); n = len(bb)
        if n == 0:
            pm = _beta_mean(self._a0, self._b0)
            return {"observed_ship_rate": 0.0, "mean_posterior": pm, "n": 0, "is_overconfident": pm > 0.0}
        mp = sum(b.posterior_mean for b in bb) / n
        osr = sum(1 for b in bb if b.alpha > self._a0 + 0.3) / n
        return {"observed_ship_rate": osr, "mean_posterior": mp, "n": n, "is_overconfident": (mp - osr) > 0.05}

    def to_dict(self) -> Dict:
        return {
            "half_life_days": self._half_life, "prior_alpha": self._a0,
            "prior_beta": self._b0, "min_obs_threshold": self._min_obs,
            "beliefs": [b.to_dict() for b in self._beliefs.values()],
        }

    def save(self, path: Optional[Path] = None) -> Path:
        """Atomically write beliefs to JSON (write-then-rename)."""
        out = Path(path) if path else DEFAULT_STORE
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")
        tmp.replace(out)
        return out

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "BeliefStore":
        """Load from JSON; returns a fresh store if the file is absent."""
        p = Path(path) if path else DEFAULT_STORE
        if not p.exists():
            return cls()
        d = json.loads(p.read_text(encoding="utf-8"))
        store = cls(half_life_days=d.get("half_life_days", _DEFAULT_HALF_LIFE),
                    prior_alpha=d.get("prior_alpha", _PRIOR_ALPHA),
                    prior_beta=d.get("prior_beta", _PRIOR_BETA),
                    min_obs_threshold=d.get("min_obs_threshold", _MIN_OBS_THRESHOLD))
        for bd in d.get("beliefs", []):
            store._beliefs[(bd["sport"], bd["family"])] = FamilyBelief.from_dict(bd)
        return store

    def render_table(self) -> str:
        """Human-readable table of all family posteriors.  No edge is claimed."""
        if not self._beliefs:
            return "No beliefs recorded yet."
        hdr = f"{'sport':<12}{'family':<35}{'P(ship)':<10}{'95% CI':<20}{'eff_obs':<10}updated"
        sep = "-" * 100
        lines = [hdr, sep]
        for (sport, family), bel in sorted(self._beliefs.items()):
            lo, hi = bel.credible_interval()
            lines.append(f"{sport:<12}{family:<35}{bel.posterior_mean:<10.3f}"
                         f"[{lo:.3f}, {hi:.3f}]{'':4}{bel.effective_obs:<10.1f}{bel.last_updated}")
        lines += [sep, "Note: P(ship) = historical ship-rate prior.  No edge is claimed."]
        return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> None:
    p = argparse.ArgumentParser(prog="belief_store",
                                description="Beta-Binomial ship-rate priors.  No edge is claimed.")
    p.add_argument("--ledger", metavar="PATH")
    p.add_argument("--store", metavar="PATH")
    p.add_argument("--save", action="store_true")
    p.add_argument("--half-life", type=float, default=_DEFAULT_HALF_LIFE, metavar="DAYS")
    args = p.parse_args(argv)
    from scripts.research_harness.research_ledger import Ledger
    ledger = Ledger(path=Path(args.ledger) if args.ledger else None)
    store = BeliefStore(half_life_days=args.half_life)
    findings = ledger.all_findings()
    if not findings:
        print("Ledger is empty or absent — showing prior-only beliefs.")
    else:
        store.update_from_ledger(ledger)
        print(f"Loaded {len(findings)} findings from {ledger.path}")
    print()
    print(store.render_table())
    if args.save:
        out = store.save(Path(args.store) if args.store else None)
        print(f"\nBeliefs saved to: {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
