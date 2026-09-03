from scripts.platformkit.g130_recensus import ClipInfo, blind_rejudge_rows, stratified_draw, wilson_interval


def test_g130_stratified_draw_is_deterministic_unique_and_bounded() -> None:
    clips = [ClipInfo("b.mp4", 120, 640, 360), ClipInfo("a.mp4", 120, 640, 360)]
    rows = stratified_draw(clips, seed=13020260902, strata_per_clip=15)

    assert rows == stratified_draw(clips, seed=13020260902, strata_per_clip=15)
    assert len(rows) == 30
    assert len({(row["source_file"], row["source_frame"]) for row in rows}) == 30
    assert {(row["clip"], row["slot"]) for row in rows} == {
        (clip, slot) for clip in ("a", "b") for slot in range(15)
    }
    assert all(
        120 * int(row["slot"]) // 15 <= int(row["source_frame"]) < 120 * (int(row["slot"]) + 1) // 15
        for row in rows
    )
    lower, upper = wilson_interval(24, 24)
    assert round(lower, 6) == 0.862024
    assert upper == 1.0
    rejudge = blind_rejudge_rows(rows, seed=13020260903)
    assert rejudge == blind_rejudge_rows(rows, seed=13020260903)
    assert len(rejudge) == 6
    assert {row["audit_id"] for row in rejudge}.issubset({row["audit_id"] for row in rows})
