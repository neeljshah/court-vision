# S398 1i -- cross-venue counts (PREPARE)

Local construct validation only; no network, real archive scan, commit or data/cache access.
FIX 1h addresses AMENDMENT 10 and FIX 1i addresses AMENDMENT 11; historical probe records remain intact.
Modules and tests remain within 300 lines each; local check results are recorded below.
Prior FIX 1f self-report: 53 scan cases and 31 schedule cases passed, one file at a time.
Machine: local Windows worktree C:/Users/neelj/nba-harness-h59.

## BINDING BEFORE-CONDITION -- quoted from master
(a) `coherence_scanner.py:71` `def scan(rows: list[dict], definitions: list[dict]) -> dict` and
`:141` `def run(book_paths: list[str], definitions: list[dict]) -> dict`. The sync rule is
`:48-52`:

    skew = max(receipts) - min(receipts)
    result["receipt_skew_seconds"] = skew
    if skew > Decimal("5"):
        result.update(status="sync_failure", reason="response_end_skew")
Receipts come from `timestamp(rows[t][0]["response_end_ts"])` (`:43`). The counts schema is a
`Counter` serialized at `:126` as `{"notice": NOTICE, "counts": dict(sorted(counts.items())), ...}`,
and `NOTICE` (`:22`) is `"MARKET-STRUCTURE MEASUREMENTS. A residual is not an opportunity. Related
contracts of one game are not independent families."`
(b) `coherence_scanner_inputs.py:18` `def decimal_value(value: Any) -> Decimal` (accepts `str` or
`Decimal` only, refuses non-finite); `:28` `def timestamp(value: Any) -> Decimal` (parses through
`parse_venue_time` and rebuilds the exact fraction at `:35-41`, so sub-microsecond digits survive);
`:83` `def batch_fee_decimal(venue, mode, qty, price) -> Decimal` dispatching
`("polymarket", "taker"|"maker"): venue_fees._POLYMARKET_{TAKER,MAKER}_FEE_RATE` (`:88-89`) with
the Kalshi cent-ceiling at `:97`; `:188` `def read_rows(paths, counts) -> tuple[list, list]`
(sorts resolved files, `parse_float=Decimal`, counts `file_errors` / `json_errors`).
(c) `capture_book_adapter.py:1-7`: "Capture prices are probabilities (legacy orderbook yes/no levels
are cents). Both output fill ladders are resting bids: a NO bid p is a YES ask 100-p." `_touch`
(`:97`) pairs `yes_bid` with the mirrored `no_ask`, and `_fill_levels` (`:135`) carries the touch
size. This row consumes that convention directly (the YES ask size is the NO bid size).
(d) S397 spec, snapshot row: venue `polymarket`, `price_unit 'probability'`, `yes_bid_cents /
yes_ask_cents as Decimal cents`, `api_ts = the book's timestamp field verbatim`, `a sequence field
(the book hash verbatim)`; market_meta row: `umaResolutionStatuses`, `end_date_iso`, `neg_risk`,
`minimum_tick_size`, `game_start_time`, `tokens`.
(e) Kalshi snapshot row, `local_capture_runner_row.py:44` envelope
(`record_type, venue, sport, series, ticker, event_ticker, venue_status, capture_ts,
request_start_ts, response_end_ts, http_status, capture_version`) and `:94` `book_row`, which sets
`api_ts=body.get("ts"), yes_bid=yb, no_bid=nb, yes_ask=Decimal(1) - nb`.
(f) State row, live shard `data/cache/ingame_books_local/state/mlb/2026-09-22.jsonl`, first row keys:
`away_abbr, capture_ts, capture_version, date, game_key, home_abbr, http_status, raw_sha256,
request_start_utc, response_end_utc, source_ts, sport, state, state_changed, status`; `status` is
`"live"` and `state` carries `score_home` / `score_away`.
(g) The S360 orientation finding, quoted from the S398 spec itself: "home / away orientation:
0 matched as-is, 1603 matched flipped, 4 ambiguous". A grep of `docs/evidence/` here did not locate
the underlying artifact line; it is carried as the spec states it and is only the REASON the
orientation check exists, never an input.
(h) `fee_certification_gate.py:64` `@dataclass(frozen=True) class CertificationStatus` with
`certified, checks_total, mismatches_total, mismatch_fixture_ids, mismatch_classes,
fee_module_sha256, fixture_set_sha256, evaluated_at_utc, undercharge_bound_per_order, label` and a
`__post_init__` that refuses `self.certified != (self.mismatches_total == 0)`.
## Historical probes (orchestrator measurements, not rerun by FIX 1f)

Earlier float and integral-int explanations below are superseded by the correction section.

### Probe 1 (AMENDMENT 1), verbatim counts

MEASURED: pairs 0; games_total 16, games_unmatched 16, every one
unmatched_missing_directional_team_evidence (the Kalshi orderbook rows carry no home / away evidence, exactly the S404 finding);
polymarket_link_refusals 120 and polymarket_link_conflicts 52 (the smoke rows were captured before S397 fix 1c and carry game_key
None, link_path 'unlinked').

### Probe 2 (AMENDMENT 2), verbatim counts

PAIRS: pairs_matched 2 (824709 KXMLBGAME-26SEP221845CLEBOS-BOS with the label
'Boston Red Sox'; 824867 KXMLBGAME-26SEP221915CINATL-ATL with 'Atlanta Braves'), games_total 6, orientation_unresolved 4,
polymarket_label_unresolved 26, pm_linked_by_game_key 40, pm_start_from_meta 120, pm_game_key_unscheduled 12,
state_date_disagrees_with_schedule 0, input_lines 107241. SCAN: paired_instants 0 because polymarket_row_refusals 120 = EVERY
S397 snapshot row (the reader raised ValueError 'expected a decimal string' on all 120: the S397 rows carry best_bid / best_ask /
sizes / yes_bid_cents / yes_ask_cents as JSON floats such as 43.0, and the landed decimal reader admits int or decimal text only,
never a float -- the reader is right, the archive encoding is the defect and is S397 AMENDMENT 6); kalshi_row_refusals 45,
kalshi_non_snapshot_rows 96310, unpaired_kalshi_receipts 94 (46 + 48), fee_certification_absent 1, orientation_unresolved 4,
settlement_mismatch 0, every other total 0. [withdrawn: AMENDMENT 7(i) / 9(c)]

### Probe 3 (AMENDMENT 3), verbatim counts

PAIRS: pairs_matched 5 of games_total 6 (823328 STLPIT-PIT 'Pittsburgh Pirates', 823412
MILPHI-PHI 'Philadelphia Phillies', 824624 MIACHC-CHC 'Chicago Cubs', 824709 CLEBOS-BOS 'Boston Red Sox', 824867 CINATL-ATL
'Atlanta Braves'); games_unmatched 1 (824785 TORBAL: conflicting_state_identity 1 and schedule_home_code_unresolved 1 -- the
smoke-4 archive holds only totals markets for that event, so the expected count was moneyline_absent; the verifier judges which
of the two counted reasons fired first and whether moneyline_absent must also be counted for it); spread_market_excluded 4,
total_market_excluded 9, orientation_unresolved 0, pm_linked_by_game_key 40, pm_start_from_meta 120, pm_game_key_unscheduled 12,
input_lines 114894. SCAN: paired_instants 0 still; polymarket_row_refusal_reasons {"'yes_bid_size'": 120} -- a KeyError, not the
float refusal: the scan's quote reader requires the Kalshi-shaped touch sizes yes_bid_size / yes_ask_size and the S397 row
carries best_bid_size / best_ask_size only (a second S397 encoding gap, now S397 AMENDMENT 6(d)); kalshi_row_refusal_reasons
{'expected a decimal string': 45} (45 real Kalshi rows carry a float field; counted, a finding for the S368 reader's owner, not
this row); unpaired_kalshi_receipts 233 over the five pairs; every other total 0. [withdrawn: AMENDMENT 7(i) / 9(c)]

### Probe 4 (AMENDMENT 6), verbatim counts

PAIRS: pairs_matched
5 of 6 (STLPIT, MILPHI, MIACHC, CLEBOS, CINATL), games_unmatched 1 (TORBAL: conflicting_state_identity 1,
schedule_home_code_unresolved 1), kalshi_label_unresolved 1, orientation_unresolved 0, settlement_unverified 5 (the witness
table ships EMPTY, as ruled), settlement_witness_refusals 1, spread_market_excluded 5, total_market_excluded 9,
pm_linked_by_game_key 38, pm_start_from_meta 120, pm_game_key_unscheduled 14, input_lines 122205. SCAN: polymarket_row_refusals
0 (every S397 decimal-text row ADMITTED -- the S397 fix 1e closed the reader gap); paired_instants STILL 0, unpaired_kalshi_receipts
233 (45 / 45 / 49 / 46 / 48 per pair), state_changes 1, lead_base_missing 1, fee_certification_invalid 1 (no document injected),
kalshi_row_refusals 45 ('expected a decimal string').

ROOT CAUSE OF THE ZERO, measured on the Kalshi shard: the five paired tickers
have 45-49 snapshot receipts for the WHOLE day, the last at 15:43-15:46Z (the supervised relaunch), none in the smoke's window
18:44:03-18:45:46Z -- the landed Kalshi capture polls a scheduled game's book only sparsely before its focus window (median
receipt gap 257 s, one gap of 45164 s), so a pre-game Polymarket smoke cannot pair with anything. 
paired_instants > 0 has never been observed on real rows

## FIX 1f behavior and pinned cases

- 8(a)/7(a): certification reads every required key and constructs the landed
  CertificationStatus. status/errors/unverified are additional required report fields.
  checks_total is a positive strict int; mismatches_total/errors/unverified must be zero;
  both SHA-256 identities must be 64-hex and evaluated_at_utc must parse as venue time.
  Each omitted field is tested. Missing certification AND settlement witness independently
  count fee_uncertified AND settlement_unverified_instants on the eligible paired instant.
- The quantity-linearity assurance is WITHDRAWN. Kalshi fees round UP to cents, so quantity
  changes can change a crossing decision. All crossing checks now use exactly ONE contract
  on each venue while touch-size units remain undeclared. Sizes still undergo input validation.
- 8(b): previous state is updated only on accepted non-None rows; pre / None / live retains
  the change at receipt 2 and counts state_refused_receipts 1.
- 8(c): strict pair-table counts are validated inside the refusal branch. A count of 1.0
  yields pair_table_invalid 1, zero results, and no exception or partial count import.
- 7(b): SLUG_ORDERS declares MLB away-first only. Every undeclared sport refuses
  orientation_undeclared_sport and orientation_unresolved. Both labels' alias witnesses are
  checked where they resolve. The NBA Lakers/Clippers home-first question never forms a pair.
- 7(c): exact schedule duplicates include scheduled_start in their identity. Different starts
  for the same four-field identity refuse duplicate_schedule_identity, independent of order;
  excluded identities count games_total and games_unmatched once, including the file loader.
- 7(d): nearest-neighbor pairing consumes the Polymarket receipt as well as the Kalshi receipt.
  Both polling-cadence directions are pinned: paired_instants <= min(receipts at either venue).
- 7(e): book_age_seconds is receipt minus api_ts, separately per venue, with nearest-rank
  median/p90/max. age_semantics_undeclared is counted. stale_kalshi/stale_polymarket/ties remain
  explicit zero compatibility counters; they no longer classify observations. staleness_seconds
  is replaced by book_age_seconds under the explicit amendment. Only the owned tests consume it.
- 7(f): EPISODE_CONTINUITY_SECONDS = 60 is declared once in pairs and imported by scan.
  A non-crossing paired instant, a gap exceeding 60 seconds, or a suspension on either venue
  ends an episode. The Polymarket-only suspension and 600-second observation hole are pinned.
- 7(g): state api_ts supplies the change time. state_receipt_latency_seconds records receipt
  minus api_ts; receipt after both moves counts lead_state_receipt_late and excludes leadership.
  Missing state api_ts counts state_api_time_refusals and lead_state_time_missing without
  inventing an API time from receipt. A six-second delayed receipt retains the +3/+9 ordering.
- Accepting status remains Kalshi text active / Polymarket text true. Non-text is
  venue_status_invalid. The S368 imported sync bound stays 5 seconds, pairing window 30,
  lead window 120, and the declared implausible API clock bound 3600 seconds.

## Correction of the historical Kalshi explanation (8d)

AMENDMENT 7(i) withdrew AMENDMENT 6's Python-float diagnosis: the writer emits Decimal
values as JSON number text. The later S406 AMENDMENT 2 landed reader also decodes INTEGRAL
numbers as Decimal (read_rows uses parse_float=Decimal and parse_int=Decimal). Therefore
neither default-json float observations nor an integral-int explanation attributes today's
45 refusals. CONSTRUCT-ONLY: the field-level fixture reproduction uses this candidate's own quote():
local_capture_runner_v1, no_bid_size, NoneType, expected a decimal string.
The fixture s398_kalshi_refusals.jsonl has exactly one null NO-side touch field, no_bid_size;
the other three numeric quote inputs are Decimal after read_rows. This identifies the null
NO-side refusal mechanism in that fixture only. There is no by-field attribution table.
The [S406 real census](S406_census_real_2026-09-22.md) reports null price fields on a null
book side: 292 shard-wide, 45 among the five paired tickers; attribution by count only.
Those 45 remain un-attributed by field until the orchestrator runs this candidate's quote()
over the same real Kalshi mlb shard and records each refusing field per capture_version.
quote() reads yes_bid and yes_ask before sizes; this size-only fixture cannot identify
which price field refuses on real rows. No real archive or data/cache was opened here.
Probe 4 admitted all Polymarket rows. Its zero paired instants is attributed to sparse
Kalshi polling outside the smoke window, not to the earlier Polymarket reader refusals.

## Reproductions and verification

The FIX 1f Python one-liners print the before/after cases below. All are constructs.
Before scan outputs: incomplete certification True/invalid 0; previous []/refused 1;
non-strict table ValueError; missing cert plus witness fee_uncertified 0/settlement 1;
cadences 3/1; hole episodes 1; suspension episodes 1; delayed lead K0/P1/unbounded1;
late state excluded 0/neither1. The prior min-size policy counts the narrow construct
crossing, while ONE contract refuses it (Kalshi cent rounding is material).
Before orientation: pair True, outcome Los Angeles Clippers, unresolved0/undeclared0.
After orientation: pair False, outcome None, unresolved1/undeclared1.
Before starts: [(1, 0, 0), (0, 0, 1)]; after: [(0, 1, 0), (0, 1, 0)].
Each tuple names pairs / duplicate_schedule_identity / settlement_mismatch.

After scan outputs (same Python one-liner):
8a incomplete: False 1
8b previous: [Decimal('2')] 1
8c table: 0 1
7a missing both: 1 1
7d cadences: 1 1
7f hole: 2
7f suspension: 2
7e age: 0 1
7g delayed: 1 0 0
7g late: 1 0
The isolated age probe reports Kalshi 0.0 seconds / Polymarket 600.0 seconds and
age_semantics_undeclared 1; the old timestamp-order rule reported stale_polymarket 1.
8d field: local_capture_runner_v1 no_bid_size NoneType expected a decimal string.
The memo-marker probe changed False to True.

Required test last lines:
53 passed in 0.97s
31 passed in 0.81s
Both cross_venue_scan and cross_venue_pairs --help exited 0.
git diff master --stat with only owned pathspecs is empty: candidate files are untracked.
The spec modification and archived critique were already present at lane start.

Fixture inputs below are local CONSTRUCT rows, resolution not_applicable:
tests/platformkit/execution/fixtures/s398_kalshi.jsonl | 2054 bytes
tests/platformkit/execution/fixtures/s398_kalshi_refusals.jsonl | 1024 bytes
tests/platformkit/execution/fixtures/s398_markets.jsonl | 10343 bytes
tests/platformkit/execution/fixtures/s398_polymarket.jsonl | 2438 bytes
tests/platformkit/execution/fixtures/s398_settlement_witness.json | 345 bytes
tests/platformkit/execution/fixtures/s398_state.jsonl | 2488 bytes

## FIX 1g

- CORRECTION 1: marked the 8(d) reproduction and final limitation CONSTRUCT-ONLY,
  removed the size-field attribution of the real 45, and cited S406's null-side counts.
  No by-field census table is claimed. quote()'s docstring now states its validation
  order and the construct attribution limit; executable behavior is unchanged.
- CORRECTION 2: preserved both historical probe sentences and appended the exact inline
  withdrawal marker to each. The markers withdraw explanations, not the recorded counts.
- NOTE 3: added the Kalshi venue-timestamp limitation to NOT VERIFIED.
- Reproduction: added memo assertions before corrections; per-file scan run reported
  `3 failed, 53 passed in 1.09s`. Failing output, quoted:
  `AssertionError: 1g correction 1: CONSTRUCT-ONLY labels missing`
  `AssertionError: 1g correction 2: inline withdrawal marker missing`
  `AssertionError: 1g note 3: unmeasurable book age missing`
- Regression checks are parameterized in the existing memo test to stay within 300 lines;
  all original test assertions remain. After correction, local per-file results:
  `tests/platformkit/execution/test_cross_venue_scan.py`: `55 passed in 0.95s`;
  `tests/platformkit/execution/test_cross_venue_pairs_schedule.py`: `31 passed in 0.68s`.
  Each used `python -m pytest <one file> -q -p no:cacheprovider`.
  Both row modules' `--help` commands exited 0; neither exposes a self-check flag.
  Contract preflight over all 12 owned candidate files: 9 PASS, 0 FAIL (`--base master`,
  `--spec docs/evidence/tracking/specs/S398_spec.md`); verdict file excluded.

## FIX 1h

Applies AMENDMENT 10 (a)-(k) and both round-1 verdicts. The codex lane that began this fix
stopped mid-work on a usage limit; this section continues its uncommitted state unchanged.
- (a) A None Kalshi label code excludes the pair; kalshi_label_unresolved,
  orientation_unresolved and games_unmatched each increment. The tracked schedule test now
  requires zero pairs.
- (b) Every snapshot's venue_status is type-checked before indexing; a non-string status
  counts venue_status_invalid and is excluded (and marks an interruption where tracked). Paired and
  unpaired cases on both venues are regression tests.
- (c) Schedule identities are grouped by (sport, game_key); more than one identity is one
  unmatched game with no pair, in either input order.
- (d) Polymarket metadata conflicts count once per condition with more than one distinct
  value set; A,A,B and B,A,A give byte-identical pair tables and counts.
- (e) A declared pair with both books empty carries books_absent_both_venues 1 plus both
  receipt counts (0 / 0).
- (f) Both writers use one atomic_write: sibling temporary file, flush, fsync, os.replace.
  Injected fsync or replace failures leave the previous artifact byte-identical, with no
  temporary file left behind.
- (g) The alias-witness try/except is removed; a label_code failure re-raises.
- (h) The pairing window STANDS: the scan is retrospective by design, not a decision-time query,
  and -30s and +30s are inclusive (30.000000001 s is excluded; sync limit 5 s likewise inclusive).
- (i) Moneyline questions are compared after case folding and internal whitespace collapse;
  spreads (2) and totals (1) stay excluded under uppercase and repeated spaces.
- (j) A witness winner that contradicts the archived final counts
  settlement_witness_contradicts_final and settlement_unverified; the pair is not verified.
- (k) Fixture sizes above are actual on-disk bytes (2054 / 1024 / 2488 for kalshi /
  refusals / state), pinned by a test that reads st_size.
- Line budget: cross_venue_pairs.py (316) and cross_venue_scan.py (307) were brought to 300
  by joining lines only; min() replaces next(iter()) on the single state identity.

Reproduction. The pre-fix code was untracked and was overwritten by the dead lane, so the
before-state of (a)-(g), (i) and (j) is the tiers' measured output quoted in the verdict
(for example `pairs=1, kalshi_label_unresolved=1, orientation_unresolved=0`). The one case
still failing at pickup, reproduced here:
`1 failed, 32 passed in 1.17s`
`AssertionError: assert 'retrospective by design, not a decision-time query' in ...`
After this section, per-file results (`python -m pytest <one file> -q -p no:cacheprovider`):
`tests/platformkit/execution/test_cross_venue_pairs_schedule.py`: `31 passed`;
`tests/platformkit/execution/test_cross_venue_scan.py`: `55 passed`;
`tests/platformkit/execution/test_cross_venue_s398_1h.py`: `33 passed`.
Both `--help` commands exited 0 (CPython 3.10.0). Contract preflight over the 13 owned
files (`--base master`, `--spec docs/evidence/tracking/specs/S398_spec.md`): 9 PASS, 0 FAIL.

## FIX 1i

Applies AMENDMENT 11 and both round-2 verdicts (Opus tiers 1 and 2, ACCEPT WITH CORRECTIONS).
Owned set: AMENDMENT 11(1) admits test_cross_venue_s398_1h.py and fixtures/s398_kalshi_refusals.jsonl;
this fix adds the companion regression file tests/platformkit/execution/test_cross_venue_s398_1i.py.
Each case was reproduced before the edit (scratch construct, CPython 3.10.0); BEFORE -> AFTER:
- Tier 1 finding 1 / AMENDMENT 11(1), owned set: no code change; recorded here.
- Tier 2 CORRECTION 1 / 11(2), slug_order handler (cross_venue_link.py token_code). BEFORE:
  `token_code('mlb', {'series': ' '}, ...) -> (None, False)`, slug_order_refusals 0. AFTER: the handler
  counts slug_order_refusals 1 by name (token_code now takes the counter); the pair exclusion still
  also counts polymarket_label_unresolved, so the exclusion is no longer bare.
- Tier 2 CORRECTION 2 / 11(3), non-canonical decimal text (cross_venue_scan.py _number). BEFORE:
  a Kalshi yes_bid of "0.43 ", " 0.43", "0.43
" or "0.4_3" gave `receipts 1 refusals 0`. AFTER: each
  gives `receipts 0 refusals 1` with reason noncanonical_decimal_text, refused before the landed
  decimal_value sees it. The canonical form is an optional leading minus, digits, at most one dot,
  at least one digit; no whitespace, underscore, sign plus or exponent. Decimal (parsed JSON) values
  are unchanged. Prices and sizes on both venues route through _number.
- Tier 1 NOTE 2, episode continuity. BEFORE: crossing, a Kalshi receipt refused in quote() (null
  yes_bid), crossing gave `paired 2 episodes 1`. AFTER: `paired 2 episodes 2`. A receipt refused in
  quote() is recorded in interruptions per (venue, ticker) beside invalid-status receipts; an
  unreadable ticker or time counts <venue>_refused_receipt_time_refusals. The same books() path
  applies to Polymarket refusals; both venues are pinned.
- Tier 1 NOTE 3, witness winner vocabulary (cross_venue_pairs.py verified_settlement). BEFORE:
  winner 'Toronto Blue Jays' against a TOR 3-2 final gave verified False, contradicts_final 1.
  AFTER: verified True; the winner passes through label_code over the game's two alias codes.
  'tie' stays literal; a winner that resolves to no code counts
  settlement_witness_winner_unresolved and is never verified.
- Tier 2 NOTE 4, terminal vocabulary. BEFORE: a contradicting witness (BAL against TOR 3-2) under
  status 'Game Over', or with no final row, gave verified True. AFTER: verified False with
  settlement_witness_final_absent 1. FINAL is taken from the landed normalizer
  (local_state_capture_sources._MLB_STATUS['Final'] == 'final'); archive rows carry the normalized
  token, so raw 'Game Over' text is not terminal.
- Tier 1 NOTE 4, withdrawn totals. BEFORE: totals printed stale_kalshi 0, stale_polymarket 0,
  ties 0. AFTER: all three print null (WITHDRAWN_TOTALS) until AMENDMENT 7(e) is re-declared.
- Tier 2 NOTE 3, question position onto slug order when labels do not resolve: a SPEC risk under
  the spec's own rule (:93-95, :186-187); behaviour unchanged, named in NOT VERIFIED.
- Tier 2 NOTE 5: NOT VERIFIED now restates paired_instants 0 with its reason.
- Line budget: each module stays at 300 lines by joining lines only. link.py and
  test_cross_venue_pairs_schedule.py were normalized from mixed CRLF to LF (bytes only).
- Tests changed: four token_code call sites gained a Counter(); the CLI totals assertion now
  requires null for the three withdrawn keys and a strict int for every other key.

Per-file results after FIX 1i (`python -m pytest <one file> -q -p no:cacheprovider`):
`tests/platformkit/execution/test_cross_venue_pairs_schedule.py`: `31 passed`;
`tests/platformkit/execution/test_cross_venue_scan.py`: `55 passed`;
`tests/platformkit/execution/test_cross_venue_s398_1h.py`: `33 passed`;
`tests/platformkit/execution/test_cross_venue_s398_1i.py`: `28 passed`.
Both `--help` commands exited 0 (CPython 3.10.0). Contract preflight over the 14 owned
files (`--base master`, `--spec docs/evidence/tracking/specs/S398_spec.md`): 9 PASS, 0 FAIL.

## NOT VERIFIED

- paired_instants > 0 has never been observed on real rows. Historical probe 4 formed five
  pair identities but paired_instants 0: the landed Kalshi capture polls a scheduled game's book
  only sparsely before its focus window (median receipt gap 257 s, none in the smoke window), so
  a pre-game Polymarket smoke had nothing to pair with. No real crossing, age, lead or quantile
  is claimed. paired_instants was not re-measured by FIX 1i.
- SPEC RISK (AMENDMENT 11 note): when neither label resolves through alias, token_code maps
  question position onto slug order by the spec's own rule (:93-95, :186-187); a question listed
  home-first would pair the wrong side with 0 conflicts. Real question order is unverified.
- The real terminal-status vocabulary beyond the landed normalizer tables is unverified.
- The committed settlement witness table is empty; actual rule equivalence is owner-declared.
  Generic rule hashes have no date/condition scope. The empty table prevents activation;
  reusable witness scope remains unverified (archived critique item 8).
- Touch-size units and actual timestamp semantics are undeclared. ONE-contract checks do not
  establish available size, fills, queue position, or an actionable interpretation.
- Certification provenance is not established by schema/digest-shape validation.
- CONSTRUCT-ONLY: the 45 real Kalshi refusals remain un-attributed by field until the
  orchestrator runs this candidate's quote() over the same real mlb shard per capture_version.
  [S406](S406_census_real_2026-09-22.md) supports null-side attribution by count only:
  292 shard-wide, 45 among the five paired tickers. The size-only fixture is no real census.
- Kalshi book age is unmeasurable until the Kalshi writer records a venue timestamp.
  S406 reports api_ts null on all 26927 snapshot rows; receipt time is no substitute.
- Independent verification of FIX 1i remains pending; local test counts are self-checks.

