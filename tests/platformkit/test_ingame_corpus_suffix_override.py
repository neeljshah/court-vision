"""CV_INGAME_CORPUS_SUFFIX must move the corpus root of every timing producer
regenerated in the second in-game regeneration pass, and must change nothing by
default.

The six timing artifacts read three different kinds of corpus root:

  * a glob over data/cache/ingame_grade_joined/<sport>       -- blowout_dynamics
    (via state_conditioned_calibration.load_records) and market_convergence
    (via info_arrival_curve.CORPORA);
  * an upstream showcase artifact                            -- why_attribution,
    novel_live_clock_fraction, novel_market_foresight_premium, resolved through
    _clone_safe.staged_input;
  * the NBA reliability map                                  -- comeback_atlas,
    which does not read the in-game join corpus at all and is pinned here so a
    future edit cannot quietly point it at a corpus it never used.

Run: python -m pytest tests/platformkit/test_ingame_corpus_suffix_override.py -q
"""
import importlib
import os

import pytest

SHOWCASE = "scripts.platformkit.analytics_showcase"
ENV = "CV_INGAME_CORPUS_SUFFIX"


def _reload(*names):
    """Reload modules in dependency order under the current environment."""
    mods = [importlib.reload(importlib.import_module("%s.%s" % (SHOWCASE, n)))
            for n in names]
    return mods[-1]


@pytest.fixture(autouse=True)
def _restore_default_modules():
    """Leave sys.modules holding the default-environment versions."""
    yield
    os.environ.pop(ENV, None)
    _reload("_clone_safe", "state_conditioned_calibration", "info_arrival_curve",
            "blowout_dynamics", "market_convergence", "why_attribution",
            "novel_live_clock_fraction", "novel_market_foresight_premium",
            "comeback_atlas")


def _set(monkeypatch, value):
    if value is None:
        monkeypatch.delenv(ENV, raising=False)
    else:
        monkeypatch.setenv(ENV, value)


def _corpus_glob_roots(monkeypatch, value):
    """(blowout_dynamics root, market_convergence mlb pattern) under `value`."""
    _set(monkeypatch, value)
    _reload("_clone_safe")
    scc = _reload("state_conditioned_calibration")
    _reload("blowout_dynamics")
    iac = _reload("info_arrival_curve")
    mc = _reload("market_convergence")
    blow_root = os.path.join(scc.CORPUS_DIR, "mlb" + scc.CORPUS_SUFFIX)
    assert mc.CORPORA is iac.CORPORA, "market_convergence must reuse the shared corpus map"
    return blow_root.replace("\\", "/"), mc.CORPORA["mlb"]


def _artifact_inputs(monkeypatch, value):
    """The upstream-artifact corpus roots of the three derived producers."""
    _set(monkeypatch, value)
    _reload("_clone_safe")
    why = _reload("why_attribution")
    lcf = _reload("novel_live_clock_fraction")
    mfp = _reload("novel_market_foresight_premium")
    return [p.replace("\\", "/") for p in
            (why.IN_JSON, lcf.IN_BLOWOUT, mfp.IN_BRIER, mfp.IN_ENTROPY)]


def test_default_corpus_roots_are_the_published_ones(monkeypatch):
    blow_root, mc_pattern = _corpus_glob_roots(monkeypatch, None)
    assert blow_root.endswith("data/cache/ingame_grade_joined/mlb")
    assert mc_pattern.replace("\\", "/") == "data/cache/ingame_grade_joined/mlb/*.jsonl"
    for path in _artifact_inputs(monkeypatch, None):
        assert "/out/" in path and "out_segmented" not in path, path


def test_override_moves_the_glob_corpus_roots(monkeypatch):
    blow_root, mc_pattern = _corpus_glob_roots(monkeypatch, "_segmented")
    assert blow_root.endswith("data/cache/ingame_grade_joined/mlb_segmented")
    assert mc_pattern.replace("\\", "/") == "data/cache/ingame_grade_joined/mlb_segmented/*.jsonl"


def test_override_moves_the_artifact_corpus_roots(monkeypatch):
    for path in _artifact_inputs(monkeypatch, "_segmented"):
        assert "/out_segmented/" in path, path
        assert os.path.exists(path), path


def test_staged_input_falls_back_when_nothing_is_staged(tmp_path, monkeypatch):
    """An artifact with no staged copy keeps the published one, override or not."""
    monkeypatch.setenv(ENV, "_segmented")
    clone_safe = _reload("_clone_safe")
    (tmp_path / "out").mkdir()
    (tmp_path / "out_segmented").mkdir()
    (tmp_path / "out" / "only_published.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(clone_safe, "_SHOWCASE", tmp_path)
    assert clone_safe.staged_input("only_published.json") == str(tmp_path / "out" / "only_published.json")
    (tmp_path / "out_segmented" / "only_published.json").write_text("{}", encoding="utf-8")
    assert clone_safe.staged_input("only_published.json") == str(tmp_path / "out_segmented" / "only_published.json")


def test_comeback_atlas_corpus_is_the_nba_reliability_map(monkeypatch):
    """comeback_atlas reads the NBA reliability map, never the in-game join corpus,
    so the in-game override cannot and must not move it."""
    default = _reload("comeback_atlas")._RELIABILITY_MAP
    _set(monkeypatch, "_segmented")
    overridden = _reload("comeback_atlas")._RELIABILITY_MAP
    assert str(default).replace("\\", "/").endswith(
        "data/cache/calibration_grid/nba_reliability_map.json")
    assert overridden == default
