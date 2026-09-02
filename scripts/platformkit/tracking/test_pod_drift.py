import subprocess

from scripts.platformkit.tracking import pod_drift


def test_drift_check_names_three_planted_sets_and_fails_soft(tmp_path, monkeypatch):
    master = {
        "domains/tennis/tracking/shared.py": "a" * 32,
        "domains/tennis/tracking/master_only.py": "b" * 32,
    }
    pod_output = "\n".join(
        [
            "c" * 32 + "  /workspace/nba-ai-system/domains/tennis/tracking/shared.py",
            "d" * 32 + "  /workspace/nba-ai-system/domains/tennis/tracking/pod_only.py",
        ]
    )
    monkeypatch.setattr(pod_drift, "master_hashes", lambda _: master)
    lines: list[str] = []
    result = pod_drift.run_drift_check(
        tmp_path,
        "example.invalid",
        "22",
        runner=lambda *args, **kwargs: subprocess.CompletedProcess(args, 0, pod_output, ""),
        emit=lines.append,
    )

    assert result == 0
    assert lines == [
        "== pod drift (tracking-number producer modules)",
        "  DIFFERS (1)",
        "    domains/tennis/tracking/shared.py",
        "  POD-ONLY (1)",
        "    domains/tennis/tracking/pod_only.py",
        "  MASTER-ONLY (1)",
        "    domains/tennis/tracking/master_only.py",
    ]

    unknown: list[str] = []
    result = pod_drift.run_drift_check(
        tmp_path,
        "example.invalid",
        "22",
        runner=lambda *args, **kwargs: (_ for _ in ()).throw(OSError("unreachable")),
        emit=unknown.append,
    )
    assert result == 0
    assert unknown == ["UNKNOWN: pod drift check unavailable"]
