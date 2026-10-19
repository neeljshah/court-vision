# S666 cloud result -- 2026-09-30 (risk_delta: per-game scenario grid netted to the game outcome)

Branch `cloud/S666-2026-09-30` (base e1b3bcdc, trunk head at clone). Routine: desk-improve, ONE-OFF
OVERRIDE pinned to S666 (slate `QUANT_GRADE_BUILD_SLATE_2026-09-30.md` section 3a). Paper only;
execution-quality language only (contracts, points = contracts x cents against the mark).
No register or DESK_STATE edit on the branch; nothing landed; nothing pushed to trunk.

## Verdicts

| Tier | Who | Verdict |
|---|---|---|
| Pre-build critic | independent Opus sub-agent (codex not available in the cloud) | REVISE, 12 items, all folded as spec AMENDMENT 1 |
| CONTRACT (A/B/Q + spec + AMENDMENT 1) | independent Opus sub-agent, did not build | ACCEPT WITH CORRECTIONS (2 items, both memo items: this memo; A1.6 untested -> test added) |
| ADVERSARIAL (probes + mutants) | independent Opus sub-agent, did not build | ACCEPT (32 of 34 mutants killed; 2 survivors outside the acceptance rule, both now killed by an added test) |

Codex was NOT used. The critic and both verifier tiers were separate Opus sub-agents. None of them
wrote the build, and each read the spec and the code cold.

## Premise (Q8) and premise correction

- **Premise, re-measured.** `position_caps.check_caps` correlated scope reads 20 for YES home 10 +
  YES away 10. It sums magnitudes and never nets (`test_premise_correlated_never_nets`).
- **Premise correction: the slate's acceptance case is financially false.** The slate case is "YES
  home ML plus NO away ML nets to zero delta".
  - A NO on the away ML pays when the away side does not win, which is the same direction as YES
    home. The two positions ADD: delta +2n, and the worst cell is 2n*p with no draws.
  - The zero-delta hedge is YES home + YES away. Its worst cell is 0 exactly with marks p and
    100-p and no draws; with a draw possible it is 100n, in the draw cell.
  - The build follows the corrected case and tests the slate case as +2n.
  - Both the critic and the adversarial tier independently confirmed the correction under
    binary YES/NO payoffs.

## What was built (new files only)

- `scripts/platformkit/execution/risk_delta.py` (222 lines; pure, Decimal)
  - Public entry points: `game_risk(snapshot, game_id, leg_map, marks_cents, draws_possible)` and
    `risk_delta(...)` over the book.
  - **Inputs:** the S345 snapshot, read through `position_exposure.exposure_book` (unchanged), plus
    a caller-supplied leg map, YES-price marks and per-game draw flags. The leg map supports
    home_win, away_win, home_margin_over, away_margin_over, total_over and total_under.
  - **Grid:** at most 5 x 5 integer (margin, total) cells, made from region representatives.
    Infeasible Cartesian cells are kept, so the grid only ever overstates.
  - **Cell points:** per mapped leg, the maximum over the fill scenarios {net, net+yes, net-no} of
    k * (mark - 100 * YES).
  - **Unmapped bucket:** 100 * worst_case per unmapped leg, added to every cell and never netted.
    Its reasons are NO_LEG_MAP, GAME_MISMATCH, UNKNOWN_KIND, NO_MARK, BAD_MARK and GRID_OVERFLOW
    (an overflow sends the whole game to unmapped).
  - **Outputs:**
    - `worst_cell_points` (never clamped) and `worst_cell_at`;
    - `net_delta_home_contracts`: a direction count over filled net, not a probability delta;
    - `net_delta_home_range_contracts` {lo, hi}, which accounts for open orders;
    - `summed_caps_bound_points`.
  - S667, S669 and S670 can build on `game_risk` without editing this module.
- `tests/platformkit/execution/test_risk_delta.py` (273 lines): 26 tests.
  - Enumerated cases for bars 1-7 and AMENDMENT 1.
  - A property test over 10,000 books (`random.Random(666)`), with no book excluded. On every game
    it asserts `worst <= summed bound` and exact Decimal equality with an independent brute force
    over every integer (margin, total) in a box around all thresholds.
  - The run covered 14,965 games: 30 grid overflows, every reason code, and 8,736 games with two
    or more mapped legs.
- `docs/evidence/harness/S666_spec_2026-09-30.md`: the spec plus AMENDMENT 1.

On the old code the test file fails at import, because the module is absent.

**Unchanged (byte-identical, `git diff e1b3bcdc` confirms):** position_caps.py, position_exposure.py,
position_decimal.py, position_reducers.py, paper_account.py, quote_engine.py and paper_maker.py.
No S519-pinned or PREREG-pinned path was touched; a grep of `docs/evidence/forward/**/PREREG*.json`
found no match.

## Tests (one file per process)

| Command | Result |
|---|---|
| `python3 -m pytest tests/platformkit/execution/test_risk_delta.py -q` | 26 passed (~33 s); verifiers ran it at 25 tests, before the test-only addition below |
| `python3 -m pytest tests/platformkit/execution/test_position_caps.py -q` | 42 passed |
| `python3 -m pytest tests/platformkit/execution/test_position_exposure.py -q` | 26 passed |

## Independent reproduction

- **CONTRACT tier.** Its own brute force, written from scratch with seed 20260930, ran 2,500 books
  (4,959 games): 0 mismatches. It also hand-checked the spread hedge (cells 250 / -750 / 250) and
  the 2n*p case.
- **ADVERSARIAL tier.** Its own brute force ran 11,102 games over 2 seeds with a wider box: 0
  mismatches.
  - JSON output was byte-identical under permutation.
  - Hand probes passed: fractional quantities, marks 0 and 100, integer and quarter lines,
    negative totals lines, an empty book, open=False orders and a NaN mark.

## Corrections applied after verification (test-only; no module change)

`test_verifier_gaps_negative_worst_total_overflow_away_directions` adds four cases:
- A1.6: the worst cell is negative and not clamped (NO home + NO away at 60/60 gives -200).
- A GRID_OVERFLOW on the total axis.
- away_margin_over delta = -n; this kills surviving mutant X17.
- An away_win delta range with yes and no open orders gives {lo -10, hi 4}; this kills surviving
  mutant X5.

After the addition, both mutants were re-run in a scratch copy and turn the test red.

## NEW GAP lines from the verifiers (not fixed here)

- The property test does not check `net_delta_home_contracts` or its range against an independent
  computation.
- Bar (3) "flip to unmapped never lowers worst" is enumerated on one pair only. The CONTRACT tier
  checked it on 4,959 random games with 0 lowerings, but it is not yet part of the property loop.
- A leg_map entry that is not a dict raises AttributeError, not ValueError.
- The property generator never draws a negative totals line. The adversarial probe covered one by
  hand.
- The spec's `git diff trunk` was checked against base e1b3bcdc, because the clone's local trunk
  ref is stale.

## NOT VERIFIED

- Replay on archived paper_account receipt logs. The clone has no data/, so fixtures only.
- The real leg map for venue tickers: which Kalshi tickers are home win, spread or total. No
  mapping source exists yet; every real ticker is UNMAPPED until one is supplied.
- Real marks (the venue mid at the snapshot instant).
- The case where an open order fills at a limit price other than the mark. Loss is measured
  against the mark.
- Feasibility tightening (score parity, |margin| <= total). Infeasible cells are kept, which can
  overstate the worst cell.
- Whether alternate-line ladders on real books routinely overflow the 5-region axis. An overflow
  sends the game to fully unmapped, which is equal to check_caps today.
- Wiring. No runtime caller exists (PREPARE only); S667 wraps check_caps with this module later.

PORTABLE: yes (pure Python; the construct tests run on Ubuntu with Python 3.11).
