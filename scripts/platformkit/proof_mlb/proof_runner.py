"""scripts.platformkit.proof_mlb.proof_runner — V1/V2/V3/V4 execution helpers.

ZERO src.data/src.sim/src.tracking/src.pipeline/domains.nba/domains.basketball_nba
or other-domain imports.

Delegates to the sport-blind generic harness in scripts.platformkit.proof_common
(platform-harness promotion, W-PROOFSWAP-002)."""
from __future__ import annotations

from scripts.platformkit.proof_mlb.spec import SPEC
from scripts.platformkit.proof_common import paper as _paper, runner as _runner

_V4_DISCLAIMER = _paper._V4_DISCLAIMER


def run_v1(adapter, league_filter=None):
    return _runner.run_v1(SPEC, adapter, ctx=league_filter)


def run_v2(adapter, league_filter=None):
    return _runner.run_v2(SPEC, adapter, ctx=league_filter)


def run_v3(adapter, league_filter=None):
    return _runner.run_v3(SPEC, adapter, ctx=league_filter)


def run_v4(adapter, paper_book_dir=None, league_filter=None):
    return _paper.run_v4(SPEC, adapter, paper_book_dir=paper_book_dir, ctx=league_filter)
