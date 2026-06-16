"""Per-file test: retrieve.py -- RRF fusion math, exact boost, honest-reject gate.

The RRF / boost / tokenizer units run with NO built index. The end-to-end retrieval
checks run only if data/index/vault/ exists (skipped otherwise so the test is
self-contained on a fresh clone). Standalone-runnable + pytest-discoverable. ASCII.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[4]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from scripts.platformkit.knowledge import config  # noqa: E402
from scripts.platformkit.knowledge import retrieve as R  # noqa: E402
from scripts.platformkit.knowledge.text_utils import stem_tokenizer  # noqa: E402

_HAS_INDEX = config.CORPUS_PARQUET.exists()


def test_rrf_merges_and_weights():
    # Item 0 ranks first in dense, item 1 first in sparse. With equal weight, both
    # should outrank a sparse-only item that appears lower in only one lane.
    dense = [0, 2, 5]
    sparse = [1, 0, 7]
    fused = R._rrf(dense, sparse, dense_w=0.5, sparse_w=0.5, k=60)
    # item 0 appears in both lanes -> highest fused score
    assert max(fused, key=lambda i: fused[i]) == 0
    # an item in only one lane scores less than the doubly-ranked item
    assert fused[0] > fused[5]


def test_rrf_weighting_direction():
    fused_dense = R._rrf([9], [], dense_w=0.9, sparse_w=0.1, k=60)
    fused_sparse = R._rrf([], [9], dense_w=0.9, sparse_w=0.1, k=60)
    # heavier dense weight -> a dense-only hit beats the same-rank sparse-only hit
    assert fused_dense[9] > fused_sparse[9]


def test_proportional_title_boost():
    q = set(stem_tokenizer("drop coverage ball screen defense"))
    full = R._boost(q, "Drop Coverage Against the Ball Screen", "DefensiveSchemes")
    partial = R._boost(q, "Transition Defense Get-Back", "TransitionDynamics")
    # a title sharing more query tokens gets a strictly larger boost
    assert full > partial >= 0.0
    assert full <= config.TITLE_BOOST + config.CATEGORY_BOOST + 1e-9


def test_tokenizer_hyphen_split():
    toks = stem_tokenizer("Rest-Defense Stability")
    # compound kept AND split so it matches separated query words
    assert "rest-defense" in toks and "rest" in toks and "defense" in toks


def test_retrieve_relevant_vs_reject():
    if not _HAS_INDEX:
        print("SKIP end-to-end retrieve (no index built)")
        return
    R.reset_state()
    rel = R.retrieve("drop coverage pick and roll defense", sport="NBA", top_k=6)
    assert not rel.reject and rel.hits
    assert all(h.citation == f"[[{h.note_id}]]" for h in rel.hits)
    # scores are a relevance rank, never a probability -> bounded, no % semantics
    assert all(isinstance(h.score, float) for h in rel.hits)
    irrel = R.retrieve("lunar regolith spectroscopy compiler kernel", sport="NBA")
    assert irrel.reject and not irrel.hits
    assert irrel.reject_message == "No relevant intel found."


def test_memory_source_retrieval():
    if not _HAS_INDEX:
        print("SKIP memory retrieve (no index built)")
        return
    R.reset_state()
    res = R.retrieve("why minimizing prediction error is not a betting edge",
                     sport="MEMORY", top_k=5)
    assert not res.reject and res.hits
    assert all(h.note_id.startswith("MEMORY/") for h in res.hits)


def _run() -> int:
    fails = 0
    for fn in (test_rrf_merges_and_weights, test_rrf_weighting_direction,
               test_proportional_title_boost, test_tokenizer_hyphen_split,
               test_retrieve_relevant_vs_reject, test_memory_source_retrieval):
        try:
            fn()
            print("PASS", fn.__name__)
        except AssertionError as exc:
            fails += 1
            print("FAIL", fn.__name__, exc)
    return fails


if __name__ == "__main__":
    raise SystemExit(_run())
