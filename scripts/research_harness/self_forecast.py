"""self_forecast.py — Pre-registered researcher self-forecasts + Brier grading.

The single highest-leverage honesty mechanism: researcher logs P(ship) *before*
running each experiment, then is graded on those predictions.

On an efficient market P(ship)~0 and most families REJECT.  A forecaster
predicting low P(ship) is WELL-CALIBRATED — stated honestly here.
No edge is claimed.

Store: data/research/forecasts.jsonl (append-only; dedup sport+family+hypothesis)
CLI:   python -m scripts.research_harness.self_forecast [--ledger PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STORE = ROOT / "data" / "research" / "forecasts.jsonl"


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

@dataclass
class SelfForecast:
    """Pre-registered forecast: p_ship = prior P(SHIP verdict), dated at registration."""
    sport: str
    family: str
    hypothesis: str
    p_ship: float
    dated: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%d"))

    def __post_init__(self) -> None:
        if not 0.0 <= self.p_ship <= 1.0:
            raise ValueError(f"p_ship must be in [0, 1]; got {self.p_ship}")
        if not self.hypothesis.strip():
            raise ValueError("hypothesis must not be empty")

    @property
    def key(self) -> Tuple[str, str, str]:
        return (self.sport, self.family, self.hypothesis)

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Dict) -> "SelfForecast":
        return cls(sport=d["sport"], family=d["family"], hypothesis=d["hypothesis"],
                   p_ship=float(d["p_ship"]), dated=d.get("dated", ""))


# ---------------------------------------------------------------------------
# Append-only JSONL store
# ---------------------------------------------------------------------------

class ForecastStore:
    """Append-only JSONL self-forecast ledger; dedup by (sport, family, hypothesis)."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = Path(path) if path else DEFAULT_STORE
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._seen: Dict[Tuple[str, str, str], SelfForecast] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        with self._path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    fc = SelfForecast.from_dict(json.loads(line))
                    self._seen[fc.key] = fc
                except (KeyError, ValueError):
                    pass

    def _flush(self, fc: SelfForecast) -> None:
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(fc.to_dict()) + "\n")

    def append(self, fc: SelfForecast) -> bool:
        """Append forecast; returns False (no-op) if exact key already present."""
        if fc.key in self._seen:
            return False
        self._seen[fc.key] = fc
        self._flush(fc)
        return True

    def all_forecasts(self) -> List[SelfForecast]:
        return list(self._seen.values())

    @property
    def path(self) -> Path:
        return self._path


# ---------------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------------

@dataclass
class GradeReport:
    """Brier score + calibration of researcher P(ship) forecasts."""
    n_graded: int
    n_unresolved: int
    brier_score: float
    mean_p_ship: float
    observed_ship_rate: float
    is_overconfident: bool
    is_well_calibrated: bool
    note: str


def _outcome(verdict: str) -> float:
    return 1.0 if verdict == "SHIP" else 0.0


def grade(forecasts: List[SelfForecast], findings: List[object]) -> GradeReport:
    """Grade P(ship) forecasts against resolved verdicts.  No edge is claimed.

    findings: list of ResearchFinding (duck-typed: .sport/.family/.hypothesis/.verdict).
    SHIP=1, REJECT/DEFER/VARIANCE_ONLY=0.
    """
    idx: Dict[Tuple[str, str, str], str] = {
        (f.sport, f.family, f.hypothesis): f.verdict  # type: ignore[attr-defined]
        for f in findings
    }
    graded: List[Tuple[float, float]] = []
    n_unresolved = 0
    for fc in forecasts:
        v = idx.get(fc.key)
        if v is None:
            n_unresolved += 1
        else:
            graded.append((fc.p_ship, _outcome(v)))

    if not graded:
        return GradeReport(
            n_graded=0, n_unresolved=n_unresolved,
            brier_score=float("nan"), mean_p_ship=float("nan"),
            observed_ship_rate=float("nan"),
            is_overconfident=False, is_well_calibrated=False,
            note=("No graded forecasts yet.  Pre-register P(ship) before running "
                  "experiments; verdicts will resolve them.  No edge is claimed."),
        )

    n = len(graded)
    brier = sum((p - o) ** 2 for p, o in graded) / n
    mean_p = sum(p for p, _ in graded) / n
    osr = sum(o for _, o in graded) / n
    gap = mean_p - osr
    overconfident = gap > 0.05
    well_calibrated = abs(gap) <= 0.05

    if well_calibrated:
        note = (f"WELL-CALIBRATED: mean P(ship)={mean_p:.3f} ≈ observed ship-rate "
                f"{osr:.3f}.  On an efficient market most families REJECT; "
                f"predicting low P(ship) is correctly calibrated.  "
                f"Brier={brier:.4f}.  No edge is claimed.")
    elif overconfident:
        note = (f"OVERCONFIDENT: mean P(ship)={mean_p:.3f} >> observed ship-rate "
                f"{osr:.3f} (gap={gap:+.3f}).  Brier={brier:.4f}.  No edge is claimed.")
    else:
        note = (f"UNDERCONFIDENT: mean P(ship)={mean_p:.3f} << observed ship-rate "
                f"{osr:.3f} (gap={gap:+.3f}).  Brier={brier:.4f}.  No edge is claimed.")

    return GradeReport(n_graded=n, n_unresolved=n_unresolved, brier_score=brier,
                       mean_p_ship=mean_p, observed_ship_rate=osr,
                       is_overconfident=overconfident, is_well_calibrated=well_calibrated,
                       note=note)


# ---------------------------------------------------------------------------
# Auto-pre-register from BeliefStore posteriors
# ---------------------------------------------------------------------------

def auto_pre_register(store: object, forecast_store: ForecastStore,
                      dated: Optional[str] = None) -> int:
    """Create SelfForecast entries from BeliefStore.all_beliefs() posterior means.

    p_ship = posterior_mean.  Skips families already in the store (dedup).
    Returns number of new forecasts written.
    """
    today = dated or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    written = 0
    for bel in store.all_beliefs():  # type: ignore[attr-defined]
        fc = SelfForecast(
            sport=bel.sport, family=bel.family,
            hypothesis=(f"{bel.family}: pure transform of leak-free base "
                        f"on {bel.sport} corpus (auto-registered)"),
            p_ship=round(bel.posterior_mean, 4), dated=today,
        )
        if forecast_store.append(fc):
            written += 1
    return written


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_scoreboard(report: GradeReport) -> None:
    sep = "-" * 70
    print(sep)
    print("RESEARCHER SELF-FORECAST SCOREBOARD")
    print(sep)
    print(f"  Graded forecasts  : {report.n_graded}")
    print(f"  Unresolved        : {report.n_unresolved}")
    if report.n_graded > 0:
        print(f"  Brier score       : {report.brier_score:.4f}")
        print(f"  Mean P(ship)      : {report.mean_p_ship:.3f}")
        print(f"  Observed ship-rate: {report.observed_ship_rate:.3f}")
        print(f"  Overconfident     : {report.is_overconfident}")
        print(f"  Well-calibrated   : {report.is_well_calibrated}")
    print()
    print(f"  {report.note}")
    print(sep)


def main(argv: Optional[List[str]] = None) -> None:
    p = argparse.ArgumentParser(
        prog="self_forecast",
        description="Self-forecast scoreboard.  No edge is claimed.")
    p.add_argument("--ledger", metavar="PATH")
    p.add_argument("--store", metavar="PATH")
    p.add_argument("--auto-register", action="store_true",
                   help="Auto-register forecasts from belief store posteriors first")
    args = p.parse_args(argv)

    from scripts.research_harness.research_ledger import Ledger
    ledger = Ledger(path=Path(args.ledger) if args.ledger else None)
    fc_store = ForecastStore(path=Path(args.store) if args.store else None)

    if args.auto_register:
        from scripts.research_harness.belief_store import BeliefStore
        bstore = BeliefStore.load()
        bstore.update_from_ledger(ledger)
        n_new = auto_pre_register(bstore, fc_store)
        print(f"Auto-registered {n_new} new forecast(s) from belief posteriors.")

    report = grade(fc_store.all_forecasts(), ledger.all_findings())
    _print_scoreboard(report)


if __name__ == "__main__":
    main(sys.argv[1:])
