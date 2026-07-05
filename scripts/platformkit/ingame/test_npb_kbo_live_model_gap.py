"""Per-file regression test for the npb/kbo in-game-model gap (LANE npbkbo-live-model).

WHY THIS FILE EXISTS: this lane's task was to wire an npb/kbo branch into
scripts.platformkit.frontend.live_board.live_model_home_prob using the proven cross-sport
BASE pattern (sigmoid((a+b*frac_elapsed)*state_diff), see
scripts.platformkit.ingame.ingame_gate_generic_models.fit_base). That fit requires a
corpus of INTRA-GAME ticks: {state_diff, frac_elapsed, p0, outcome} per game (the frozen
schema at data/cache/ingame/{sport}_states__*.parquet). Investigation this wave found:

  1. ZERO such tick files exist for npb/kbo (data/cache/ingame has none matching
     npb_states__*.parquet / kbo_states__*.parquet).
  2. The only historical corpora (data/domains/{npb,kbo}/*_results.parquet) are
     FINAL-SCORE-ONLY -- one row per completed game, no innings/running-score/frac_elapsed
     column at all. There is nothing to derive in-game ticks from, even offline.
  3. The live feed itself (scripts.platformkit.ingame.npb_kbo_live_state) ALWAYS returns
     frac_elapsed=None for both sports -- npb.jp's schedule-detail page and koreabaseball's
     GetScheduleList expose no distinct mid-game marker keyless (documented in that
     module's own docstring + test_npb_kbo_live_state.py assertions).

So this is a DATA-AVAILABILITY WALL, not a missing-dispatch-branch bug: there is no way to
fit the requested BASE model, and even a hypothetically-fitted one could never be fed a
real frac_elapsed from the live tick stream. Per the lane's RAILS ("if a sport fails the
guard, report HONEST_NEGATIVE ... and do NOT wire it"), NO branch was added to live_board.

This test locks the (pre-existing, unchanged) honest behavior: live_model_home_prob
returns None for npb/kbo on every state shape the real live feed can produce -- so the
capture loop's no_model_prob skip (data/domains/npb_kbo_grade_diagnosis.json) is UNCHANGED
by this lane, and no fabricated probability can ever reach a paired tick for these sports.

Full proof + real-corpus numbers: data/domains/npb_kbo_model_wire_proof.json.

Per-file test (do NOT run the full suite -- see repo rails):
  cd /c/Users/neelj/nba-ai-system && \
    python -m pytest scripts/platformkit/ingame/test_npb_kbo_live_model_gap.py -q
"""
from __future__ import annotations

import glob
import os

from scripts.platformkit.frontend import live_board as lb

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_STATE_DIR = os.path.join(_REPO, "data", "cache", "ingame")


def test_no_ingame_tick_corpus_exists_for_npb_or_kbo():
    """The frozen-schema tick corpus (state_diff,frac_elapsed,p0,outcome) that fit_base
    needs has zero files for npb/kbo -- confirms there is nothing to fit a BASE model on."""
    npb_files = glob.glob(os.path.join(_STATE_DIR, "npb_states__*.parquet"))
    kbo_files = glob.glob(os.path.join(_STATE_DIR, "kbo_states__*.parquet"))
    assert npb_files == []
    assert kbo_files == []


def test_live_model_home_prob_returns_none_for_npb():
    """No dispatch branch was wired (honest -- no corpus/no live frac_elapsed to serve
    from) -- npb must still return None, exactly like any other unsupported sport."""
    state = {"home": "Yomiuri Giants", "away": "Hanshin Tigers",
              "home_score": 3.0, "away_score": 1.0, "frac_elapsed": None}
    assert lb.live_model_home_prob("npb", state) is None


def test_live_model_home_prob_returns_none_for_kbo():
    state = {"home": "LG Twins", "away": "KT Wiz",
              "home_score": 2.0, "away_score": 2.0, "frac_elapsed": None}
    assert lb.live_model_home_prob("kbo", state) is None


def test_live_model_home_prob_none_even_if_frac_elapsed_were_present():
    """Belt-and-suspenders: even a (hypothetical) state carrying a frac_elapsed still
    returns None for npb/kbo -- there is genuinely no dispatch branch, not merely a
    missing-field guard, so no future frac_elapsed source can silently start serving an
    unfit/unproven number through this path by accident."""
    state = {"home": "SSG Landers", "away": "Doosan Bears",
              "home_score": 4.0, "away_score": 3.0, "frac_elapsed": 0.6}
    assert lb.live_model_home_prob("kbo", state) is None
    state_npb = {"home": "Chunichi Dragons", "away": "Hiroshima Toyo Carp",
                 "home_score": 1.0, "away_score": 0.0, "frac_elapsed": 0.6}
    assert lb.live_model_home_prob("npb", state_npb) is None
