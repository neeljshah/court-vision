# S198 bridge test premise - FALSIFIED
SUPERSEDED: lines 3-48 record attempt 1; the final candidate result is attempt 2.

## Scope

S198 requires a premise measurement before any implementation work: the bridge
test must fail at HEAD and pass at `15a1ad26e^`. The measurement below falsifies
that premise. Under verifier contract Q8, this is a valid closure without a
code change.

## Reproduction

All commands ran from the `track-a14` worktree, one test file at a time.

```text
python -m pytest scripts/platformkit/ingame/test_inplay_capture_bridge.py -q -p no:cacheprovider
```

| Revision | Resolved SHA | Result | Failing test |
|----------|--------------|--------|--------------|
| HEAD | `14e124e978bc409dc0d1c4132ab6842e99b1d2a2` | 1 failed, 15 passed | `test_bridge_enables_ingame_bet` |
| `15a1ad26e^` | `0b6181cf7028657e7e1aa7529841e05e11253eab` | 1 failed, 15 passed | `test_bridge_enables_ingame_bet` |

At both revisions, the asserted `n_pairs` value is 1 and `n_bets` is 0. The
test file contains 16 tests at both measured revisions.

## Bisect result

No bisect was started. The required lower endpoint is already failing, so it
cannot be marked good and does not establish a range containing a first bad
commit. Naming a first bad commit or a flipping hunk would therefore be
unsupported.

`git bisect reset` was run before this evidence edit and confirmed that no
bisect session was active.

- First bad commit: not determined; the supplied lower endpoint fails.
- Flipping hunk: not determined; no valid good-to-bad transition exists.
- Commits bisected (CONSTRUCT): 0; none.

## Limit and verifier self-check

The assertion was not weakened, skipped, deleted, or otherwise changed. No
production module, threshold, schema, reader, FWER artifact, register, or
ledger was changed. Because the S198 premise is false, no candidate fix or
breaker-specific test file can be identified from the stipulated range.

This memo is the sole S198 implementation artifact. The outcome is FALSIFIED,
not a calibration result or a behavior change.

## S198 attempt 2 - first bad commit found

### Historical sample and bisect

The test function was added by `861cc35d9a901873dd62cbb7b93599a21a4b7491`.
The chronological union of later commits that touch the capture loop,
`game_pk_bridge_live.py`, or this test contains 31 commits. The three sample
revisions are positions 8, 16, and 24 of that union. The bridge module itself
was touched by `8927ae6cc93f80974ffe3d9707e82728426cb415`,
`426e942aec534c83b96b17e923caaeeadbeb3ad8`, and
`366b10038d802836159b8674c08be5a33e6f87bf`.

All historical commands ran only:

```text
python -m pytest scripts/platformkit/ingame/test_inplay_capture_bridge.py -q -p no:cacheprovider
```

| Revision | SHA | Result |
|----------|-----|--------|
| Test added | `861cc35d9a901873dd62cbb7b93599a21a4b7491` | 4 passed |
| Sample 8 of 31 | `7e5bccbed465faf98cd82f01279eeaa9bbabd21c` | 7 passed |
| Sample 16 of 31 | `1055910559ca6b3bbd9e074f5ce8a86664d0dfee` | 7 passed |
| Sample 24 of 31 | `066cc9e37fd6126758de8c451456bc9b855010d9` | 11 passed |
| Bisect bad endpoint | `0b6181cf7028657e7e1aa7529841e05e11253eab` | 1 failed, 15 passed |
| First bad | `c1b3f435806339b8b4a146afb0a81f8ce584ca77` | 1 failed, 10 passed |

Because the sampled revisions passed and `0b6181cf` failed, the valid range
was `git bisect start 0b6181cf 066cc9e37`. The bisect executed the bridge test
file for 11 construct commits and identified:

- `4ff779286c0274116bd2c12abaf1fd0845f9be04`
- `aba62df29b0d9c460eda0db6f48c9bd3763032dc`
- `88151239a685f7cc3e1f129876ff0fd4b3c09724`
- `95d6eb4d927cd0ea8b4a6b403845af3a3b2935e9`
- `28bb4414c15cff0544a9632bc8d8bbdc83af38a4`
- `ae6859ee95884e7b3af1251605b41b49a0699de8`
- `c0a404aeb58427e75b220146efa5725757aae3c2`
- `5796533969a483864a5974bb0932c759eaa44859`
- `5e194ce2a3357ccbdc55e7c270202cf21462679b`
- `05c3fc387a4a846edc4eaad282b3e2a10ba4ee66`
- `c1b3f435806339b8b4a146afb0a81f8ce584ca77`

```text
c1b3f435806339b8b4a146afb0a81f8ce584ca77
feat(exec-gate): declared max-divergence stale-quote gate
```

`git bisect reset` completed before returning to `track-a14`.

### Flipping hunk and correction

The first bad commit adds this early return in
`scripts/platformkit/execution/ingame_exec_gate.py`:

```python
devig = ev.get("bet_devigged_price", ev.get("devigged_price"))
div = (abs(float(fair_prob) - float(devig))
       if fair_prob is not None and devig is not None else None)
g["divergence"] = round(div, 6) if div is not None else None
if div is not None and div > INGAME_MAX_DIVERGENCE:
    return {"suppress": True, "reason": "divergence_stale_quote", "exec_gate": g,
            "exec_depth": depth}
```

The old bridge fixture supplied 0.82 against a devigged price of about 0.555,
which is above the unchanged 0.15 divergence cap. That suppression leaves the
row's `bet` false, so the capture loop does not increment `n_bets` at
`inplay_capture_loop.py:729-730`.

The test fixture now supplies 0.65, below that cap. It also threads `positions`
through two bridge polls: the first correctly submits a maker quote and the
second produces the required crossed fill. The assertions remain strict:
`n_pairs == 1`, `n_bets == 1`, `bet is True`, a tier is present, and the fill
reason is exactly `maker_fill_cross`. No production threshold or breaker
behavior changed.

### Final per-file verification

```text
python -m pytest scripts/platformkit/ingame/test_inplay_capture_bridge.py -q -p no:cacheprovider
16 passed

python -m pytest tests/platformkit/ingame/test_inplay_daytrader.py -q -p no:cacheprovider
41 passed

python -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider
1 passed
```

### Contract self-check

This is a construct-only historical diagnosis and regression correction, not a
scored comparison. No threshold, schema, deployment, reader, FWER artifact,
register, or ledger changed. The evidence path exists in this commit, the test
was never skipped or deleted, and all language here is calibration-only.

## NOT VERIFIED

- Deployment was not verified.
- Live external behavior was not verified.
