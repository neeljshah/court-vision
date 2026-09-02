"""Focused additive-contract tests for tracking evidence provenance."""
import json
from pathlib import Path
from types import SimpleNamespace

from scripts.platformkit.tracking.run_environment import build_run_environment_stamp, with_run_environment
from scripts.platformkit.tracking_feature_bridge import _iter_reports


def _git(revision: str, dirty: bool):
    def run(args, **_kwargs):
        value = revision if args[1:3] == ["rev-parse", "HEAD"] else (" M writer.py" if dirty else "")
        return SimpleNamespace(returncode=0, stdout=value, stderr="")
    return run


def test_three_constructed_stamps_and_stampless_payload_remain_parseable(tmp_path):
    module = Path(__file__)
    torch = SimpleNamespace(__version__="2.test", cuda=SimpleNamespace(is_available=lambda: True))
    with_torch = with_run_environment(
        {"writer": "test"}, 7, [module],
        seed_reason=None)
    with_torch["run_environment"] = build_run_environment_stamp(
        7, [module], importer=lambda name: torch if name == "torch" else SimpleNamespace(__version__="1.test"),
        git_runner=_git("abc123", False))
    without_torch = with_run_environment({"writer": "test"}, 7, [module])
    without_torch["run_environment"] = build_run_environment_stamp(
        7, [module], importer=lambda _name: (_ for _ in ()).throw(ImportError()),
        git_runner=_git("abc123", False))
    dirty_tree = with_run_environment({"writer": "test"}, None, [module], seed_reason="no seed")
    dirty_tree["run_environment"] = build_run_environment_stamp(
        None, [module], seed_reason="no seed",
        importer=lambda name: torch if name == "torch" else SimpleNamespace(__version__="1.test"),
        git_runner=_git("def456", True))

    for artifact in (with_torch, without_torch, dirty_tree):
        stamp = artifact["run_environment"]
        assert set(("timestamp_utc", "hostname", "platform", "python_version", "cv2_version",
                    "numpy_version", "torch_version", "cuda_available", "seed", "git_revision",
                    "git_tree_dirty", "source_hashes_sha256")) <= set(stamp)
        assert stamp["source_hashes_sha256"]
    assert with_torch["run_environment"]["cuda_available"] is True
    assert without_torch["run_environment"]["torch_version"] is None
    assert without_torch["run_environment"]["cuda_available"] is None
    assert dirty_tree["run_environment"]["git_tree_dirty"] is True

    historical = {"bounds": {"x": [-6.0, 84.0]}, "matches": {}}
    assert json.loads(json.dumps(historical)) == historical
    stamped = with_run_environment(historical, 7, [module])
    assert {key: stamped[key] for key in historical} == historical
    assert "run_environment" in stamped
    report_path = tmp_path / "reports" / "tennis" / "legacy.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(json.dumps(historical), encoding="utf-8")
    assert list(_iter_reports(report_path.parents[1])) == [("tennis", "legacy", report_path)]
