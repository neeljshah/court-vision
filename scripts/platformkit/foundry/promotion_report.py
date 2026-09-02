"""Promotion LIST from one or more results DBs: the frozen rule applied, nothing charged.

Reads T1 SCREEN rows, recomputes each hypothesis's frozen family from FWER_FAMILIES_SPEC by
(sport, horizon, market, member) -- the DB's `family` column is never trusted (S66: the pod
hour labelled 6,000 claims with the queue's sport) -- asserts every group is single-sport,
ranks by the frozen `rank_by` inside `promotion.promote`, and prints markdown. A SCREEN is a
non-finding; this module prints candidates for the orchestrator to charge LATER, serially.
Calibration language only.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterator, Optional

from scripts.platformkit.eval_gate.family_bars import load_families
from scripts.platformkit.foundry.grammar import Hypothesis
from scripts.platformkit.foundry.promotion import PromotionRule


@dataclass(frozen=True)
class Screen:
    """The slice of a T1 row `promotion.promote` ranks on, plus what the memo prints."""
    hash: str
    tier: str
    family: str
    brier_model: float
    brier_close: float
    n: int
    n_eff: float
    hypothesis: Hypothesis
    iso_week: str
    screen_p: Optional[float]
    incumbent: str
    partition_sha: str

    @property
    def delta(self) -> float:
        return self.brier_model - self.brier_close


def _iso_week(stamp: str) -> str:
    year, week, _ = datetime.fromisoformat(stamp.replace("Z", "+00:00")).isocalendar()
    return "%04d-W%02d" % (year, week)


def families_of(hypothesis: Hypothesis) -> list:
    """Every frozen family that enumerates this hypothesis; [] if none does."""
    return [f.name for f in load_families().families
            if f.sport == hypothesis.sport and f.horizon == hypothesis.horizon
            and f.market == hypothesis.market and hypothesis.feature in f.members]


def screens(db_path: Path) -> Iterator[Screen]:
    """T1 SCREEN rows joined to their hypothesis; the archive JSON supplies screen_p + incumbent."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT r.*, h.sport, h.feature, h.transform, h.params, h.conditioning, h.horizon, h.market "
        "FROM result r JOIN hypothesis h ON h.hash = r.hash WHERE r.tier='T1' AND r.verdict='SCREEN' "
        "AND r.brier_model IS NOT NULL ORDER BY r.id").fetchall()
    for row in rows:
        hypothesis = Hypothesis(row["sport"], row["feature"], row["transform"],
                                tuple(tuple(p) for p in json.loads(row["params"])),
                                frozenset(json.loads(row["conditioning"])), row["horizon"], row["market"])
        extra: dict = {}
        path = Path(row["artifact_path"] or "")
        if path.exists():
            extra = json.loads(path.read_text(encoding="ascii"))
        archive = extra.get("archive") or {}
        for family in families_of(hypothesis) or ["UNFROZEN:%s" % row["sport"]]:
            yield Screen(row["hash"], row["tier"], family, float(row["brier_model"]),
                         float(row["brier_close"]), int(row["n"]), float(row["n_eff"] or 0.0),
                         hypothesis, _iso_week(row["run_at"]), archive.get("screen_p"),
                         str(extra.get("incumbent", "?")), str(extra.get("screen_partition_sha256", "?")))
    conn.close()


def promotion_list(rows: list, rule: PromotionRule) -> dict:
    """{(family, iso_week): [Screen, ...]} -- the frozen top_n per group, single-sport asserted."""
    out: dict = {}
    for key in sorted({(s.family, s.iso_week) for s in rows}):
        group = [s for s in rows if (s.family, s.iso_week) == key]
        sports = {s.hypothesis.sport for s in group}
        if len(sports) != 1:
            raise ValueError("group %s mixes sports %s" % (key, sorted(sports)))
        ranked = sorted(group, key=lambda s: (s.delta, s.hash))
        out[key] = ranked[:rule.top_n]
    return out


def render(rows: list, picks: dict, rule: PromotionRule) -> str:
    lines = ["| family | iso_week | screened | beat incumbent (delta<0) | promoted | best delta | best n_eff | incumbent | partition sha (screen) |",
             "|---|---|---|---|---|---|---|---|---|"]
    for (family, week), chosen in picks.items():
        group = [s for s in rows if (s.family, s.iso_week) == (family, week)]
        beat = sum(1 for s in group if s.delta < 0)
        best = chosen[0]
        lines.append("| %s | %s | %d | %d | %d | %+.6f | %.1f | %s | %s |" % (
            family, week, len(group), beat, len(chosen), best.delta, best.n_eff, best.incumbent,
            best.partition_sha[:16]))
    lines.append("")
    lines.append("## Candidates per family (SCREEN deltas -- NOT findings)")
    for (family, week), chosen in picks.items():
        lines.append("")
        lines.append("### %s (%s)" % (family, week))
        lines.append("| rank | feature | transform | params | delta (model - incumbent) | screen DM p | n | n_eff | hash |")
        lines.append("|---|---|---|---|---|---|---|---|---|")
        for rank, s in enumerate(chosen, 1):
            p = "n/a" if s.screen_p is None else "%.4f" % s.screen_p
            lines.append("| %d | %s | %s | %s | %+.6f | %s | %d | %.1f | %s |" % (
                rank, s.hypothesis.feature, s.hypothesis.transform,
                dict(s.hypothesis.params) or "-", s.delta, p, s.n, s.n_eff, s.hash[:16]))
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", nargs="+", required=True)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    rule = PromotionRule.from_spec()
    rows = [s for path in args.db for s in screens(Path(path))]
    picks = promotion_list(rows, rule)
    text = render(rows, picks, rule)
    dist = Counter("delta<0" if s.delta < 0 else "delta>=0" for s in rows)
    head = ["screens=%d families=%d promoted=%d rule=%s top_n=%d prereg=%s" % (
        len(rows), len(picks), sum(len(v) for v in picks.values()), rule.spec_version, rule.top_n,
        rule.prereg_sha256), "distribution: %s" % dict(dist), ""]
    text = "\n".join(head) + text
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="ascii")
    print(text)


if __name__ == "__main__":
    main()
