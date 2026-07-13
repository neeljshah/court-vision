"""scripts.platformkit.interaction_factory.builders_umpire -- B3: MLB
UMPIRE-CONDITIONED as-of attrs (mlb_umpire_self_cross template), split out per
the builders_carryover.py / builders_statcast_fatigue.py / builders_
statcast_batquality.py convention (runner.py stays under its LOC budget).
Same contract as any other runner builder: `builder(attrs, tpl) -> {"frame",
"cluster", "corpus", "kind", ...} | None` -- registered into runner._BUILDERS
by runner.py itself.

STEP0 PREMISE (what exists on disk, checked live this session):
 * data/domains/mlb/umpire_assignments.parquet -- a genuine FORWARD-capture
   daemon snapshot (238 rows, 2026-07 only) -- too sparse for a strictly-as-of
   PRIOR-games stat yet (umpire_assignment_gate_verdict.json: UNDERPOWERED,
   0 pregame-scorable games, needs >=150).
 * data/domains/mlb/probables.parquet (11316 rows, game_pk-keyed, hp_umpire_id
   99.4%% non-null, 2022-2026) -- the table umpire_zone_index.py/umpire_totals_
   gate.py already use. Per umpire_join_probe.json this is a 2026-07 BACKFILL
   snapshot for the 2022/2023 rows, not captured at-the-time -- DESCRIPTIVE/
   retrospective identity join only (same caveat catcher_framing_index.py /
   umpire_zone_index.py already carry), not independently verified as a real-
   time-knowable pregame feature. This module inherits that SAME caveat and
   is NOT offered as a leak-free live-deployable feature; it IS leak-free in
   the narrower sense the factory's own gate checks -- no future game's
   outcome informs any given game's asof value (see leak-trap test).
 * PITCH-LEVEL join: statcast_fuller__2022/2023.parquet -> probables.parquet
   on game_pk. umpire_join_probe.json measured 460/460 games on 2026-07-05;
   re-verified LIVE this session (2026-07-13) both statcast_fuller files have
   since grown to full-season coverage -- 4862 distinct combined game_pks,
   matching domains.mlb.umpire_totals_gate's own corpus (n=4861 after the
   hp_umpire_id-notna filter, 103 umpires). Pitch-level IS joinable at scale.

REUSE (not copy): build_umpire_totals_corpus() imported directly from
domains.mlb.umpire_totals_gate -- the exact game_pk-grain corpus (game_pk,
date, home_team, hp_umpire_id, total_runs, n_ooz, ooz_strikes) that module's
own pre-registered gate already built and validated (statcast raw
post_home_score/post_away_score for total_runs, derive_out_of_zone() for the
out-of-zone-strike counts). No new join logic, no new data pulled.

PRIOR ART / HONESTY NOTE: domains/mlb/umpire_totals_gate.py already
PRE-REGISTERED and REJECTED a related-but-DIFFERENT hypothesis: a single
demeaned out-of-zone-strike-rate term (with a fixed, un-fitted scale) added to
an internal league+park total-runs baseline -- verdict REJECT, planted null
matched-or-beat the real effect (added-flexibility artifact, not umpire
signal; see data/domains/mlb/umpire_totals_gate_verdict.json). The 2 attrs
here are DISTINCT candidates for the interaction factory's own 2-attr
self-cross grammar (a fresh, not-yet-tested pair, not a re-test of that closed
single-term model) -- but on priors, given the closed sibling result, a SHIP
verdict here would be a strong surprise, not an expectation. No edge claimed
either way; see .claude/rules/no-edge-claims.md.

ATTRS (STATIC_POOLS key "mlb_umpire_asof", atomic_unit "game" -- a game has
exactly ONE home-plate umpire shared by both teams, so there is no home/away
diff framing here, unlike the team_game carryover/boxdetail pools):
 * ump_total_runs_tendency_asof = this hp_umpire_id's STRICTLY-PRIOR expanding
   mean total_runs MINUS the STRICTLY-PRIOR expanding LEAGUE-WIDE mean total
   runs (demeaned, "vs league mean" per the task spec), floored at
   MIN_UMPIRE_PRIOR prior games for this umpire.
 * ump_called_strike_proxy_asof = this hp_umpire_id's STRICTLY-PRIOR expanding
   out-of-zone STRIKE rate (called-or-swung, raw, NOT demeaned -- same
   ooz_strikes/n_ooz ingredients umpire_totals_gate.py's own ump_term uses,
   just exposed as a standalone as-of attribute here rather than folded into
   one scaled term), same MIN_UMPIRE_PRIOR floor.

OUTCOME: y = total_runs (this game's own REAL total, not as-of -- only
features need to be leak-free).

LEAK RULE (binding): a game's own asof value uses ONLY games strictly before
it in (date, game_pk) chronological order -- both the per-umpire cumsum and
the league-wide cumsum are shift(1)'d before dividing. See
test_builders_umpire.py's tamper-today's-own-outcome trap test.

NO STATE-CONDITIONER cross registered: the only other MLB "prior" pools in
generator.py (carryover_asof, mlb_sp_fatigue_prior, mlb_batquality_prior) all
live at "team_game" or "pitcher_appearance_checkpoint" atomic units with a
per-team-diff or per-pitcher framing; umpire attrs are shared per-game with no
home/away side to diff against, so forcing a cross would need an artificial
per-team assignment of a shared value -- not a sensible pairing, so it is
honestly skipped per the task's own conditional ("if a sensible pairing
exists").

Per-file test:
  cd /c/Users/neelj/nba-ai-system && python -m pytest scripts/platformkit/interaction_factory/test_builders_umpire.py -q
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from domains.mlb.umpire_totals_gate import build_umpire_totals_corpus

REPO = Path(__file__).resolve().parents[3]
_STATCAST_2022 = REPO / "data" / "cache" / "statcast" / "statcast_fuller__2022.parquet"
_STATCAST_2023 = REPO / "data" / "cache" / "statcast" / "statcast_fuller__2023.parquet"
_PROBABLES = REPO / "data" / "domains" / "mlb" / "probables.parquet"
_UMPIRE_SOURCES = (_STATCAST_2022, _STATCAST_2023, _PROBABLES)
_UMPIRE_CORPUS_ID = "statcast_fuller_x_probables_umpire_totals"

MIN_UMPIRE_PRIOR = 15  # same floor domains.mlb.umpire_totals_gate.MIN_UMPIRE_PRIOR uses


def build_umpire_game_frame(corpus: pd.DataFrame, attrs: List[str],
                             min_prior: int = MIN_UMPIRE_PRIOR) -> pd.DataFrame:
    """Leak-free per-game frame from domains.mlb.umpire_totals_gate's own
    corpus shape (game_pk, date, home_team, hp_umpire_id, total_runs, n_ooz,
    ooz_strikes). Sorted chronologically; every asof__ column is a
    STRICTLY-PRIOR expanding stat (cumsum().shift(1)), the current game
    excluded from its own feature by construction -- same idiom
    build_mlb_fatigue_prior_frame's cross-game cumsum-shift uses."""
    d = corpus.sort_values(["date", "game_pk"], kind="mergesort").reset_index(drop=True)
    league_cum_n = d.index.to_series()  # row i (0-indexed) has exactly i strictly-prior rows
    league_cum_sum = d["total_runs"].cumsum().shift(1)
    league_mean = league_cum_sum / league_cum_n.where(league_cum_n > 0)

    grp = d.groupby("hp_umpire_id", sort=False)
    n_prior = grp.cumcount()
    valid = n_prior >= min_prior

    if "ump_total_runs_tendency_asof" in attrs:
        ump_cum_runs = grp["total_runs"].transform(lambda s: s.cumsum().shift(1))
        ump_mean_runs = ump_cum_runs / n_prior.where(valid)
        d["asof__ump_total_runs_tendency_asof"] = (ump_mean_runs - league_mean).where(valid)
    if "ump_called_strike_proxy_asof" in attrs:
        ump_cum_strikes = grp["ooz_strikes"].transform(lambda s: s.cumsum().shift(1))
        ump_cum_n_ooz = grp["n_ooz"].transform(lambda s: s.cumsum().shift(1))
        d["asof__ump_called_strike_proxy_asof"] = (
            ump_cum_strikes / ump_cum_n_ooz.where(ump_cum_n_ooz > 0)).where(valid)

    d["y"] = d["total_runs"]
    keep = ["game_pk", "hp_umpire_id", "y"] + [
        "asof__" + a for a in attrs if ("asof__" + a) in d.columns]
    return d[keep].copy()


def _mlb_umpire_asof_builder(attrs: List[str], tpl: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not all(p.exists() for p in _UMPIRE_SOURCES):
        return None
    corpus = build_umpire_totals_corpus()
    frame = build_umpire_game_frame(corpus, attrs)
    return {"frame": frame, "cluster": "hp_umpire_id", "corpus": _UMPIRE_CORPUS_ID, "kind": "ols"}


__all__ = ["build_umpire_game_frame", "_mlb_umpire_asof_builder", "MIN_UMPIRE_PRIOR"]
