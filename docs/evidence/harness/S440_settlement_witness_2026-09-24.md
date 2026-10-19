# S440 settlement witness census

Candidate built; independent verification pending. Local construct tests only.
Before: module absent. Bar = 12 / 12; n = 12 (CONSTRUCT).
Observed: all 12 enumerated cases pass; 60 pytest instances pass.
No real-day measurement was performed.

## Binding before-condition

Executed before coding: AST inspection of the complete capture envelope, source
assertions for all five premises, complete served-schedule identity validation,
and comparison of the six protected sources against master. Result: PASS
(a)-(e), static source and complete served schedule schema; module absent at
that time; no archive opened; actual real-day counts NOT MEASURED. No supplied
witness implies all games unresolved. The six protected sources' hashes are
recomputed in the current A9 table below and confirmed byte-identical to
master after every fix (`git diff --quiet master -- <path>`).

These checks establish the normalized capture fields, not the absence of
arbitrary fields inside untouched raw provider payloads. No raw payload result
is trusted. No protected source was edited at any point in this lane.

## Landed dependencies read before coding

Exact signatures relied on:
- coherence_scanner_inputs.py: `def timestamp(value: Any) -> Decimal:`
- venue_time.py: `def parse_venue_time(value: object) -> float | None:`
- cross_venue_link.py: `def text(value: object) -> str:`, `def label_code(sport, label, codes):`
- cross_venue_pairs.py: `def strict_counts(counts: Counter) -> dict:`
- cross_venue_pairs.py: `def atomic_write(path: str, body: str) -> None:`
- cross_venue_pairs.py: `FINAL = _MLB_STATUS["Final"]`.
- game_market_link.py: `def alias(sport, abbr):`, `def team_code_from_ticker(ticker):`
- tennis_ticker_match.py: `def parse_tennis_ticker(ticker):`, `def surname_codes(name):`
The imported modules were read before coding. timestamp delegates validation to
parse_venue_time and reconstructs fractional seconds as Decimal. Receipts here
must be zoned ISO strings. The writer flushes and fsyncs a sibling temporary
file before atomic replacement. No pre-existing module was changed.
The distinct module name settlement_witness was kept as asked; it is never
imported as the existing function of that name.

## Input and output contract

Shards: books-root/sport/date.jsonl and state-root/sport/date.jsonl, streamed
line by line. Book receipts use response_end_ts; state receipts use
response_end_utc. All selected served identities appear, including missing
shards, zero-row games, and duplicate schedule identities. Duplicate schedule
identities remain visible but cannot be witnessed.
Each source record includes absolute path, bytes, SHA-256, read-complete and
opened flags; resolution is not_applicable. A missing path has null SHA-256.
Unreadable schedules fail explicitly rather than certifying an empty result.

The optional owner table retains entries, sport, both rule digests and winner.
A usable entry additionally requires game_key, game_id, ticker and
response_end_utc. Rule-only legacy entries cannot establish a game-specific
receipt and are counted as settlement_witness_refusals. The Kalshi rule digest
must equal the captured raw_market.rules_primary digest, read from the latest
row whose record_type is snapshot or snapshot_bulk (a trade row carries no
raw_market). The other digest is owner-declared; this census does not
establish cross-provider equivalence. A declared winner resolves via
label_code: a word of the label, or its first three letters, must alias to
exactly one of the two resolved codes (team codes for team sports, the
surname codes for tennis) or the literal string "tie" -- never a raw string
equality against a feed identity, and never a guess when more than one code
matches.
The schedule's exact event/ticker identity and the ticker's YES-side suffix
resolve orientation, via the landed game_market_link aliases for team sports
and, for tennis, the landed parse_tennis_ticker()/surname_codes() surname-code
split of the ticker's raw tail against the two full player names on the state
row (exactly one consistent split, else orientation_unresolved); no team-name
or player-name string similarity is used either way.
An unusable declaration is settlement_unverified and witnessed=false.
settlement_witness_final_absent/_final_unresolved fire only when the witness
entry carries an explicitly declared, non-empty string winner; otherwise a
missing/empty/non-string winner is settlement_witness_winner_unresolved only.
A contradictory declared winner is mismatch, counted with the landed
settlement_witness_contradicts_final reason, and cannot make the day gradable.
No supplied table gives the expected all-unwitnessed result.

As-of filtering precedes deduplication and row-content validation. Future rows
are counted and skipped. CLI --as-of supports reproducible boundary checks.
Absent that option, current UTC is the query instant and is not serialized.
Per-key selection uses the maximum parsed receipt among rows that already
passed identity, http/lifecycle-status and (for a terminal row) score and
feed-identity validation -- a bad row never touches seen/previous/latest/
terminal bookkeeping, so it can never falsely age out or duplicate-suppress a
later valid receipt. The duplicate-receipt key for book rows includes
record_type and trade_id (distinct trades sharing one instant are both kept).
A conflict at the exact same key AND the exact same instant keeps whichever
copy is read FIRST and therefore DEPENDS ON FILE ORDER -- this is never
input-order independent; distinct-instant "latest" selection is unaffected by
order since the maximum instant wins regardless of read order.

Feed scores are strict nonnegative ints bounded at 1000, a conservative
report-only refusal guard. Missing scores are never zero. MLB score_home/away,
home_score/away, and identity-aligned tennis players' sets_won are supported.
Normalized final shares the landed token. Only the literal ESPN "postponed"
token reaches the void path on real shards; CANCELED/WALKOVER/RETIRED are
normalized to "final" before this module sees them and do NOT reach void --
retaining the provider's own status token for that case is a NEW GAP deferred
to a later row; the capture source lives under scripts/platformkit and is
buildable there.

Outcome completeness counts witnessed final agreements over all served games.
Markout completeness counts venue receipt endpoint reach, independently.
--post-final-window-s declares a positive Decimal window of at most one day.
Without an explicit window, games_covered=0 and window_s=null; no duration is
invented. Every game names its last observed receipt and venue post-final span.
Endpoint reach does not prove continuous sampling or an observation exactly at
the requested endpoint. week_gradable is this served day's report-only check;
week_scope explicitly says other days are not certified. Nothing is written
to the existing weekly producer or its ledger schema.

## Construct evidence and reproduction

The first test consumes the first committed served schedule entry verbatim
through schedule JSON, synthetic shard JSONL, witness JSON and the census.
All feed/book/declaration records are constructs. No REAL ROW of a captured
shard was supplied in the spec; no captured shard was opened.

| Case | Check | Result |
| --- | --- | --- |
| 1 | Matching declared winner, real schedule identity fixture | PASS |
| 2 | Contradictory winner, exact refusal reason | PASS |
| 3 | No owner witness, unresolved and unwitnessed | PASS |
| 4 | No feed final, absent final status | PASS |
| 5 | Strictly later witness, exact nanosecond lag | PASS |
| 6 | Duplicate book and state receipt, first retained | PASS |
| 7 | Out-of-order receipt refused, maximum stable in both orders | PASS |
| 8 | Missing shard, served game retained | PASS |
| 9 | Existing shard with no rows, day not gradable | PASS |
| 10 | CLI reruns byte-identical, sorted ASCII JSON and int counters | PASS |
| 11 | Cancelled/postponed, void | PASS |
| 12 | Unresolved YES orientation, counted | PASS |

Additional instances cover malformed/nonfinite/absurd scores, future content
before validation, naive and invalid times, witness permutations and duplicates,
multiple served identities, raw cancellation, away-side orientation, schedule
duplicates, rule mismatch, legacy table refusal, bounded windows, exact counts
above the binary-float integer boundary, interrupted atomic replacement, trade
dedup fit, order-independent invalid-row handling, bad-score/bad-identity
final rows refused pre-bookkeeping in both file-order permutations, and a
tennis full-name identity resolved through the surname-code split. The CLI
reproduction test calls main twice with the same fixture arguments and diffs
every output byte; it also recomputes source sizes and hashes in case 1.

Commands:
```text
python -m pytest tests/platformkit/execution/test_settlement_witness.py -q -p no:cacheprovider
python -m pytest tests/platformkit/execution/test_settlement_witness_1b.py -q -p no:cacheprovider
python -m scripts.platformkit.execution.settlement_witness --help
python -m scripts.platformkit.tracking.contract_preflight --base master --spec docs/evidence/tracking/specs/S440_spec.md --paths scripts/platformkit/execution/settlement_witness.py scripts/platformkit/execution/settlement_witness_orient.py tests/platformkit/execution/test_settlement_witness.py tests/platformkit/execution/test_settlement_witness_1b.py docs/evidence/harness/S440_settlement_witness_2026-09-24.md
```

## Real-day state

Real-day counts: NOT MEASURED, as the lane is construct-only. In the prescribed
orchestrator run without --settlement-witness, every served game is expected
to be settlement_unverified, agreement=unresolved, witnessed=false and
week_gradable=false, except any observed cancellation is explicitly void.
This expectation is not a claim that the real run occurred.

## Self-check

A9: runtime input manifests and source hashes. B1/B9: all served denominators
retained. B2/B6: additive module with no existing callers changed. B3/B4:
missing evidence remains visible; no claim/recovery loop. B5: local only.
B7/B8/B11 and Q7: enumerated constructs with byte reproduction, no sampling.
B10/Q3: protected sources unchanged; 12 / 12 bar unchanged.
Q1/Q2/Q4/Q5/Q9: no scored comparison, promotion, trial or paired-loss claim.
Q6: contract preflight required. S1: local CPU fixtures. S2: premise above.
S4: only this report's games, counts, outcome_completeness and
markout_completeness fields; no weekly schema change.

## Fix history

- FIX 1b (2026-09-24, AMENDMENTS 1-2, round 1 codex sol REJECT applied): rule
  row read from the latest snapshot/snapshot_bulk row only; duplicate-receipt
  key extended with record_type/trade_id; witness duplicates keep the first
  accepted copy (never nulled); orientation moved onto the landed
  game_market_link aliases/label_code instead of a bare string compare;
  final_absent/_final_unresolved gated on a real declared winner; row
  validation (http/lifecycle/terminal) moved before dedup/order bookkeeping.
- FIX 1c (2026-09-24, AMENDMENT 3, round 2 codex sol REJECT applied): terminal
  scores validated before any bookkeeping (bad-score final rows refused
  pre-bookkeeping in both file-order permutations); final-absence counters
  additionally require an explicitly declared non-empty string winner; the
  orientation block extracted verbatim into settlement_witness_orient.py to
  hold settlement_witness.py under 300 LOC.
- FIX 1d (2026-09-24, AMENDMENT 4, round 3 codex sol REJECT applied): feed
  identity (home/away aliases plus YES-side suffix) validated together with
  the scores, before any bookkeeping, via the served identity passed into
  `_scan`; `identity()`/`_codes()` factored out of `orientation()` for reuse
  pre-bookkeeping.
- FIX 1e (2026-09-24, AMENDMENT 5, round 4 codex sol REJECT applied): tennis
  branch added to identity()/orientation() -- see "Tennis identity" below;
  this memo corrected for file-order dependence and trimmed under 300 lines.
- FIX 1f (2026-09-24, AMENDMENT 6, round 5 codex sol REJECT applied): see
  "FIX 1f (AMENDMENT 6)" below.

## Tennis identity (AMENDMENT 5(a))

identity()/orientation() now branch on game["sport"] == "tennis": the new
`_tennis_codes()` helper in settlement_witness_orient.py resolves the state
row's two full player names (surname_codes()) against the ticker's raw tail
(parse_tennis_ticker()) by searching every 2-4 char split of the tail for
exactly one split consistent with (one name's candidate code, the other
name's candidate code); zero or more than one consistent split is
orientation_unresolved, never guessed. The MLB/team-sport alias path
(`_codes()`) is untouched and still runs for every non-tennis sport. A
full-name regression (ticker KXATPMATCH-26SEP22BARILA-BAR, players "Marcelo
Barrios Vera" / "Ilay A", tail "BARILA" splitting uniquely at "BAR"/"ILA")
passes the terminal instead of being refused, and its declared winner "BAR"
resolves and agrees with the state row's sets_won, agreement=match.
Real tennis capture end-to-end remains unexercised (construct-only, as below).

## Current A9 identities (this tree, base sha `dec6b6b85`; resolution not_applicable)

```json
{"bytes": 15760, "path": "scripts/platformkit/execution/settlement_witness.py", "sha256": "b824c8f28de7204042a05cef00f5ae723f32b683623a9a01a41ac2148b8b80e5"}
{"bytes": 3903, "path": "scripts/platformkit/execution/settlement_witness_orient.py", "sha256": "dbb522bc621a34b2d859e47c598b547d1564d9a4bb3beee3745c9d86a3e5d0da"}
{"bytes": 12885, "path": "tests/platformkit/execution/test_settlement_witness.py", "sha256": "79204d94d2fd287880388ae14d49de1588d2d39ed30d486b77f51c4b3d13e54e"}
{"bytes": 15214, "path": "tests/platformkit/execution/test_settlement_witness_1b.py", "sha256": "cb84addc212dafd3204953c2e99470fb116e999361d9bd845691cb28d76a8587"}
{"bytes": 16530, "path": "docs/evidence/tracking/specs/S440_spec.md", "sha256": "a7fd63e1e052e6782e99e276768063c50e169c4dc7a6403263cfd1ca31992134"}
{"bytes": 14985, "path": "scripts/platformkit/execution/cross_venue_link.py", "sha256": "9a56eb1d84184e906f8c6178049bc1bf4ed98060f4be3afff3d1f1a6cac377bf"}
{"bytes": 17501, "path": "scripts/platformkit/execution/cross_venue_pairs.py", "sha256": "7f240260727ecaeba1d7e49a715a2ef2ba97cc6d0e291fe5c580cc22da7351c1"}
{"bytes": 20512, "path": "scripts/platformkit/ingame/local_state_capture_sources.py", "sha256": "70aac0623c242073fed60c48b9894e234c691bde3e20cfda3bd82e36c690062e"}
{"bytes": 13537, "path": "domains/nfl/ingest_nfl_states.py", "sha256": "a9d5a3b0ada8eed29aab02408e8f4d18e67199750c972d7b38a94840ce1810fb"}
{"bytes": 11384, "path": "scripts/platformkit/execution/family_week_ledger.py", "sha256": "ffa5c7e45775d35c44dcf7fbbf0b0019fc38bad84b29e44ab7f56920adb17618"}
{"bytes": 14570, "path": "scripts/platformkit/ops/forward_week_report.py", "sha256": "792a94c0cbc7410433ebe526b40b7fe0b056e5cd97b0d79502a9cb82fbba7641"}
{"bytes": 9410, "path": "scripts/platformkit/ingame/game_market_link.py", "sha256": "800b82ea07b2d8a06f5f49c5751e3a0dd0ab1405e59dd798353541da8f55f8dc"}
{"bytes": 5777, "path": "scripts/platformkit/ingame/tennis_ticker_match.py", "sha256": "71b65dcdb7e5ba872b3804a136982e199d9e4ef005abdc580080b8969c286d24"}
```

All six must-not-move files (cross_venue_link.py, cross_venue_pairs.py,
local_state_capture_sources.py, domains/nfl/ingest_nfl_states.py,
family_week_ledger.py, forward_week_report.py) are confirmed byte-identical to
`master` (`git diff --quiet master -- <path>`) after every fix, including this
one; game_market_link.py and tennis_ticker_match.py (read-only dependencies)
are likewise untouched.

Contract preflight: 9 PASS, 0 FAIL (vocab, crlf, loc, schema, head_slice,
spec_threshold, proposed, removed_artifact, row_duplication) over the five
owned files (including this memo).

Test counts: test_settlement_witness.py 45 passed (unchanged since fix 1c);
test_settlement_witness_1b.py 15 passed (2 new, AMENDMENT 6 regressions).
Total 60 passed. `wc -l`: settlement_witness.py 300, settlement_witness_orient.py
79, test_settlement_witness.py 297, test_settlement_witness_1b.py 278, this
memo <= 300 -- all <= 300, all ASCII.

The all-unwitnessed real-day result is unchanged by this fix and stays the
expected outcome: with no `--settlement-witness` table on disk, every served
game remains settlement_unverified / agreement=unresolved / witnessed=false
and week_gradable=false. This fix changes construct behavior only; no
real-day run was performed.

## FIX 1f (AMENDMENT 6)

Round 5 codex sol REJECT (two blockers, one correction), applied:
(a) `_tennis_codes()` in settlement_witness_orient.py now requires the
ticker's YES suffix (`team_code_from_ticker`) to be one of the two resolved
surname codes, mirroring `_codes()`'s own suffix check for team sports --
previously only the split of the ticker's raw tail against the two player
names was checked, so an unrelated suffix (never verified against the
resolved pair) could reach orientation() unrefused. Regression: ticker
KXATPMATCH-26SEP22BARILA-XYZ with resolved BAR/ILA -> the row fails identity
before bookkeeping (state_row_refusals), orientation() then sees no usable
state row and raises "orientation absent" -- both paths converge on
orientation_unresolved, agreement=unresolved, witnessed=false, never a match.
(b) `declared` in settlement_witness.py (~line 193) is now
`isinstance(winner, str) and bool(winner.strip())`; a whitespace-only winner
no longer counts as a declaration, so it never fires
settlement_witness_final_absent/_final_unresolved -- it resolves through
label_code (which finds no word to alias) to winner=None and is refused as
settlement_witness_winner_unresolved, with settlement_unverified alongside it
as the only other reason. Regression: entries=[dict(witness, winner="   ")]
with no feed final -> counts has no final_absent, one winner_unresolved.
(c) Memo: the prior sentence claiming a winner "must exactly equal one of the
feed's two identities or tie" is corrected above (Input and output contract)
to the actual rule the code applies -- label_code's word/first-three-letters
alias against the two resolved codes (team codes, or tennis surname codes),
or the literal "tie"; never a raw string-equality check.
Both fixes are additive to the shared helpers already used elsewhere in this
module (`_codes()`'s pattern; the existing `declared` gate), so no other
construct case moved job; all 12 enumerated cases plus 2 new AMENDMENT 6
regressions pass, 60 pytest instances total. The six protected sources are
confirmed byte-identical to `master` after this fix (see the A9 table above,
base sha `dec6b6b85`).

## NOT VERIFIED

- No real-day counts, archived shard behavior, network, GPU or pod run.
- No owner-provided witness table or real provider equivalence established.
- No continuous post-final coverage, cadence quality or complete week certified.
- Tennis score AND identity support are implemented; no tennis capture
  end-to-end exercised.
- Filesystem crash/power-loss durability beyond constructed replacement failure.
- Independent verifier acceptance and sandbox commit were not performed.
