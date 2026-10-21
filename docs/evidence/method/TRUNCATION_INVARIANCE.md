# Method excerpt: in-game truncation invariance

Source (private path, line range, as of 626fe42f0):
- `tests/test_ingame_leak_free.py`, lines 1-6 (docstring), 33-59
  (`test_truncation_invariance_game_rows`), 62-87 (`test_truncation_invariance_player_rows`)
- Contrast: `kernel/testing/invariants.py`, lines 46-76 (`check_truncation_invariance`; public)

The test featurizes a full game's play-by-play with `src.ingame.state_featurizer.featurize_game`,
re-featurizes only the first K events, and requires the row at the cut to match.

## The assertion lines (verbatim)

```python
_GAME_CONSTANT_FIELDS = {"home_team", "away_team", "game_remaining_sec",
                         "played_share"}

    gid, ev = _first_real_game()
    full = featurize_game(ev, gid, "AAA", "BBB", emit_players=False)["game"]
    # pick a mid-game cut
    K = len(ev) // 2
    truncated = featurize_game(ev[:K], gid, "AAA", "BBB", emit_players=False)["game"]
    assert len(truncated) == K
    last_trunc = truncated[-1]
    same_idx = full[K - 1]
    for k, v in last_trunc.items():
        if k in _GAME_CONSTANT_FIELDS:
            continue
        assert same_idx[k] == v, f"field {k} leaked future info: {same_idx[k]} != {v}"
```

The player-row test does the same at the cut event for each player present in the truncated run:

```python
        for stat in ("pts", "reb", "ast", "fg3m", "stl", "blk", "tov", "pf",
                     "fga", "fgm"):
            assert frow[stat] == trow[stat], (
                f"player {key} stat {stat} leaked: {frow[stat]} != {trow[stat]}")
```

Exempt fields: `game_remaining_sec` and `played_share` depend on total game length resolved from
the maximum period (a clock denominator), and the two team fields are game constants.

## How it differs from kernel/testing/invariants.py

`check_truncation_invariance` in the public kernel shares the name but tests a different property:
it folds the COMPLETE event log and asserts the per-side point totals equal the declared final
score (`fold_scores(...)` compared to `expected_totals`). That is an ingest-completeness check (no
dropped or double-counted scoring events). It never deletes future events, so it cannot detect a
featurizer that reads ahead. The private test above is the lookahead check.

## What it guarantees / what it does not

Guarantees: on the test game, the game-state row and the player box rows at the mid-game cut are
equal (Python `==`, field by field, minus the exempt fields) whether or not the later half of the
game is in the input. A featurizer that let a later event change that row would fail the test.

Does not guarantee: invariance at every event (one mid-game cut on one game: the first local game
that passes the `_first_real_game` length filter); byte identity of serialized rows (the docstring says
"byte-identical"; the code compares values); anything about models trained on these rows. The test
skips when no play-by-play game is available locally, so a skip is not a pass.
