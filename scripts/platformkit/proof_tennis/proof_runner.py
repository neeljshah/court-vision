"""scripts.platformkit.proof_tennis.proof_runner — V1/V2/V3/V4 execution helpers.

Split from run_proof.py to stay within the 300-LOC/file discipline.
Imports: only kernel gate seam, domains.tennis.*, proof_metrics, decision-kernel seam.
ZERO src.data / src.sim / src.tracking / src.pipeline / domains.nba imports.

Delegates to the sport-blind generic harness in scripts.platformkit.proof_common
(platform-harness promotion, W-PROOFSWAP-002)."""
from __future__ import annotations

from scripts.platformkit.proof_tennis.spec import SPEC
from scripts.platformkit.proof_common import paper as _paper, runner as _runner

_V4_DISCLAIMER = _paper._V4_DISCLAIMER


def run_v1(adapter):
    return _runner.run_v1(SPEC, adapter)


def run_v2(adapter):
    return _runner.run_v2(SPEC, adapter)


def run_v3(adapter):
    return _runner.run_v3(SPEC, adapter)


def run_v4(adapter, paper_book_dir=None):
    return _paper.run_v4(SPEC, adapter, paper_book_dir=paper_book_dir)
