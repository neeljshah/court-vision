GAP S398 | sport all captured (venue) | worktree harness-h59 (master-based) | log cx_s398_cross_venue_scan
# Cross-venue coherence scan on identical games, counts only (workstream D; ASTRA_ROUND15 row 11; after the first S397 archive)

SINGLE PROBLEM: with Kalshi and Polymarket books captured for the same game, nothing measures which venue is stale, by how many
seconds and how often, nor how often a fee-netted crossing exists between the two books. The landed coherence scanner (row S368)
reasons within ONE venue about related contracts of one game. Cross-venue staleness is a microstructure fact; it must be measured as
counts and seconds before anyone reasons about it, and asynchronous receipts, suspensions or different resolution rules must not be
allowed to masquerade as venue disagreement.

BINDING BEFORE-CONDITION: quote from master (a) scripts/platformkit/execution/coherence_scanner.py scan(rows, definitions) / run(),
the sync_failure rule (receipt skew > Decimal('5') seconds on response_end_ts), the counts schema and NOTICE; (b)
coherence_scanner_inputs.py decimal_value, timestamp, batch_fee_decimal(venue, mode, qty, price) (dispatches polymarket taker /
maker), read_rows; (c) capture_book_adapter.py (YES bid / mirrored NO bid as the YES ask, Decimal cents, touch sizes); (d) the S397
spec's snapshot row (venue polymarket, price_unit, yes_bid_cents / yes_ask_cents, api_ts, sequence) and market_meta row
(umaResolutionStatuses, end_date_iso, neg_risk); (e) the Kalshi snapshot row fields (yes_bid, no_bid, yes_ask = 1 - no_bid, api_ts,
response_end_ts, venue_status); (f) the state row's game_key and status; (g) the S360 finding on nba_checkpoints_full (home / away
orientation: 0 matched as-is, 1603 matched flipped, 4 ambiguous); (h) fee_certification_gate.CertificationStatus.

CHANGE (owned files: NEW scripts/platformkit/execution/cross_venue_scan.py, NEW cross_venue_pairs.py, NEW
tests/platformkit/execution/test_cross_venue_scan.py, NEW tests/platformkit/execution/fixtures/s398_*.jsonl, memo):
1. cross_venue_pairs.py (<= 300 LOC): the PAIR TABLE of identical games from the two archives and the state archive: a pair =
   (game_key, the Kalshi ticker for the home side, the Polymarket token for the same outcome) where both venues link to the same
   game_key through the landed linkers; an outcome-orientation check (the Kalshi YES outcome text and the Polymarket outcome label
   name the same team; a mismatch is orientation_unresolved, counted, and the pair is excluded) -- the recorded orientation swap in
   (g) is the standing reason this check exists; a settlement-scope check (a neg_risk market, a market whose end_date_iso is before
   the scheduled start, or a Kalshi market whose settlement rule text differs from the pair's declared rule is settlement_mismatch,
   counted, and excluded). Matched and unmatched games are both counted so the denominators survive.
2. cross_venue_scan.py (<= 300 LOC): --kalshi <paths> --polymarket <paths> --state <paths> --pairs <json> --certification <json or
   absent> --out <json>. For each pair and each Kalshi snapshot receipt (response_end_ts) find the nearest Polymarket snapshot receipt
   within plus or minus 30 s; refuse the instant as sync_failure when the receipt skew exceeds the S368 limit (imported, not
   re-declared); refuse it as suspended when either venue's status is not accepting orders; otherwise record the venue whose api_ts
   is OLDER (stale_venue in {kalshi, polymarket, tie, unknown}) and the staleness in seconds (Decimal; nearest-rank median, p90 and
   max per venue at the end); whether a FEE-NETTED CROSSING exists (the cheaper YES ask on one venue against the other venue's YES
   bid with both fees charged through batch_fee_decimal for the touch quantity; the Polymarket fee is applied ONLY when the injected
   S399 certification status says the units are certified, otherwise the instant is counted as fee_uncertified and never as a
   crossing) -- COUNTED, never valued, and a crossing that persists across consecutive receipts is ONE episode (episodes and
   instants are both reported); and after every state change (a score or status change in the state rows at instant s) which
   venue's mid moved first by more than one tick within 120 s (lead_venue in {kalshi, polymarket, simultaneous, neither}) with the
   lead in seconds. Output: counts per pair and totals (paired_instants, sync_failures, suspended, stale_kalshi, stale_polymarket,
   ties, unknown, crossings_fee_netted_instants, crossings_fee_netted_episodes, fee_uncertified, state_changes, lead_kalshi,
   lead_polymarket, simultaneous, neither, pairs_matched, games_unmatched, orientation_unresolved, settlement_mismatch) plus the
   quantiles; no price VALUE leaves the tool; the NOTICE sentence of S368 is printed. Strict-int counts; Decimal times and prices;
   order independence over files and rows; times only through parse_venue_time.
3. Tests: fixtures from the two real row shapes (at most 30 rows each, public quotes only); a pair with Polymarket 8 s behind on
   api_ts -> stale_polymarket with the staleness in seconds; receipts 6 s apart -> sync_failure; a suspended venue status -> suspended,
   never a crossing; a synthetic crossing wider than both fees -> one instant and one episode only with a certified status injected
   and fee_uncertified 1 otherwise; the same crossing over three consecutive receipts -> 3 instants, 1 episode; a state change followed
   by a Kalshi move at plus 3 s and a Polymarket move at plus 9 s -> lead_kalshi 1 with lead 6; an orientation mismatch excluded and
   counted; a neg_risk market excluded and counted; order independence.
4. Memo docs/evidence/harness/S398_cross_venue_scan_2026-09-22.md.

CONTROLS: PREPARE only; construct tests; no network; no real archive run by the builder; the orchestrator runs it on the first real
S397 archive and records counts only. ACCEPTANCE: per-file tests pass one at a time; --help works; <= 300 LOC; ASCII; contract Q6
vocabulary (a crossing is a count, never an opportunity); memo ends with NOT VERIFIED.

AMENDMENT 1 (2026-09-22 17:2xZ; binding; from the orchestrator's real-row run of the candidate on the real Kalshi mlb shard, the
S397 smoke archive and today's v2 state rows). MEASURED: pairs 0; games_total 16, games_unmatched 16, every one
unmatched_missing_directional_team_evidence (the Kalshi orderbook rows carry no home / away evidence, exactly the S404 finding);
polymarket_link_refusals 120 and polymarket_link_conflicts 52 (the smoke rows were captured before S397 fix 1c and carry game_key
None, link_path 'unlinked'). CHANGE (additive): (a) the Kalshi side of a pair is identified from the COMMITTED SCHEDULE, never from
book-row team evidence: cross_venue_pairs takes --schedule <the S386 / S403 file> and uses each entry's (sport, game_key, game_id =
the Kalshi event ticker, ticker = the canonical home-side ticker); the directional linker is not used on the Kalshi side at all;
an entry whose game_id has no book rows is counted book_event_absent and produces no pair. (b) The Polymarket side pairs by
game_key when the S397 rows carry one (the S397 fix 1c links through gameStartTime / startDate / game_start_time and the slug's
team codes against the state archive); rows without a game_key are paired by the slug's team codes plus the UTC date of the
row's start field against the SCHEDULE entry's state rows (the S386 team_set path), counted pm_linked_by_slug; a row with neither
is counted pm_unlinked and excluded. (c) The outcome-orientation check compares the Polymarket outcome label (a team name) with the
Kalshi canonical ticker's team code through the landed alias table (game_market_link.alias); a label that maps to neither team is
orientation_unresolved. (d) The orchestrator re-probes on the S397 smoke 3 archive (rows with game_key) before the verifier round;
the memo records the pre-fix counts above verbatim.

AMENDMENT 2 (2026-09-22 18:2xZ; binding; VERBATIM FACTS from the orchestrator's second real-row run of fix 1c: the real Kalshi mlb
shard (197,091,580 bytes), the S397 smoke-4 archive (rows with game_key; 2,185,892 bytes), today's v2 state shard and the committed
2026-09-22 full-selection schedule of six games). PAIRS: pairs_matched 2 (824709 KXMLBGAME-26SEP221845CLEBOS-BOS with the label
'Boston Red Sox'; 824867 KXMLBGAME-26SEP221915CINATL-ATL with 'Atlanta Braves'), games_total 6, orientation_unresolved 4,
polymarket_label_unresolved 26, pm_linked_by_game_key 40, pm_start_from_meta 120, pm_game_key_unscheduled 12,
state_date_disagrees_with_schedule 0, input_lines 107241. SCAN: paired_instants 0 because polymarket_row_refusals 120 = EVERY
S397 snapshot row (the reader raised ValueError 'expected a decimal string' on all 120: the S397 rows carry best_bid / best_ask /
sizes / yes_bid_cents / yes_ask_cents as JSON floats such as 43.0, and the landed decimal reader admits int or decimal text only,
never a float -- the reader is right, the archive encoding is the defect and is S397 AMENDMENT 6); kalshi_row_refusals 45,
kalshi_non_snapshot_rows 96310, unpaired_kalshi_receipts 94 (46 + 48), fee_certification_absent 1, orientation_unresolved 4,
settlement_mismatch 0, every other total 0. ROOT CAUSES of the four unresolved games, read from the market_meta rows: (i) one
Polymarket event holds SEVERAL markets that share the team labels -- the moneyline whose question is '<away label> vs. <home
label>' (e.g. 'Milwaukee Brewers vs. Philadelphia Phillies'), spread markets whose question is 'Spread: <team> (-1.5)' with the
same two team labels in a different order, and totals whose question ends ': O/U 7.5' with labels Over / Under; the pair builder
selects no market type, so 823412 and 823328 (moneyline plus two spreads each) resolve to more than one token and 824785 (only
totals captured in that smoke) to none; (ii) the label resolver's first-three-letters rule cannot reach codes that are not the
city's first three letters: 'Chicago Cubs' maps to neither CHI nor CHC for 824624 (the same failure awaits KC, SD, SF, TB, WSH,
CWS, LAA, LAD, NYY, NYM, ARI). CHANGE (additive): (a) MARKET SELECTION by a declared rule: the pair uses the MONEYLINE market only
-- the market_meta whose question is exactly '<label0> vs. <label1>' (no 'Spread:' prefix, no ': O/U' suffix) and whose two token
outcomes are exactly those two labels; spread and totals markets on the same event are counted spread_market_excluded /
total_market_excluded (they settle on a different rule, the settlement_mismatch class) and never paired; an event with no moneyline
market captured is counted moneyline_absent and produces no pair. (b) ORIENTATION from the slug order: the S397 series slug
'mlb-mia-chc-2026-09-22' lists the codes away-then-home and the moneyline question lists the labels in the same order, so label i
is the team at slug code i; the alias-table word rule of fix 1c stays as a SECOND witness where it resolves and a disagreement
between the two witnesses is orientation_unresolved (counted, excluded); a label the slug rule cannot place (a question that is
not '<label0> vs. <label1>') is orientation_unresolved. (c) The scan's every row refusal carries its reason: polymarket_row_refusal_
reasons and kalshi_row_refusal_reasons Counters keyed by the exception text (strict-int values) beside the existing totals, so a
run that refuses every row can be read from the counts. (d) The memo records the counts above verbatim as the second probe; the
orchestrator re-probes on a smoke written after S397 fix 1e (decimal text) before the verifier round.

AMENDMENT 3 (2026-09-22 18:21Z; binding; VERBATIM FACTS from the orchestrator's third real-row run, fix 1d on the same three
archives and schedule as AMENDMENT 2). PAIRS: pairs_matched 5 of games_total 6 (823328 STLPIT-PIT 'Pittsburgh Pirates', 823412
MILPHI-PHI 'Philadelphia Phillies', 824624 MIACHC-CHC 'Chicago Cubs', 824709 CLEBOS-BOS 'Boston Red Sox', 824867 CINATL-ATL
'Atlanta Braves'); games_unmatched 1 (824785 TORBAL: conflicting_state_identity 1 and schedule_home_code_unresolved 1 -- the
smoke-4 archive holds only totals markets for that event, so the expected count was moneyline_absent; the verifier judges which
of the two counted reasons fired first and whether moneyline_absent must also be counted for it); spread_market_excluded 4,
total_market_excluded 9, orientation_unresolved 0, pm_linked_by_game_key 40, pm_start_from_meta 120, pm_game_key_unscheduled 12,
input_lines 114894. SCAN: paired_instants 0 still; polymarket_row_refusal_reasons {"'yes_bid_size'": 120} -- a KeyError, not the
float refusal: the scan's quote reader requires the Kalshi-shaped touch sizes yes_bid_size / yes_ask_size and the S397 row
carries best_bid_size / best_ask_size only (a second S397 encoding gap, now S397 AMENDMENT 6(d)); kalshi_row_refusal_reasons
{'expected a decimal string': 45} (45 real Kalshi rows carry a float field; counted, a finding for the S368 reader's owner, not
this row); unpaired_kalshi_receipts 233 over the five pairs; every other total 0. RULING: the reason counters work as
specified (a run that refuses every row is now readable from the counts); the memo records these counts verbatim as the third
probe; the fourth probe runs on a smoke written after S397 fix 1e.

AMENDMENT 4 (2026-09-22 18:5xZ; binding; from the Opus round-1 verdict). (a) OWNED SET PINNED: scripts/platformkit/execution/
cross_venue_pairs.py, cross_venue_link.py (split out for the 300-LOC rail), cross_venue_scan.py, tests/platformkit/execution/
test_cross_venue_pairs_schedule.py, test_cross_venue_scan.py, tests/platformkit/execution/fixtures/s398_kalshi.jsonl,
s398_markets.jsonl, s398_polymarket.jsonl, s398_state.jsonl, and the memo -- additive, no landed module touched. (b) THE REAL
POLYMARKET api_ts IS EPOCH MILLISECONDS TEXT ('1790117436000') beside api_ts_iso ('2026-09-22T23:10:36.000000Z'); the scan's
quote reads api_ts_iso when present, else api_ts through parse_venue_time; a bare epoch string with no api_ts_iso refuses
api_time_refusals (never guessed); the s398_polymarket.jsonl fixture carries the real pair so the staleness test exercises the
real shape (a fixture that hides the real encoding is a defect of the fixture, per CHANGE 3). (c) DENOMINATORS CLOSE: every
excluded schedule entry increments games_unmatched exactly once, on every exclusion path (settlement_mismatch,
kalshi_metadata_conflicts, orientation_unresolved, moneyline_absent, polymarket_meta_missing, conflicting_state_identity), so
games_total = pairs_matched + games_unmatched always; the balance is asserted in a test over each path. (d) venue_status
VOCABULARY DECLARED: the Polymarket accepting value is the CLOB accepting_orders boolean rendered as the text 'true' by the S397
writer (ACCEPTING['polymarket'] = ('true',)); a non-string venue_status is a named refusal venue_status_invalid, never a silent
suspended count; the memo names both vocabularies. (e) NOT VERIFIED must carry: the two venues' touch-size units are undeclared
(Kalshi no_bid_size is not a contract count), so min(ask_size, bid_size) is a unit-blind bound -- fees and gross are linear in
quantity, so no count can be manufactured, but the equivalence is unverified.

AMENDMENT 5 (2026-09-22 18:5xZ; binding; from the codex sol round-1 verdict, five blockers). (a) BOTH LABELS COMPARED: the
Kalshi YES outcome label (the canonical home-side ticker's team code through team_code_from_ticker, and its rules / title text
where present) and the SELECTED Polymarket outcome label are BOTH resolved to a team code (slug-order rule, alias second witness)
and must be EQUAL; a disagreement is orientation_unresolved (counted, excluded) -- a pair whose two labels name different teams
was previously emitted as matched. (b) SETTLEMENT SCOPE AGAINST THE SCHEDULE: end_date_iso is compared with the COMMITTED
scheduled_start of the schedule entry, never with Polymarket's asserted start; settlement_mismatch when end_date_iso precedes it.
Settlement-rule EQUIVALENCE needs a witness: the pair carries settlement_rule_sha256 for BOTH venues (the Kalshi rules text and
the Polymarket description text); a declared equivalence table (tests/platformkit/execution/fixtures/s398_settlement_witness.json,
entries (sport, kalshi_rule_sha256, polymarket_rule_sha256) judged equivalent by the owner; empty until the owner fills it) is
consulted; a pair with no witness entry is counted settlement_unverified and is EXCLUDED from the crossing counts (a crossing
across non-equivalent settlements is meaningless) while staying in the staleness and lead measurements (which do not depend on
settlement); the memo states the table is empty and every real pair is settlement_unverified until the owner declares.
(c) STRICT PAIR-TABLE INPUT: the scan REQUIRES the pair table's counts object with every required key present as a strict int
(a missing key refuses pair_table_invalid, never defaults to zero); the pair writer emits explicit zeroes for every counter.
(d) STRICT CERTIFICATION INPUT: fee-netting is enabled only by a COMPLETE injected certification document validated against the
landed schema (fee_certification_gate.CertificationStatus / the S399 report: checks_total a positive strict int, mismatches 0,
errors 0, unverified 0, status text certified, the evidence identities present); anything less is fee_certification_invalid
(counted) and every instant is fee_uncertified -- {"certified": true} alone never enables netting. (e) AMENDMENT 4(c) stands:
every exclusion path increments games_unmatched exactly once; the balance is asserted.

AMENDMENT 6 (2026-09-22 19:0xZ; binding; VERBATIM FACTS from the orchestrator's fourth real-row run: fix 1e on the S397 smoke-5
archive (decimal text), the real Kalshi mlb shard, today's v2 state rows and the six-game committed schedule). PAIRS: pairs_matched
5 of 6 (STLPIT, MILPHI, MIACHC, CLEBOS, CINATL), games_unmatched 1 (TORBAL: conflicting_state_identity 1,
schedule_home_code_unresolved 1), kalshi_label_unresolved 1, orientation_unresolved 0, settlement_unverified 5 (the witness
table ships EMPTY, as ruled), settlement_witness_refusals 1, spread_market_excluded 5, total_market_excluded 9,
pm_linked_by_game_key 38, pm_start_from_meta 120, pm_game_key_unscheduled 14, input_lines 122205. SCAN: polymarket_row_refusals
0 (every S397 decimal-text row ADMITTED -- the S397 fix 1e closed the reader gap); paired_instants STILL 0, unpaired_kalshi_receipts
233 (45 / 45 / 49 / 46 / 48 per pair), state_changes 1, lead_base_missing 1, fee_certification_invalid 1 (no document injected),
kalshi_row_refusals 45 ('expected a decimal string'). ROOT CAUSE OF THE ZERO, measured on the Kalshi shard: the five paired tickers
have 45-49 snapshot receipts for the WHOLE day, the last at 15:43-15:46Z (the supervised relaunch), none in the smoke's window
18:44:03-18:45:46Z -- the landed Kalshi capture polls a scheduled game's book only sparsely before its focus window (median
receipt gap 257 s, one gap of 45164 s), so a pre-game Polymarket smoke cannot pair with anything. The cross-venue measurement is
only meaningful while BOTH captures poll the same game: the first real scan runs over tonight's games (first start 22:35Z) with a
Polymarket capture running concurrently with the Kalshi capture from the landed S397 code; until then every count in this row is
construct-only or zero. SECOND FACT: the Kalshi snapshot rows for these tickers carry FLOAT fields (yes_bid, no_bid, yes_ask,
no_ask, yes_bid_size, no_bid_size, depth_bid, depth_ask, minutes_to_close on all 233 rows); 45 of them refuse in the landed
decimal reader and the rest are admitted (an integral float read as an int) -- the Kalshi archive has the same encoding defect
S397 just fixed; its census is row S406 (kalshi_decimal_census, allocated now); this row does not convert or guess. The memo
records the probe-4 counts verbatim as the fourth probe and states that paired_instants > 0 has never been observed on real rows.

AMENDMENT 7 (2026-09-22 19:1xZ; binding; (i) a correction of AMENDMENT 6's second fact and (ii) the astra round-2 critique).
(i) CORRECTION: the Kalshi snapshot rows do NOT carry Python floats -- the landed writer serializes Decimal values as JSON number
text (local_capture_runner_row.py:113, local_capture_writer.py:15); the orchestrator's probe decoded them with the default
json.loads and reported floats. The 45 refusals ('expected a decimal string') come from the landed reader rejecting an INTEGRAL
JSON number decoded as int (decimal_value admits str and Decimal only); the census of that is S406 (re-scoped by its AMENDMENT 1).
This row's Kalshi refusal reasons stay as counted; nothing here converts. (ii) FROM THE CRITIQUE (the full text is archived as
docs/evidence/harness/S398_astra_r2_critique_2026-09-22.md and is binding where it names a line): (a) CERTIFICATION STRICTNESS:
no defaulted field -- errors, unverified, mismatches, checks_total and every evidence identity must be PRESENT with the landed
types (identities are 64-hex digests, never 'nonempty text'); a missing certification with a missing settlement witness counts
fee_uncertified for the instant (settlement_unverified is a separate exclusion, both counted); the memo's quantity-linearity
sentence is withdrawn: coherence_scanner_inputs.py:97 rounds Kalshi fees UP to cents, so the crossing decision can depend on the
size unit -- while units are undeclared, a crossing instant is counted ONLY at the touch quantity of ONE contract on each venue
(unit-blind by construction) and the memo says so. (b) SPORT-SPECIFIC ORIENTATION: the slug-order rule (away-then-home with the
question in the same order) is DECLARED PER SPORT in a table (mlb: away-first measured on the real questions; every other sport:
UNDECLARED until measured on real questions) -- a sport without a declared order refuses orientation_undeclared_sport; and the
two witnesses must AGREE whenever both resolve, so 'Los Angeles Lakers vs. Los Angeles Clippers' on slug nba-lac-lal is
orientation_unresolved, never a pair of opposing outcomes. (c) SCHEDULE DEDUPE INCLUDES scheduled_start: duplicate schedule
identities with different starts are refused (duplicate_schedule_identity, counted, no pair), order-independent. (d) UNIQUE
PAIRING: each receipt of EITHER venue participates in at most one paired instant (nearest-neighbour matching with consumption);
paired_instants <= min(kalshi_receipts, polymarket_receipts) per pair; both cadence directions tested. (e) AGE, NOT STALENESS: the
venues' api_ts semantics differ (Kalshi book timestamp vs the CLOB last-update time) -- the measured quantity is renamed
book_age_seconds per venue (receipt minus api_ts), reported per venue as quantiles, and the stale_<venue> classification is
withdrawn until the semantics are declared (counted as age_semantics_undeclared); lead measurements keep their definition.
(f) EPISODE CONTINUITY: an episode ends at any paired instant without a crossing, at any gap between consecutive paired instants
longer than the declared continuity window (60 s, imported as one constant), or at a suspension on either venue; tested with
crossing / hole / crossing and crossing / Polymarket-only suspension / crossing. (g) STATE RECEIPT LATENESS: the lead measurement
uses the state row's api_ts (venue time) as the change instant and records the state receipt latency; a state receipt later than
both venue moves is counted lead_state_receipt_late and excluded from lead counts.

AMENDMENT 8 (2026-09-22 19:2xZ; binding; from the codex sol round-2 verdict on fix 1e, read with AMENDMENT 7). (a) CERTIFICATION
BY KEY: every required certification field is read by key (a missing errors or unverified never reads as zero) and validated
through the landed CertificationStatus; each omitted field tested (restates 7(ii)(a)). (b) STATE PREVIOUS ONLY ON ACCEPTED ROWS: a
refused or None state receipt never resets previous, so {0: pre, 1: None, 2: live} yields the change at 2 with
state_refused_receipts 1 (before: [] and the next genuine change lost). (c) PAIR-TABLE STRICTNESS INSIDE THE REFUSAL BRANCH: a
non-strict count (pairs_matched 1.0) yields pair_table_invalid 1 and no results, never an uncaught ValueError. (d) MEMO: AMENDMENT
6's probe-4 counts verbatim, the sparse-polling attribution, the sentence 'paired_instants > 0 has never been observed on real
rows', the stale NOT VERIFIED bullets and header counts reconciled, and the 45 Kalshi refusals attributed BY FIELD from this
candidate's own quote() (which field was neither str nor Decimal -- null or absent -- per capture_version), since the landed
read_rows admits integral numbers (S406 AMENDMENT 2).

AMENDMENT 9 (2026-09-22 21:4xZ; binding; from the fix 1f report on AMENDMENTS 7-8, which closed 7(a)-(g) and
8(a)-(c) with reproductions and left 8(d) open on real rows). (a) THE 45 REFUSALS ARE CENSUSED ON REAL ROWS OR
LABELLED CONSTRUCT-ONLY: MEASURED -- fix 1f reproduced 8(d)'s memo reconciliation
(8d memo: False -> True; 8d field: local_capture_runner_v1 no_bid_size NoneType) against CONSTRUCTED rows and closed
with "The 45 real refusals were not re-censused; field attribution is construct-only", so AMENDMENT 8(d)'s
per-capture_version field attribution has no real-archive evidence. RULING: the by-field attribution table is
produced by running this candidate's own quote() over the SAME real Kalshi mlb shard that produced the 45, and every
row of the table names its capture_version and the field that was neither str nor Decimal; until that run exists the
table header and the memo say CONSTRUCT-ONLY in those words, the count 45 is never presented as attributed, and the
NOT VERIFIED list carries the gap. Test: the memo's attribution counts sum to 45 and cite the real shard path, or
the table is absent and the construct-only sentence is present.
(b) THE CANDIDATE IS UNVERIFIED UNTIL A ROUND READS IT: MEASURED -- fix 1f reports 53 and 31 passing tests, preflight
FAIL=0 and an empty owned-path diff against master, but no independent verdict on fix 1f exists. RULING: the fix
agent's own counts are never the verification of record; the next round re-runs both suites, re-reads 7(a)-(g) and
8(a)-(c) against the named lines, and states its own counts. Test: the round's transcript carries its own 53 / 31
(or the counts it measures) beside the file paths it read.
(c) CORRECTED READING: AMENDMENT 7(i) withdrew the float claim; the S406 real census (docs/evidence/harness/
S406_census_real_2026-09-22.md) then showed the Kalshi prices and sizes are Decimal-origin number text (max 4 / 2 fractional
digits) and that read_rows decodes with parse_int=Decimal, so an integral number is ADMITTED; the 45 refusals correspond to
snapshot rows whose price fields are NULL (a null side of the book; 292 such rows shard-wide, 45 among the five paired
tickers). The by-field table of (a) must therefore report null / absent fields per capture_version; nothing in this row
converts a refusal, and the census of the encoding belongs to S406.

AMENDMENT 10 (2026-09-23 16:5xZ; binding; from the round-1 independent verification of fix 1g -- sol REJECT (three blockers)
and astra REJECT (one blocker, six corrections); every item MEASURED on constructs by the tiers). (a) AN UNRESOLVED KALSHI
LABEL NEVER PAIRS: kalshi_yes_label 'Unknown Club' with canonical home BAL produced pairs 1 / kalshi_label_unresolved 1 /
orientation_unresolved 0 / games_unmatched 0 (cross_venue_pairs.py:208), and the tracked test at
test_cross_venue_pairs_schedule.py:239 requires that behaviour -- WRONG per AMENDMENT 5(a). RULING: when the Kalshi code is
None the pair is excluded, orientation_unresolved and games_unmatched both increment, and the test requires zero pairs.
(b) VENUE STATUS IS VALIDATED ON EVERY SNAPSHOT BEFORE INDEXING: an unpaired non-string status (True) between two crossings
silently ended an episode with venue_status_invalid 0 (cross_venue_scan.py:182). RULING: every snapshot's status is validated
and counted (venue_status_invalid) before pairing; invalid rows are excluded; the unpaired case is a regression test.
(c) CONFLICTING SCHEDULE IDENTITIES FAIL CLOSED: two distinct event / ticker identities for one (sport, game_key) reduced to
the first with pairs 1 / schedule_duplicate_games 1 / games_unmatched 0 (cross_venue_pairs.py:172). RULING: group by
(sport, game_key); more than one identity -> one unmatched game counted, NO pair emitted. (d) ORDER INDEPENDENCE UNDER
CONFLICTING METADATA: A,A,B vs B,A,A gave conflict counts 1 vs 2 (cross_venue_pairs.py:124, cross_venue_link.py:119).
RULING: a conflict is counted per DISTINCT conflicting value set, never first-vs-rest; both orders byte-identical; test pinned.
(e) A declared pair with both books empty carries a named per-game reason (books_absent_both_venues with the receipt counts),
never a bare zero. (f) Both writers use the atomic pattern (sibling temp + flush + fsync + os.replace; a failure leaves the
previous artifact byte-identical). (g) The alias-witness exception handler (cross_venue_link.py:250) counts the failure by
name (alias_witness_errors) or re-raises; never sets disagreed False silently. (h) The retrospective +/-30 s pairing window
of the spec STANDS (inclusive both ends, stated in the memo; the scan is retrospective by design, not a decision-time query);
the memo says so in one sentence. (i) Moneyline selection normalizes case and internal whitespace before the exact-question
rule; tests for uppercase and repeated spaces. (j) A settlement witness whose winner contradicts the state archive's final is
refused by name (settlement_witness_contradicts_final), never settlement_verified. (k) Memo fixture byte sizes are the ACTUAL
file bytes on disk (2054 / 1024 / 2488 for kalshi / refusals / state), never LF-normalized counts. Everything else in fixes
1b-1g byte-identical in behaviour.

AMENDMENT 11 (2026-09-23 17:2xZ; binding; from round 2 on fix 1h -- BOTH Opus 5.5 tiers ACCEPT WITH CORRECTIONS; every
AMENDMENT 10 item (a)-(k) reproduced as closed by both). CORRECTIONS RULED: (1) the owned set of AMENDMENT 4(a) gains the two
additive files fix 1h wrote -- tests/platformkit/execution/test_cross_venue_s398_1h.py and
tests/platformkit/execution/fixtures/s398_kalshi_refusals.jsonl (s398_settlement_witness.json is already named by AMENDMENT
5(b)); (2) cross_venue_link.py:247 `except REFUSALS: return None, False` around slug_order neither counts nor re-raises (the
memo's (g) said the handler was removed; this one remains): it counts by name slug_order_refusals or re-raises, never a bare
exclusion filed under polymarket_label_unresolved; (3) NON-CANONICAL DECIMAL TEXT IS REFUSED: a yes_bid of "0.53 " (and " 0.53",
"0.53\n", "0.5_3") PARSED through the landed decimal_value because Decimal() tolerates whitespace and underscores, and
_number / quote (cross_venue_scan.py:23, :35-37) call it unguarded; RULING: _number refuses by name (noncanonical_decimal_text)
any text that is not the canonical form the archive writer emits (digits with at most one dot, optional leading minus, no
whitespace, no underscore, no exponent), before decimal_value sees it; Polymarket rows are decimal text so this path is live.
NOTES RECORDED (not blockers; each named in the memo's NOT VERIFIED or a one-line statement): a Kalshi receipt refused in
quote() (a null side, 292 rows shard-wide per S406) does not end an open episode -- refused receipts are recorded per ticker in
interruptions beside invalid-status receipts (a one-line change; pinned by a construct); the settlement witness 'winner' is
passed through the alias / label_code path (a witness written as a full team name is otherwise always a contradiction; fails
closed today); only the status text 'final' is treated as final -- the landed normalizer's terminal vocabulary
(local_state_capture_sources.py:28-48) is the authority, and a witness under 'Game Over' or with no final row stays
settlement_unverified (never verified); the totals stale_kalshi / stale_polymarket / ties are printed as null until AMENDMENT
7(e)'s withdrawn classification is re-declared; when labels do not resolve, token_code maps question position onto slug order by
the spec's own rule (:93-95, :186-187) -- a SPEC risk, recorded, unchanged; the memo's NOT VERIFIED restates paired_instants 0
with its reason (sparse Kalshi polling). Everything else in fixes 1b-1h byte-identical in behaviour.
