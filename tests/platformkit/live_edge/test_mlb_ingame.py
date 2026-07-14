"""Per-file test for the MLB in-game grid+mine lane. Uses a small synthetic
tick frame (not the real corpus) so it stays fast and hermetic."""
import pandas as pd

from scripts.platformkit.live_edge.mlb_ingame import mlb_grid as mg
from scripts.platformkit.live_edge.mlb_ingame import mlb_mine as mm


def _toy_ticks() -> pd.DataFrame:
    rows = []
    for gp in (1, 2):
        for i, (inning, half, outs, balls, strikes, o1, o2, o3, sh, sa, bat, pit, date) in enumerate([
            (1, "Top", 0, 0, 0, False, False, False, 0, 0, 100, 900, "2026-07-01"),
            (1, "Top", 1, 0, 0, False, False, False, 0, 0, 101, 900, "2026-07-01"),
            (1, "Top", 1, 0, 0, True, False, False, 0, 1, 102, 900, "2026-07-01"),
            (1, "Bot", 0, 0, 0, False, False, False, 0, 1, 200, 950, "2026-07-01"),
        ]):
            rows.append({"game_pk": gp, "inning": inning, "half": half, "outs": outs,
                         "balls": balls, "strikes": strikes, "on_first": o1, "on_second": o2,
                         "on_third": o3, "score_home": sh, "score_away": sa, "batter_id": bat,
                         "pitcher_id": pit, "base_state": int(o1) + 2 * int(o2) + 4 * int(o3),
                         "base_label": "x", "captured_at": f"{date}T00:00:{i:02d}Z", "date": date})
    return pd.DataFrame(rows)


def test_dedupe_transitions_drops_no_repeats():
    df = _toy_ticks()
    dup = pd.concat([df.iloc[[0]], df], ignore_index=True)  # inject a repeat of the very first row
    out = mg.dedupe_transitions(dup)
    assert len(out) == len(df)  # the injected duplicate is dropped


def test_tag_situations_axes_present_and_in_game():
    df = mg.tag_situations(mg.dedupe_transitions(_toy_ticks()))
    for col in mg.GROUP_COLS:
        assert col in df.columns
    assert set(df["count_bucket"]) == {"B0S0"}
    assert df["tto"].isin(["1st", "2nd", "3rd+"]).all()


def test_split_discovery_reserve_is_trailing_by_date():
    df = _toy_ticks().copy()
    df.loc[df["game_pk"] == 2, "date"] = "2026-07-05"
    disc, res = mg.split_discovery_reserve(df)
    assert disc["date"].max() <= res["date"].min()
    assert len(disc) + len(res) == len(df)


def test_add_targets_run_scored_rest_half():
    tagged = mm.add_targets(mg.dedupe_transitions(_toy_ticks()))
    top_g1 = tagged[(tagged["game_pk"] == 1) & (tagged["half"] == "Top")]
    # away scores 0->1 within the Top half: the pre-score rows should show run_scored_rest_half=1
    assert top_g1.iloc[0]["run_scored_rest_half"] == 1.0
    assert top_g1.iloc[-1]["run_scored_rest_half"] == 0.0  # already scored, no MORE runs after


def test_run_sweep_end_to_end(tmp_path):
    base_dir = tmp_path / "claims"
    result = mm.run_sweep(base_dir=str(base_dir), ticks_source=_toy_ticks(), discovery_only=False)
    assert result["cells_screened"] > 0
    assert result["claims_added"] > 0
    assert (base_dir / "journal.jsonl").is_file()
