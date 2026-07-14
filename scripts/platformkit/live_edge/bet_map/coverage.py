"""scripts.platformkit.live_edge.bet_map.coverage -- coverage matrix + honest
uncovered-bet-shape (mining backlog) report for Track B3.

Runs bet_map.bet_fanout over the real on-disk ledger and reports, for a
representative NBA slate, which of bet_map.ALL_MARKET_SHAPES have >=1
informing claim (any lifecycle -- a screened claim is still a real signal
that COULD inform a shape once mined) vs which have zero. Zero-coverage
shapes are the explicit mining backlog for future cycles.

INVARIANTS: pandas + stdlib only. <=300 LOC. ASCII stdout. Writes only under
data/omni/live_edge/bet_map/ (own namespace, never data/registry/).
"""
from __future__ import annotations

import pathlib

import pandas as pd

from scripts.platformkit.live_edge.bet_map.bet_map import ALL_MARKET_SHAPES, bet_fanout

_REPORT_DIR = pathlib.Path("data/omni/live_edge/bet_map")
_REPORT_NAME = "COVERAGE_REPORT.md"


def coverage_matrix(sport: str = "nba", base_dir=None) -> pd.DataFrame:
    """One row per market shape in ALL_MARKET_SHAPES: n_claims (distinct,
    any lifecycle) that can inform it, and covered (n_claims >= 1)."""
    fan = bet_fanout(sport=sport, base_dir=base_dir)
    fan = fan[fan["market_family"] != ""]
    counts = fan.groupby("market_family")["claim_id"].nunique()
    rows = [{"market_family": fam, "n_claims": int(counts.get(fam, 0)),
             "covered": bool(counts.get(fam, 0) >= 1)}
            for fam in ALL_MARKET_SHAPES]
    return (pd.DataFrame(rows)
            .sort_values(["covered", "n_claims"], ascending=[True, False])
            .reset_index(drop=True))


def unmapped_summary(sport: str = "nba", base_dir=None) -> pd.DataFrame:
    """Claims whose topic resolved to no observable at all -- honest count
    of what bet_map still cannot place, grouped by topic."""
    fan = bet_fanout(sport=sport, base_dir=base_dir)
    unmapped = fan[fan["observable"] == "unmapped"]
    if unmapped.empty:
        return pd.DataFrame(columns=["topic", "n_claims"])
    return (unmapped.drop_duplicates("claim_id").groupby("topic")
            .size().reset_index(name="n_claims")
            .sort_values("n_claims", ascending=False).reset_index(drop=True))


def write_report(sport: str = "nba", base_dir=None,
                  out_dir: pathlib.Path | None = None) -> pathlib.Path:
    matrix = coverage_matrix(sport=sport, base_dir=base_dir)
    unmapped = unmapped_summary(sport=sport, base_dir=base_dir)
    n_total_shapes = len(matrix)
    n_covered = int(matrix["covered"].sum())
    uncovered = matrix[~matrix["covered"]]["market_family"].tolist()

    lines = [
        "# Track B3 -- claim -> bet-shape coverage report",
        "",
        f"Sport slate: {sport}. Shapes covered: {n_covered}/{n_total_shapes} "
        f"({100.0 * n_covered / n_total_shapes:.1f}%). Any-lifecycle claims "
        "count (mining-target index, not a trusted-signal index).",
        "",
        "## Coverage matrix",
        "",
        "| market_family | n_claims | covered |",
        "|---|---|---|",
    ]
    for _, r in matrix.iterrows():
        lines.append(f"| {r['market_family']} | {r['n_claims']} | "
                      f"{'yes' if r['covered'] else 'NO'} |")

    lines += ["", "## Uncovered bet shapes (mining backlog, ranked as-is)", ""]
    if uncovered:
        for fam in uncovered:
            lines.append(f"- {fam}")
    else:
        lines.append("- (none -- every enumerated shape has >=1 informing claim)")

    lines += ["", "## Claims with no resolvable observable (by topic)", ""]
    if unmapped.empty:
        lines.append("- (none)")
    else:
        for _, r in unmapped.iterrows():
            lines.append(f"- {r['topic']}: {r['n_claims']} claims")

    out_path = (out_dir or _REPORT_DIR) / _REPORT_NAME
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n", encoding="ascii", errors="replace")
    return out_path


if __name__ == "__main__":
    p = write_report()
    print(f"wrote {p}")
