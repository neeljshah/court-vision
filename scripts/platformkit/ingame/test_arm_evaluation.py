from scripts.platformkit.ingame.arm_evaluation import evaluate


def test_absent_joined_features_hard_stops_every_arm():
    report = evaluate([{"game": "g", "officials": None}])
    assert report["officials_excluded"]
    assert all(arm["verdict"] == "INSUFFICIENT" for arm in report["arms"].values())
    assert all(not arm["walk_forward"] for arm in report["arms"].values())
