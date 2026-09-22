# S400 -- fee-aware PAPER sizing under calibration uncertainty (PREPARE only)

Lane: cx_s400_paper_sizing, worktree `nba-harness-h61` (branch `harness-h61`, master-based).
Binding spec: `docs/evidence/tracking/specs/S400_spec.md`. Contract:
`docs/evidence/tracking/VERIFIER_CONTRACT.md` sections B and Q. Calibration language only; no
currency figure appears anywhere in this row.

**Headline.** Under today's evidence the policy returns ZERO everywhere. The licence step refuses
every cell the harness can present: the S347 result is UNDERPOWERED in every cell, the second
corpus is unsealed, and a single-window AHEAD is unlicensed by definition. Zero is the honest
size, and the policy reaches it with a named reason rather than by clamping. The fee path is
stronger than zero: in REFUSE mode the landed gate refuses at INPUT CONSTRUCTION, before
`size_paper` is reached at all -- `conservative_fee` raises `FeeCertificationError` for a stale or
fabricated status, so no `FeeEvidence` is built and no decision object exists. On this tree the live gate is not certified
at all (the numbers are under NOT VERIFIED). The `fee_uncertified` zero is the BOUNDED branch: that
label constructs, carries no issuance, and returns zero. Since fix 1c a cell whose declared verdict
the LANDED gate contradicts is refused at construction too.

**Nothing is wired.** `scripts/platformkit/execution/sizing.py` is byte-identical to master and is
NOT IMPORTED BY ANY S400 FILE (its own landed caller, `inplay_daytrader_maker.py:19`, is not this
row's), and no caller of `size_paper` exists (`grep -rn paper_sizing --include=*.py .` returns only
the five files below). The owned set is those five plus this memo -- spec AMENDMENT 1(a).

## Q8 premise check -- re-measured before any code was written

The row rests on one fact: the only sizer in the tree is `sizing.py`, it returns a binary float,
and it knows nothing about fees, intervals, caps, family streaks or certification. Re-measured in
this worktree:

- `scripts/platformkit/execution/sizing.py:40` --
  `def stake_for(tier: Optional[str], market_type: str) -> float:` returning `2.0 / 1.5 / 1.0`
  tier units; `BASE_UNITS: float = 1.0` at line 25.
- Exactly one runtime caller, `scripts/platformkit/ingame/inplay_daytrader_maker.py:124`:
  `stake = (_sizing.stake_for(ev["tier"], "moneyline") if _sizing.tier_sizing_enabled() else 0.0)`.
- The whole-tree `stake_for` scan finds only that caller, `sizing.py` and its own test file.

**Premise HOLDS.** `sizing.py` was left untouched and its per-file test still passes (`7 passed`).

## BINDING BEFORE-CONDITION -- quoted from master

**(a) `position_caps.py:27`** -- `def check_caps(positions_snapshot, caps, *, order_id, ticker,
game_id, side, qty) -> Dict[str, Any]:` (full annotations at that line) and
`def order_permitted(report) -> bool:` (line 86). Caps shape: `{"per_order": {order_id: cap},
"per_game": {ticker: cap}, "correlated": {game_id: cap}, "global": cap}` (the four-key `limits`
literal ending at line 57). Per-scope report keys `current`, `post`, `cap`, `breached`,
`allowed_new_exposure` (lines 23-24), plus `reducing`, `permitted`, `max_permitted_qty` (lines 60,
66, 82). Its docstring at line 5 states the worst case: "Every logged open unfilled quantity
counts" -- resting orders count as exposure.

**(b) `quote_reservation.py:138`** -- `def reserve(positions_snapshot: Snapshot, caps: dict,
ticker: str, game_id: str) -> Reservation:`. `Reservation` (line 69) carries `bid_room: str` and
`ask_room: str` -- "Issuer-checked capability; sizes are immutable Decimal strings" -- each the
largest whole quantity `check_caps` permits on that side (lines 177-186), plus the private
`_snapshot` and `_caps` those rooms were computed against.

**(c) `position_decimal.py:8`** -- `def number(value: Any, field: str = "quantity") -> Decimal:`
-- "Accept finite Decimal, integer or numeric string, never binary floats."

**(d) `fee_certification_gate.py:204, 219`** -- `def require_certified(mode: str = "refuse") ->
CertificationStatus:` and `def conservative_fee(module_fee: object, status: CertificationStatus)
-> Decimal:`. `CertificationStatus` (line 64) carries `certified`, `checks_total`,
`mismatches_total`, `fee_module_sha256`, `fixture_set_sha256`, `undercharge_bound_per_order`,
`label`. `conservative_fee` refuses a positive-fee violation ("module fee must be positive", line
235) and a status whose `fee_module_sha256` no longer matches the loaded module ("stale
certification status", line 226).

**(e) `family_week_ledger.py:18, 164`** -- `TARGET_WEEKS = 8` and `def streak(self, family: str)
-> int:` -- "Count qualifying weeks ending at the latest completed UTC ISO week."

**(f) `baseline_four_arm.py:177-182`** (top-level `n_games` at :151) -- the summary cell schema: `point`, `ci95: [lo, hi]`,
`verdict`, `leave_one_game_out_range`, `largest_absolute_share`, `concentration_pass` (true only
when the largest game share is at most one half), `n_games` carried as the cell's own `ng`; an
`AHEAD` is rewritten to `SINGLE-WINDOW` at lines 174-176. `gate_a0_ingame_vs_market.py:84`, with
`N_MIN_GAMES = 30` at line 24:

```
def verdict(lo, hi, n_games, n_min=N_MIN_GAMES):
    if n_games < n_min or (lo <= 0 <= hi):
        return 'UNDERPOWERED'
    return 'BEHIND' if lo > 0 else 'AHEAD'
```

Both are IMPORTED by this row, never restated: an AHEAD interval lies strictly below zero.

**(g) `venue_fees.py:122`** -- `def fee_kalshi_maker(contracts: float, price: float) -> float:` --
"Total Kalshi MAKER fee in [unit elided] for *contracts* ... at *price*." (The unit word is elided
under the Q6 rail; the line is otherwise verbatim.) It returns the WHOLE order's fee, not a
per-contract fee (lesson S345), so S400 takes the per-contract number as the whole-order fee for
exactly one contract, and only through `conservative_fee`, which ceilings it to a cent.

**(h) `quote_engine.py:86`** -- `def make_quotes(...)`. Quantity inputs are
`caps['max_order_qty']` (a strict count via `_count`, line 49), `caps['max_position']` (a Decimal
via `number`, line 129) and the three external rooms `game_room / correlated_room / global_room`
per side (lines 148-150); the emitted `qty` is `min(active)` with the comment "Never increase size
to change fee rounding" (line 162), serialized as a Decimal string (line 175).

## What landed

| file | lines | sha256 |
|---|---|---|
| `scripts/platformkit/execution/paper_sizing_validate.py` | 128 | `1d3bd7fcde802c338ef987f4bbcaa889a0806c8af1eced42c92084beb4d5c05f` |
| `scripts/platformkit/execution/paper_sizing_inputs.py` | 233 | `33c43e8d58c50faa27a91fefd1a1bedcfff2427bf8b42196dbba002c65da5a60` |
| `scripts/platformkit/execution/paper_sizing_policy.py` | 205 | `ec4b82e607a46dbb15e7f98701aacbb131b269aed4ee2731cd4c7b750390c62f` |
| `tests/platformkit/execution/test_paper_sizing_policy.py` | 299 | `506fc52e9582d2c1e380d14be2997663abb9555a524236a323d5d24590401053` |
| `tests/platformkit/execution/test_paper_sizing_inputs.py` | 161 | `f33febdd411a5b7ce0e450c9483606575eb2865d7f409912882296bddd756cc1` |

`paper_sizing_validate.py` holds the counted-refusal type, the closed REFUSAL_REASONS vocabulary
(20 entries) and the scalar / JSON validators. `paper_sizing_inputs.py` holds the frozen evidence
dataclasses (`CalibrationEvidence`, `FeeEvidence`, `FamilyEvidence`, `Quote`, `Rooms`). Every
constructor raises `PaperSizingInputError` with `refusal_count = 1` for: binary floats (through
the landed `position_decimal.number`), non-finite values, absurd-but-finite magnitudes,
probabilities outside the open interval between zero and one, prices outside 1..99 cents, a count
that is not a strict `int` (bool, float and numeric strings refused), duplicate corpus seals, more
seals than corpora and an inverted interval -- never a silent merge. Nested `positions_snapshot`
and `caps` payloads are validated leaf by leaf through every mapping and list; any other container,
any non-text mapping key and a container that will not iterate (`sealed_prereg_sha256=None`, a
counted `wrong_input_type`) is refused rather than converted, never a raw `TypeError`.

`paper_sizing_policy.py` holds `size_paper(quote, calibration, fees, family, rooms, params) ->
SizingDecision` plus `SizingParams` and the two DECLARED constants it defaults to
(`kelly_fraction 0.25`, `width_reference 0.02`), which live with the policy that reads them.
`size_paper` is pure: no file, no clock, no network, no randomness, no global state. The decision
carries `quantity` and `fraction_used` as Decimal strings plus a fixed-order audit trail of
thirteen intermediates, each an exact Decimal string. `fraction_used` is the fraction of
`paper_bankroll_units` the LANDED quantity commits; the pre-room fraction stays in the trail as
`fraction_after_uncertainty`, and `p_market_mid` reaches neither the size nor the trail.

## The arithmetic, in the spec's order

| step | rule | zero reason |
|---|---|---|
| (i) LICENCE | verdict AHEAD, corpus_count at least 2, one sealed prereg per corpus | `verdict_not_licensed` |
| (i) LICENCE | the streak's family is the licensing cell's OWN family | `family_mismatch` |
| (i) LICENCE | family streak at least `TARGET_WEEKS` | `family_streak_short` |
| (i) LICENCE | fee status certified in refuse mode, and ISSUED by `from_status` (BOUNDED does not qualify) | `fee_uncertified` |
| (ii) EXPECTATION | `(p_side - c_net) / (1 - c_net)`, `c_net = price_cents/100 + per-contract fee`, `p_side = p_model` for YES and `1 - p_model` for NO | `no_positive_expectation` |
| (iii) FRACTIONAL | times `params.kelly_fraction`, declared `0.25` | `no_positive_expectation` |
| (iv) UNCERTAINTY | times `max(0, 1 - width / width_reference)`, width from the licensing interval | `uncertainty_exhausted` |
| (v) CONCENTRATION | the cell's `concentration_pass` must be true | `concentration_fail` |
| (vi) ROOM | `floor(fraction * paper_bankroll_units / c_net)`, then the minimum with the reservation room for that side and with `check_caps`' `max_permitted_qty` | `below_one_contract`, `room_exhausted` |

Properties the tests hold the policy to:

- A declared verdict must agree with the LANDED gate on the cell's own interval and `n_games` at
  the landed `n_min`, or the cell never constructs.
- The point estimate is never read by the arithmetic: two cells differing only in `point` give an
  identical decision.
- The uncertainty multiplier is DECREASING by construction. Quantity is non-increasing over a
  26-point width grid (`ci_hi` fixed strictly below zero, `ci_lo` decreasing) and reaches zero at
  the declared reference width, which the test asserts exactly.
- The caps are consulted PROSPECTIVELY on the snapshot with the candidate quantity itself, before
  anything is sent, never after the fact.
- Whole contracts only. A candidate below one contract is zero with `below_one_contract`, never
  rounded up, and the final minimum against both rooms floors (`ROUND_FLOOR`): a fractional
  `max_permitted_qty` of `3.5` gives `3`, never `4` (asserted against a stub as well).
- The quoted side is priced against its OWN probability: a NO contract at 40 cents with
  `p_model 0.60` is zero with `no_positive_expectation`, while that quote's YES side sizes 80.
- Licence reasons are emitted in a declared order; reversing the argument mapping, the caps key
  order and the snapshot key order all leave the decision byte-identical (both dictionaries
  canonicalize with sorted keys).
- A fee of zero, a negative fee, NaN and infinity are counted refusals; a `CertificationStatus`
  with a stale `fee_module_sha256`, or a label whose embedded sha disagrees with the field, too.
The unit throughout is `paper_bankroll_units`. `width_reference` (`0.02`) and `kelly_fraction`
(`0.25`) are DECLARED constants stated in the policy module, not measured or tuned numbers.

## Why the answer is zero today

The spec's own licensing case is the S347 all_tick overall `B_brier` cell, quoted in the test as
literals from `S400_spec.md:47-48`:

```
point -0.003363, ci95 [-0.010776, +0.004000], UNDERPOWERED, n_games 135
```

The first test feeds those literals to the landed `gate_a0_ingame_vs_market.verdict`, which
reproduces `UNDERPOWERED` from the quoted interval, then through `size_paper`, which returns
`quantity "0"`, `fraction_used "0"` and `reasons ("verdict_not_licensed",)`. No result file is
opened: the cell reaches the test only as literals. The licence is conjunctive, so one failing
condition is enough; every S347 cell fails it, and so does a SINGLE-WINDOW by definition.

## Tests

```
python -m pytest tests/platformkit/execution/test_paper_sizing_policy.py -q -p no:cacheprovider
51 passed in 0.76s
python -m pytest tests/platformkit/execution/test_paper_sizing_inputs.py -q -p no:cacheprovider
22 passed in 0.65s
python -m pytest tests/platformkit/execution/test_sizing.py -q -p no:cacheprovider
7 passed in 0.47s
```

CONSTRUCT only: the whole decision set of reasons is enumerated (Q7 applies, `n = 73 (CONSTRUCT)`),
so the sampling rail does not bind. No module here has a CLI, so no `--help` surface exists to run.

## FIX 1b -- corrections applied after verifier round 1

Round 1 returned ACCEPT WITH CORRECTIONS (Opus) and a REJECT with four blocking findings (codex
gpt-5.6-sol). Both lists were applied; everything the verifiers confirmed was kept.

| # | finding | before | after |
|---|---|---|---|
| 1 | `_licence` never joined `calibration.family` to `family.family` | an `nba_ingame` cell with an `mlb_totals` streak of 8 sized 80 | closed reason `family_mismatch`, quantity `0` |
| 2 | the final `min(...).quantize(ONE)` used ROUND_HALF_EVEN | a stubbed `max_permitted_qty` of `3.5` gave quantity `4` | `rounding=ROUND_FLOOR`, quantity `3`; the landed caps path (cap `3.5`) also gives `3` |
| 3 | `fraction_used` was the PRE-room fraction | caps 25 of a candidate 80: `fraction_used 0.0400`, overstating what landed | `fraction_used 0.0125`; the pre-room number stays as `fraction_after_uncertainty 0.0400` |
| 4 | the NO side used the YES probability unchanged | side `yes` and side `no` at `p_model 0.60`, price 40, both sized | `Quote.p_side()`: `1 - p_model` for NO; the NO quote is zero with `no_positive_expectation` |
| 5 | a CERTIFIED label was forgeable | `FeeEvidence('CERTIFIED ...', '0'*64, '0.10')` was accepted as certified and sized | counted refusal at construction; certification carried an issuance marker |
| 6 | nested snapshot / caps numerics were unvalidated | `Rooms(..., caps={'global': 'NaN'})` was accepted | counted refusal `not_decimal`; `1e400` is `outside_finite_domain` |
| 7 | a malformed container raised an uncounted `TypeError` | `sealed_prereg_sha256=None` -> `TypeError` | counted refusal `wrong_input_type`, same for `order_ids=None` |

Two documentation corrections travelled with them (the REFUSE-mode fee path refuses at input
construction; `Quote`'s docstring states the price is the quoted side's own), and for the 300-line
rail `SizingParams` and its two DECLARED constants moved to `paper_sizing_policy.py`.

## FIX 1c -- corrections applied after verifier round 2

Round 2 returned ACCEPT WITH CORRECTIONS (Opus: one CORRECTION, two NOTEs) and a REJECT with two
blocking findings (codex gpt-5.6-sol). All five are applied below; everything the verifiers
confirmed is kept unchanged (the width-grid monotonicity, the `c_net >= 1` guard, the prospective
caps, `ROUND_FLOOR`, the family join and Q6 cleanliness). Every before-line was re-measured on this
tree before the edit and every after-line after it.

| # | finding | before (measured) | after (measured) |
|---|---|---|---|
| 1 | CORRECTION `paper_sizing_inputs.py:142-161` -- the declared verdict was never cross-checked against the landed gate; the licensed fixture declared AHEAD on an interval STRADDLING zero (`ci_lo -0.001`, `ci_hi 0.003`, `n_games 200`) | the cell constructed, `licensed() True`, `size_paper -> 80 ('sized',)`, while `verdict(-0.001, 0.003, 200)` says `UNDERPOWERED` | `__post_init__` imports the landed `verdict` and `N_MIN_GAMES` and refuses any disagreement: counted `verdict_inconsistent` (`refusal_count 1`). Every size-positive fixture moved strictly below zero (`ci_lo -0.005`, `ci_hi -0.001`, width unchanged at `0.004`, so the hand computation still lands 80) and the width grid now sweeps `ci_lo` DOWNWARD with `ci_hi` fixed at `-0.001` |
| 2 | NOTE `:29,177-199` -- `_ISSUED` was importable and was the fourth constructor field, so `FeeEvidence(LABEL, SHA, fee, _ISSUED)` forged certification | that call returned `certified True` and sized `80` | the marker is no longer a field: `FeeEvidence.__init__` takes three arguments and that call raises `TypeError`; `from_status` sets it with `object.__setattr__`. A direct `CERTIFIED ...` construction is `certified False` and sizes `0 ('fee_uncertified',)`; `from_status` still issues (`certified True`, sizes `80`) |
| 3 | NOTE `:293-300` -- `from_reservation` ignored `reservation._caps` / `_snapshot` | rooms `2 / 10`, computed by `reserve()` against `{"global":"10"}`, were stored beside the CALLER's caps `{"global":10000,"per_game":{"T":10000}}` and the caller's snapshot | both payloads now come from the reservation itself, and a caller payload that disagrees is a counted `caps_mismatch` (asserted for a different caps dict and for a moved snapshot) |
| 4 | BLOCKING `:94` -- nested TUPLES bypassed the float walk | `Rooms(..., caps={'unused': (1.5,)})` was ACCEPTED and canonicalized to `{"unused":[1.5]}` | the walk recurses through every mapping and sequence and refuses an unsupported leaf type: `(1.5,)`, `[[1.5]]`, `{'deep': (1.5,)}`, `{1.5}` and `b'x'` are each a counted `not_decimal`, in `caps` and in `positions_snapshot`; a valid `('10',)` still canonicalizes to `["10"]` |
| 5 | BLOCKING -- the memo was 354 lines and did not end with NOT VERIFIED (FIX 1b was appended after it at line 324) | 354 lines, NOT VERIFIED at lines 274-320 | both FIX sections precede NOT VERIFIED, which is last; condensed by tightening prose only -- no number, quote, sha or line reference was dropped |

Two structural notes. (a) `paper_sizing_inputs.py` was AT the 300-line rail, so the counted-refusal
type, the closed vocabulary and the scalar / JSON validators moved to a new companion module
`paper_sizing_validate.py` (only `_no_floats` changed in the move, finding 4); (b) the policy test
file was at 299 lines, so the new construction-level tests went to `test_paper_sizing_inputs.py`.
The closed vocabulary is now 20 entries: `verdict_inconsistent` and `caps_mismatch` were added and
`not_issued` was RETIRED, because the refusal it modelled is structurally impossible once the
marker is unreachable from the constructor -- a direct CERTIFIED label is never certified.

## FIX 1d -- corrections applied after verifier round 3

Round 3: ACCEPT WITH CORRECTIONS (Opus, on the memo line citations only) and a REJECT with two blocking findings (codex gpt-5.6-sol); all three are applied below and nothing the verifiers confirmed changed.

| # | finding | before (measured) | after (measured) |
|---|---|---|---|
| 1 | BLOCKING `paper_sizing_inputs.py:73` -- a declared verdict only had to be IN an allowed set, so SINGLE-WINDOW passed on ANY landed AHEAD | interval `[-0.005, -0.001]`, `n_games 200`, `corpus_count 2` declared `SINGLE-WINDOW` constructed, although the landed `verdict` gives `AHEAD` | the declared verdict must EQUAL the landed one, with a single exception: the landed one-corpus rewrite (`baseline_four_arm.py:174-176`). SINGLE-WINDOW is accepted only when the landed verdict is AHEAD and `corpus_count == 1`, and it still sizes `0 ('verdict_not_licensed',)`; two corpora, or any other disagreement, is a counted `verdict_inconsistent` |
| 2 | BLOCKING `paper_sizing_validate.py:94` -- the walk CONVERTED containers and stringified keys | `caps {'u': ('10',)}` was accepted as `{"u":["10"]}`, `{'u': [('10',)]}` as `{"u":[["10"]]}`, `{1.5: '10'}` as `{"1.5":"10"}` and `{'u': {2: '10'}}` as `{"u":{"2":"10"}}` | a mapping and a list are the ONLY containers: a tuple, set, bytes or any other container is a counted `not_decimal` even when its contents look valid, and every mapping key must be text (a float, bool, int or container key is refused before anything is copied). All four payloads above are now counted refusals, in `caps` and in `positions_snapshot` |
| 3 | CORRECTION -- the BINDING BEFORE-CONDITION line citations had drifted | `order_permitted` 82, caps shape 53-56, report keys 23 and 61/66/79, `reserve` 135, `Reservation` 68, rooms 172-181, `require_certified` 206, `conservative_fee` 222, `CertificationStatus` 63, "module fee must be positive" 245, "stale certification status" 232, the AHEAD rewrite 175-177, `BASE_UNITS` 26, `quote_engine` 86 | re-grepped to 86, the `limits` literal ending at 57, 23-24 and 60/66/82, 138, 69, 177-186, 204, 219, 64, 235, 226, 174-176, 25, 84 (`def make_quotes`); every other citation was re-checked and is unchanged. The caps-shape range is given in words because its first line number is a banned bare integer under the Q6 rail |

FIX 1e (round 4, Opus ACCEPT WITH CORRECTIONS): the owned set is the six files above (spec AMENDMENT 1a); `p_market_mid`'s "audit only" comment was wrong and now states it is never read, pinned by a test that the sized quantity and the whole trail are unchanged when it moves; the four remaining notes are recorded in NOT VERIFIED below.

## NOT VERIFIED

Everything below is honestly outside what any test in this row exercised.

- **No real evidence was read.** No ledger, result file, archive, capture, parquet or network call
  was touched, by the builder or by any test; the S347 cell is only the literals quoted in the spec.
- **The verdict cross-check is a CONSISTENCY check, not a measurement.** It re-derives the verdict
  from the cell's own quoted interval and `n_games` through the landed gate; it does not re-run the
  bootstrap or re-read the result file, so a wrong interval with a matching label still constructs.
- **The licence is a DECLARATION.** `sealed_prereg_sha256` values are checked for format (64 hex)
  and distinctness only; nothing resolves a seal to a preregistration artifact, so `licensed()`
  turns on any two distinct well-formed digests. Resolution is the S395 auditor's job.
- **The landed `order_permitted` is never called.** The policy reads `max_permitted_qty`
  (`position_caps.py:82`); round 4 measured the two equivalent over a 336-book sweep, not re-run here.
- **The nested validator allocates a discarded partial copy before refusing.** The walk builds
  child entries as it descends, so a deep refusal throws away work; the refusal is raised before
  any copy is returned.
- **`paper_sizing_inputs.py:228-229` reads a private surface.** `Reservation._snapshot.payload`
  and `Reservation._caps` are read-only reads of another module's private fields; nothing is
  written there, and no landed behaviour depends on this row.
- **The SINGLE-WINDOW acceptance is quoted, not re-run.** That a landed AHEAD is rewritten to
  SINGLE-WINDOW for one corpus is read from `baseline_four_arm.py:174-176`, never executed here.
- **The fee certification IS run, and it does not certify.** The tests call the landed `certify()`
  (and `require_certified("bounded")`) to take the LOADED fee module's identity. Measured here:
  `checks_total 39, mismatches_total 4`, both mismatch classes inside the two documented ones, and
  `require_certified("refuse")` raises. The licensed construct case flips that identity-current
  status to `certified=True` with `dataclasses.replace` and says so; the fixture comparison behind
  it was NOT re-run, and this row asserts nothing about whether the live module should certify.
- **The landed gate's own trust boundary is not closed by this row.** `conservative_fee` accepts
  any `CertificationStatus` whose module and fixture shas match the loaded files without re-running
  the fixture comparison; a hand-built status carrying the current identity is still accepted there
  -- that module's boundary, not this one's.
- **`venue_fees.fee_kalshi_maker` is never called.** The per-contract fee enters the tests as a
  literal Decimal string; the whole-order claim is quoted from its docstring, not re-measured.
- **The family streak was never read.** `FamilyWeekLedger.streak` is not called; `FamilyEvidence`
  takes the count as a strict int. Only the bar is bound to the landed `TARGET_WEEKS`, and a
  required count below that bar is refused so the bar cannot be lowered from the outside.
- **`concentration_pass` for the S347 cell is not quoted by the spec.** The fixture uses the
  refusing value and says so inline; the verdict decides the outcome first, so the fixture's choice
  does not affect the result.
- **Monotonicity is empirical over a grid**, not proved analytically over all inputs. The grid
  holds `ci_hi` fixed and sweeps 26 widths on one licensed construct case.
- **The caps / snapshot agreement check is textual.** `from_reservation` compares canonicalized
  payloads; it neither re-runs `check_caps` nor consults the reservation TTL or issuance ledger.
- **No runtime activation.** `size_paper` has zero callers; nothing measures the policy against a
  live book, a TTL or a venue; the one reservation is an in-process ledger with an injected clock.
- **No forward or prospective claim.** This row measures nothing about the market and asserts
  nothing about future sizes. It only shows that the honest size under present evidence is zero,
  with a named reason.
- **Not covered:** concurrency (the policy is pure but untested under threads), a very large
  `paper_bankroll_units` near the finite domain bound, and BOUNDED beyond its refusal at the licence.
