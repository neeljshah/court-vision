GAP S424 | sport mlb (rule sport-blind) | worktree harness-h81 (master-based) | log cx_s424_regime_census

# In-game regime census, descriptive, counts only: how often, how wide, how deep and how late each proposed regime is

SINGLE PROBLEM: nothing on file counts the in-game regimes. The owner's thesis ("I can tell when the market is at its worst")
cannot be preregistered until each regime's instants, episodes, spreads, touch sizes and state-to-book lags are COUNTED on real
rows. The register's thresholds are PROPOSALS; this row measures their SUPPORT (instants and games) and does not tune them. It
computes no markout, no drift, no sign and no verdict (register section D: "COUNTS ONLY, no markout, no drift sign read").

BINDING BEFORE-CONDITION (quote from .planning/direction/ingame_regime_hypotheses_2026-09-23.md, "the register", and master):
(a) Population and exclusions, register :73-76 VERBATIM -- "KXMLBGAME snapshots, market_state live, both touches non-null, state
    row for the same game with status live and received at or before t" ... "Exclusions, counted never imputed: decided market
    (mid <= 0.03 or >= 0.97), empty ladder, state status final, book receipt age > 5 s, state receipt age > 15 s". The 5 / 15 are
    LANDED: forward_replay_qualification.py:17 `BOOK_AGE_S, STATE_AGE_S = 5, 15` -- imported, never re-declared.
(b) Regimes (definitions VERBATIM; every constant a proposal): R1 :97-98 "no state receipt with state_changed True in the trailing
    45 s AND no book change in the trailing 15 s AND spread 1-2 c"; R2 :109-110 "from the first state receipt whose (inning, half)
    differs from the previous accepted row, until the first receipt whose pitcher_pitches increases or last_play_id changes.
    Excluded if a score change arrived in the prior 60 s"; R3 :117-119 "the book is 'behind' while every book receipt in (T_s, t]
    shows the same (yes_bid, yes_ask) as the last receipt before T_s, and that receipt is <= 5 s old" plus "the book-leads count:
    a book change received in (T_e, T_s)"; R5 :139-141 "delta raw_market.volume_fp over the trailing 300 s of receipts below V_lo,
    spread 1-2 c" with V_lo "frozen from the 2026-09-22 shard as the game-pooled p25"; R6 :149 "spread >= 2 c two-sided (sub-band
    >= 3 c), or one side null with the other non-null, excluding decided markets"; R7 :161 "no book change in the trailing 60 s
    while >= 1 state_changed True receipt landed in the same 60 s"; R8 :167 "0-30 s and 30-120 s after the first state receipt
    showing score_home + score_away increased". Book change, register :48 -- "diffing consecutive receipts' (yes_bid, yes_ask,
    sizes) per ticker". Instant, :76 -- "Instant t = a book receipt (response_end_ts)".
(c) Fields and where they live, register section 0 plus the orchestrator's 2026-09-23 re-read of first rows (parse_float=str):
    touch = row fields yes_bid / yes_ask / no_bid (decimal text, e.g. '0.9700'), sizes yes_bid_size / no_bid_size ('1272.57'),
    ladders book.orderbook_fp.{yes_dollars,no_dollars} ASCENDING [[price, size]] (last level = the touch); receipt clock
    response_end_ts; api_ts None; volume raw_market.volume_fp ('773106.16'). :17-19 "api_ts is null on 24,843 / 24,843 snapshots"
    -- so every book age is RECEIPT age. :20-21 "NEVER raw_market prices". :24-25 "A regime that reads prints by created_time
    uses information our capture did not hold at t" -- prints enter by capture_ts only (this row reads no print; see DO NOT).
    State: response_end_utc (and response_end_ts on v2 rows), status, state_changed (None on a game's first row), state.{inning,
    half, outs, score_home, score_away, pitcher_id, pitcher_pitches, last_play_id, last_play_ts}. CORRECTION to register :30:
    last_play_ts is ISO text ('2026-09-22T16:47:57.378Z'), not ms; source_ts is '20260922_164757' (unzoned; parse_venue_time
    refuses it -- never used). (d) :33-35, :249-250 -- TBNYY game 1 has an "EMPTY ladder while raw_market still shows 0.99 /
    1.00", "labelled live" on 2,329 receipts per ticker: a book-quality instant, NEVER a regime instant.
(e) Landed decode: forward_replay_io.read_jsonl (streams, parse_float=Decimal) and stamp (the only receipt-time path, via
    venue_time.parse_venue_time). native_rows composes them but MATERIALIZES the shard (S411 AMENDMENT 2: 5,670 MB), and
    load_native runs books(), whose to_quote_book RETURNS {"refused": True, "reason": ...} (capture_book_adapter.py:186-187;
    S421 AMENDMENT 1: inconsistent_touch = raw_market disagreeing with a ladder that the row fields agree with).

CHANGE (owned NEW files: scripts/platformkit/ops/regime_census.py <= 300 LOC; scripts/platformkit/ops/regime_census_defs.py
(DATA); tests/platformkit/ops/test_regime_census.py; tests/platformkit/ops/fixtures/s424_books.jsonl, s424_state.jsonl;
docs/evidence/harness/S424_regime_census_2026-09-22_23.md. Nothing landed is edited):
1. CLI `--books-root --state-root --schedule --date --as-of --out --regime-defs`; --as-of parsed only by parse_venue_time. Rows
   decoded with read_jsonl + stamp under native_rows' own rules (as_of cut -> future_records; record_type kinds; a duplicate
   (ticker, receipt) -> duplicate_native_record, both excluded); a differential test pins equality with native_rows on the
   fixtures. ONE MARKET AT A TIME (S411 AMENDMENT 2): one streaming pass builds a ticker -> byte-offset index for the schedule's
   tickers and a game_key -> offset index for state; each game loads only its ticker's rows and its game_key's state rows,
   sorts by (receipt, canonical text), folds, releases; games fold in game_id order. Declared ceiling 1,000 MB, peak measured;
   exceeding it is the refusal memory_ceiling_exceeded. The join is the schedule's (game_id, game_key, ticker) only.
2. Every book row also goes through to_quote_book; its verdict is COUNTED by reason and each regime's instants split
   adapter_accepted / adapter_refused (the landed replay chain can use only the first). Regime fields are the row fields; a row
   disagreeing with its own ladder top is excluded as ladder_field_disagree (by side).
3. Per game and per regime (R1, R2, R3, R5, R6 with sub-band >= 3 c, R7, R8 0-30 and 30-120): eligible instants, in-regime
   instants, DISTINCT episodes (a maximal run of consecutive in-regime instants of one ticker in receipt order; any other instant
   ends it), spread count-by-cents, touch size count per side in fixed buckets 0; (0,10); [10,100); [100,1000); [1000,10000);
   >= 10000 (the union of the register's :216 edges and this row's ask -- both sets are sums of these), episode span seconds
   (first to last instant), share of eligible live instants, span over the live window (first to last state receipt with status
   live, cut at as_of), exclusions by reason. A regime flag at t reads ONLY rows with receipt <= t.
4. Lag census (R3, R8): for every state_changed True receipt T_s -- change type by diff against the previous accepted state row
   (score, out, half, pitcher, other; multi-label counted per label), lag to the first book receipt whose (yes_bid, yes_ask)
   differs from the last receipt before T_s, in 5 s bins [0,5) ... [295,300) plus never_within_300; book_leads = touch moves
   received in (T_e, T_s), T_e = last_play_ts via parse_venue_time (unparseable -> t_e_refused, counted); a prior receipt older
   than BOOK_AGE_S at T_s -> prior_book_stale. Beside it a book-change census: receipts with a touch change, a size-only change,
   and a volume_fp change without a touch change (answers register :255, whether volume_fp refreshes at book cadence).
5. Book-quality census per game: market_state-live receipts that are empty ladder, decided (a touch at 0.99 / 1.00 or mid
   outside the :75 band), one-sided (which side), both-sided -- split by state status at t (live / pre / final / absent).
6. regime_census_defs.py holds every constant as DATA with its register line (45, 15, 60 s; 1-2 c, >= 2 c, >= 3 c; 0.03 / 0.97;
   300 s; 30 / 120 s; 5 s bins; buckets) and IMPORTS BOOK_AGE_S, STATE_AGE_S, WINDOW_S, COVERAGE_PERCENT, MIN_DECISIONS,
   FILL_GAMES, SPORT_GAMES from forward_replay_qualification. V_lo is None ("frozen from 09-22 p25; not yet frozen"), so R5
   reports only its conditioning distribution (trailing-300 s delta volume_fp, count-by-decade, game-pooled) and its instants as
   threshold_unfrozen -- the census never computes a quantile and applies it. A required field absent on a row counts
   field_absent[regime][field], never a silent skip. No numeric literal other than 0 / 1 / 100 in regime_census.py (AST test).
7. Artifact: counts only, Decimal text, <= 3 examples per refusal reason (receipt, ticker, reason; repr <= 512 chars), < 1 MB
   per day, atomic, byte-identical under any input order; imported bars under "frozen_bars_read_only"; the defs SHA-256.
8. Memo: the orchestrator's real runs over 2026-09-22 and 2026-09-23 (paths, byte sizes, as_of, wall, peak working set, rows)
   VERBATIM; per regime, in Q6 vocabulary, instants and games with >= 1 instant against the register's floor (:89-90 "the floor is
   30 games with >= 1 regime instant") and the 32-126 game grid (:85-88); ends with the NEXT-ROW question: which regimes have
   enough instants AND games to be preregistered for a markout measurement on shards captured after the freeze commit. It answers
   by counts -- never a markout, a drift or a verdict.

TESTS (per-file; construct fixtures; the false-PASS risks): LOOK-AHEAD -- append later rows (a later touch move, a later state
change) and assert every earlier flag, episode and exclusion unchanged; PRINTS -- a trade row with created_time inside a window
changes nothing; THRESHOLD LITERAL -- AST scan of regime_census.py; ORDER -- shuffled input gives a byte-identical artifact and
identical episodes; TBNYY -- an empty ladder labelled live counts in book-quality, in no regime; plus R2 start / end and 60 s
score exclusion, R3 book_leads with bad last_play_ts, R6 one-sided vs decided, R8 30 / 120 s edges, field_absent, duplicate
receipt, 10,000-row bound (< 1 MB), memory-ceiling refusal, atomic-write failure.

CONTROLS: PREPARE only; the builder reads no real archive (fixtures only); the orchestrator alone runs the real shards and pastes
the counts; no markout, drift or fill; nothing wired into forward_replay, S390, S411 or any daemon.
DO NOT: edit any landed file or test; move or re-declare a frozen bar; derive, fit or print a proposed threshold from these
counts (freezing is a separate committed row); read trade prints or created_time; read raw_market prices; write data/ or
data/registry/; flip a flag; run the trial runner; state a market advantage or a currency amount; re-print a retracted number.

AMENDMENT 1 (2026-09-23 17:5xZ; binding; from round 1 -- Opus tier 2 REJECT (one blocker, five corrections) and codex sol
REJECT (three blockers, two corrections); both tiers found the absent-score gap independently). (a) EXCLUDED ROWS NEVER FEED THE CHAIN: snapshot_bulk rows are
excluded as field_absent yet still feed _chain, _lag_step and last_book (regime_census_fold.py:81-103, :107-133); their
prices come from raw_market (local_capture_runner_row.py:59-63) and they carry no sizes or market_state, so raw_market prices
reach touch_changes (the end of R3, book_leads, the lag bins) and null sizes reach book_changes (the R1 / R7 quiet windows,
size_only_change) -- a bulk-like row with the same touch moved size_only_change 0 -> 2 and switched R1 off; an all-absent row
produced touch_change 2 and a phantom [0,5) lag bin; the real run holds 27-30 such rows per game. RULING: a row excluded from
the population is excluded from the chain, the lag step and last_book too, and counted by its exclusion; only accepted
snapshot rows with ladder-derived fields advance any regime state; the real selection is run again after the fix and both
runs are recorded (BEFORE / AFTER). (b) A CHANGE ACROSS AN ABSENT-FIELD GAP IS COUNTED: score 0 -> absent -> 1 produced no
type_score and R8 = 0; half changing across an absent R2 row produced break_starts 0 (regime_census_state.py:153-177).
RULING: the comparison is against the LAST ROW WHERE THE FIELD IS PRESENT, the change is counted under
change_across_absent_gap by field, and no change is ever invented from an absent row; this is the candidate cause of MIACHC's
R8 = 0 (239 absent-score rows) and the AFTER run states what it becomes. (c) A touch move at a receipt equal to T_s is binned
[0,5) (or named lag_zero), never skipped so that the next unchanged receipt is binned as the move (:210-212). (d) The memo's
NOT VERIFIED bullet says the BUILDER read no shard (the orchestrator did); the real-run section quotes the artifact's numbers
VERBATIM (the MILPHI R2 share is 0.2363367799113737075332348597, never a rounding) and cites the artifact's path and SHA-256;
the NEXT-ROW section (CHANGE item 6) is written: games with >= 1 instant per regime against the register's 30-game floor and
its 32-126 fill-bearing-game grid -- every regime sits at <= 2 games on 2026-09-22, so no regime can be preregistered from
one day. NOTES: the artifact key adapter_verdicts is renamed adapter_outcomes (verdict wording is reserved); the dangling
comment at regime_census_state.py:158 removed; the three-module split (262 / 263 / 158 lines) is accepted; look-ahead,
R6 from row fields, decided rows excluded, prints never consumed -- all confirmed by tier 2 and unchanged.
(e) DECODE THROUGH THE LANDED READER: regime_census.py:46 reimplements the decode with json.loads; CHANGE item 1 requires the
landed forward_replay_io.read_jsonl. RULING: indexing is driven by read_jsonl (its yielded rows associated with byte offsets),
its refusals carried as named counts, and the native_rows differential kept. (f) FULL INPUT PATHS (contract A9): the artifact
stores only the schedule's basename and relative shard keys; it records the RESOLVED path and byte size of the schedule and
of every shard opened. (g) THE 2026-09-23 RUN: CHANGE item 8 requires both dates; the orchestrator runs the 2026-09-23
selection once its games have played (first start 22:35Z tonight) and records it verbatim; until then the memo names it
in NOT VERIFIED, and the round-2 verifiers judge the code and the 09-22 AFTER record without it. (h) A missing score field
must NEVER overwrite the last-complete score baseline (sol: scores [(0,0,0),(1,None,None),(2,1,0)] gave R8 0 / type_other 1
where removing the absent row gives R8 1 / type_score 1) -- the same defect as (b), pinned by that exact sequence.

AMENDMENT 2 (2026-09-23 19:1xZ; binding; from round 2 on fix 1b -- BOTH Opus tiers ACCEPT WITH CORRECTIONS; both reproduced every
AMENDMENT 1 closure on constructs and the two artifacts' SHA-256). ONE CODE CORRECTION: (a) an R8 window opens only from a score
increase on a LIVE state row (regime_census_state.py:370-373 ignored status: pre (0,0) -> pre (1,0) -> live opened a window);
the real artifact is unaffected (every MILPHI / MIACHC increase sits on a live row); one construct pins it. MEMO CORRECTIONS:
(b) the CHANGE VERSUS RUN 1 statement lists EVERY difference from the artifact diff verbatim -- type_score identical in both runs
and change_across_absent_gap {} in all six games (the gap fix changed nothing on this day); the pooled lag lost six outcomes
([230,235) -1, [295,300) -1, no_book_receipt_within_300 -4, one MIACHC entry now never_within_300); volume_change_without_touch_
change 55 -> 9 and 62 -> 9; R5 threshold_unfrozen 674 -> 622 and 703 -> 648 with a new no_trailing_300s_volume and the 1e2 decade
gone; prior_book_stale became no_prior_book on the three unserved games; book_leads changed and not_snapshot added; future_records
12669 -> 18753 because the 2026-09-23 shards GREW between the runs (books 92,522,159 -> 101,747,583 bytes; state 9,253,329 ->
9,695,297) -- 'same inputs' is replaced by 'same command; the visible rows equal; the next-day shards grew'. (c) MIACHC R8 = 0 HAS
A NAMED CAUSE, measured read-only by both tiers on game_key 824624 / ticker -CHC: the four live score increases (the first at
2026-09-23T00:44:20.955905Z) each have their next book receipt 3464 / 1343 / 561 / 287 s later -- the ticker's last snapshot is at
00:39:56.613883Z, sixty minutes after the 23:40Z start, i.e. the books capture's FOCUS WINDOW closed before the first run scored;
R8 = 0 is a coverage count, not a census defect; the stale 'score absent ... to be checked' READING is removed and change_across_
absent_gap {} is stated (the 239 absent-score rows are all pre-game). This is a finding for the register and the capture profile:
with a 3600 s focus window per game, no regime later than the first hour (R4 late-game, most of R8) can be measured by this
capture, and the memo's NEXT-ROW section says so. (d) The NEXT-ROW table is rebuilt from fix1b.json (R1 5 instants / 2 games) and
states literally that every regime sits at <= 2 games against the register's 30-game floor and its 32-126 grid. (e) Stale text
removed: 'AFTER pending', 'path / SHA missing', 'BEFORE counts only'. (f) The memo is condensed to <= 300 lines with the two real-run
records kept as compact verbatim tables. (g) Declared reading: an accepted one-sided row feeds the chain, the lag step and
last_book while counted in population_exclusions (a side vanishing is a book change; no effect on 2026-09-22 where no one-sided
row was accepted). (h) After the fix the orchestrator re-runs 2026-09-22 (AFTER-2 must equal fix1b.json in every count except
where (a) applies, which it does not on this day) and runs 2026-09-23 once its games have played; both recorded verbatim.
