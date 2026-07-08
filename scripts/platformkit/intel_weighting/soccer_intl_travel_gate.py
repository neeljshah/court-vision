"""Gate + weight-ledger wiring for soccer_intl_team_travel_rate (1458 claims,
data/cache/intel_claims/soccer_intl_team_travel_rate.jsonl) -- the biggest
family with NO weight-ledger row. cli.py's per-sport dispatch (`--sport
soccer`) deliberately EXCLUDES every soccer_intl_* family (a different
corpus/domain than the soccer club one, see cli._SPORT_EXCLUDE_PREFIX), and
sport_config.py had no "soccer_intl" games loader at all -- this family was
simply never reachable by the gate. This module adds the missing wiring
(sport_config.py now has a soccer_intl loader; generic_rating.py now has its
HFA constant) and runs relevance_gate.run_family directly for this one
family, bypassing the club-soccer dispatch entirely.

EXPECTED RESULT, and why it is honest, not a bug: domains/soccer_intl/
claims_grid.py declares (see its own docstring) that career_to_date/home/away
are the ONLY windows this corpus's per-team match cadence can support -- a
per-season window was investigated and rejected there (national teams play
too few matches/year for a usable per-team floor). claim_features.
window_to_season() refuses any window containing "career"/"home"/"away" by
design (leak discipline: only a strictly-prior-SEASON aggregate may condition
the gate). So every claim in this family is UNTESTABLE by window, for every
sport(-shaped) games table -- not a data or wiring bug, a structural
consequence of the corpus's own cadence, already documented independently in
claims_grid.py. The row itself (UNTESTABLE, with the reason) is the
deliverable: it stops this family from being silently invisible to
intel_weighting's catalogue.

CLI: python -m scripts.platformkit.intel_weighting.soccer_intl_travel_gate
"""
from __future__ import annotations

from typing import List

from scripts.platformkit.intel_weighting.relevance_gate import GateResult, run_family
from scripts.platformkit.intel_weighting.weight_ledger import LEDGER, append_results

FAMILY = "soccer_intl_team_travel_rate"
SPORT = "soccer_intl"


def run() -> List[GateResult]:
    return run_family(SPORT, FAMILY)


def main() -> int:
    results = run()
    for g in results:
        print(f"family={g.family} metric={g.metric} sport={g.sport} n_games={g.n_games} "
              f"verdict={g.verdict} caveats={g.caveats}")
    path = append_results(results)
    print(f"wrote {len(results)} row(s) -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
