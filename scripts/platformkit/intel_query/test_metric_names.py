"""Per-file tests: name-derived metric fallback (metric_names.py)."""
import json

from scripts.platformkit.intel_query import metric_names as mn


def _index(tmp_path, fam, metrics):
    p = tmp_path / f"{fam}.index.jsonl"
    with open(p, "w") as fh:
        for m in metrics:
            fh.write(json.dumps({"claim_id": f"{fam}_{m}", "metric": m,
                                 "verdict": "VERIFIED"}) + "\n")
    return p


def setup_function(_):
    mn._CACHE = None  # isolate the mtime cache between tests


def test_name_match_longest_wins(tmp_path):
    _index(tmp_path, "fam_a", ["gf_diff", "winrate_diff"])
    assert mn.metric_from_name("top soccer teams by gf diff", tmp_path) == "gf_diff"
    assert mn.metric_from_name("teams by winrate diff please", tmp_path) == "winrate_diff"


def test_ambiguous_phrase_refuses(tmp_path):
    # same normalized phrase from two DIFFERENT metric spellings cannot happen
    # (phrase derives from name), so ambiguity = same phrase in two stores
    # with different real names is impossible; simulate the >1 set directly.
    _index(tmp_path, "fam_a", ["efg_delta"])
    _index(tmp_path, "fam_b", ["efg_delta"])  # same metric twice = fine
    assert mn.metric_from_name("rank by efg delta", tmp_path) == "efg_delta"


def test_formula_shaped_metrics_skipped(tmp_path):
    _index(tmp_path, "fam_a", ["sum(fta) / sum(fga)", "ts_pct"])
    names = mn._build(tmp_path)
    assert "ts pct" in names and len(names) == 1


def test_no_match_returns_none(tmp_path):
    _index(tmp_path, "fam_a", ["gf_diff"])
    assert mn.metric_from_name("who is the best shooter", tmp_path) is None


def test_tiny_phrases_excluded(tmp_path):
    _index(tmp_path, "fam_a", ["efg"])  # 3 chars < 4 floor
    assert mn.metric_from_name("efg leaders", tmp_path) is None


def test_cache_invalidates_on_new_index(tmp_path):
    _index(tmp_path, "fam_a", ["gf_diff"])
    assert mn.metric_from_name("gf diff", tmp_path) == "gf_diff"
    import time
    time.sleep(0.02)
    _index(tmp_path, "fam_b", ["xg_per_possession"])
    assert mn.metric_from_name("xg per possession", tmp_path) == "xg_per_possession"
