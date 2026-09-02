from scripts.platformkit.g126_g111_label_audit import blind_sample


def test_g126_blind_sample_is_seeded_and_has_all_label_count_strata() -> None:
    rows = []
    for prefix, count, features in (("none", 20, ""), ("some", 14, "a;b"), ("four", 20, "a;b;c;d")):
        rows.extend({"clip": prefix, "source_frame": str(index), "slot": str(index),
                     "point_features": features} for index in range(count))
    selected = blind_sample(rows)
    assert len(selected) == 45
    assert len({row["audit_id"] for row in selected}) == 45
    assert len({(row["clip"], row["source_frame"]) for row in selected}) == 45
    assert sum(row["clip"] == "some" for row in selected) == 14
