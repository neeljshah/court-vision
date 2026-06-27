"""Per-file tests for scripts.platformkit.new_sport_scaffold.

Stamps a TOY domain and proves the generated feature_spec + ingest_manifest are
valid out of the box: exec the rendered module text, then run the real validators
(build_base_matrix on the generated spec; IngestManifest.validate()). Also checks
scaffold() file writing + overwrite guard.

Run: C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
       tests/platformkit/test_new_sport_scaffold.py -q
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts.platformkit.feature_spec_core import FeatureSpec, build_base_matrix
from scripts.platformkit.ingest_manifest_core import IngestManifest
from scripts.platformkit.new_sport_scaffold import render_all, scaffold


def _exec_module(text: str) -> dict:
    ns: dict = {}
    exec(compile(text, "<scaffold>", "exec"), ns)
    return ns


def _find(ns: dict, typ: type):
    for v in ns.values():
        if isinstance(v, typ):
            return v
    return None


def test_render_all_has_three_files():
    files = render_all("toysport")
    assert set(files) == {"__init__.py", "feature_spec.py", "ingest_manifest.py"}
    assert "TOYSPORT_BASE_SPEC" in files["feature_spec.py"]
    assert "TOYSPORT_MANIFEST" in files["ingest_manifest.py"]
    assert "OP_DIFF" in files["feature_spec.py"]  # the rating_diff toy field


def test_generated_feature_spec_validators_reach_cleanly():
    ns = _exec_module(render_all("toysport")["feature_spec.py"])
    spec = _find(ns, FeatureSpec)
    assert spec is not None and spec.sport == "toysport"
    assert spec.catalog_hash()  # hashing works
    assert spec.col_names() == ["rating_diff", "rest_days"]
    # build on a synthetic frame with the toy sources present
    df = pd.DataFrame({"home_rating": [1600.0, 1400.0], "away_rating": [1500.0, 1500.0],
                       "rest_days": [3.0, 7.0]})
    mat, names = build_base_matrix(spec, df)
    assert names == ["rating_diff", "rest_days"]
    assert mat.shape == (2, 2)
    np.testing.assert_allclose(mat[:, 0], [100.0, -100.0])  # diff op


def test_generated_manifest_validators_reach_cleanly():
    ns = _exec_module(render_all("toysport")["ingest_manifest.py"])
    man = _find(ns, IngestManifest)
    assert man is not None and man.sport == "toysport"
    assert man.validate() == []
    assert set(man.pregame_corpora()) == {"games", "odds"}


def test_scaffold_writes_and_guards_overwrite(tmp_path):
    written = scaffold("toysport", tmp_path)
    assert len(written) == 3
    for p in written:
        assert p.exists() and p.read_text(encoding="ascii")
    # second call refuses to clobber...
    with pytest.raises(FileExistsError):
        scaffold("toysport", tmp_path)
    # ...unless forced
    again = scaffold("toysport", tmp_path, force=True)
    assert len(again) == 3
