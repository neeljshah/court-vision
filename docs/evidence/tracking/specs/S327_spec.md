GAP S327 | sport all | worktree aX | log cx_s327_prestart_m0_table

**DATA ROW (S register; the gate that three per-sport model rows stopped on).** `src/`, `kernel/`, `api/`
and `intel/` are READ and IMPORT only. Build in `scripts/platformkit/ingame/` and `domains/cross_sport_market/`.
NEVER write `data/registry/`, never flip a flag, never claim an edge (calibration language only), never edit a
landed memo, `docs/evidence/HARNESS_GAPS_2026-09-03.md` or `docs/evidence/RESULTS_LEDGER_SYSTEM.md`. Never
fabricate a quote; never substitute a rating for a market probability.

**WHERE THIS ROW RUNS:** LOCAL only (conda `basketball_ai` for every python call; print the interpreter
line; read every store in row-group batches -- the MLB price series has 13.5 M rows and the system python was
RAM-killed today loading it). Inputs: every pre-start / close capture store that exists locally:
`data/cache/combo/gate_corpus_nba_close.parquet` and `gate_corpus_mlb_close.parquet` (p_close, close_kind,
close_sec_after_tip), `data/cache/clv_close_legs_cache.jsonl`, the daemon capture stores behind
`data/cache/daemon_heartbeats/m16_prop_close_capture.txt`, `m17_kalshi_scan.txt`, `m18_pm_close_capture.txt`
(find their output paths from the daemon code under `scripts/`), `data/cache/book_depth/kalshi*`,
`data/cache/inplay_history/`, and the in-play price series `data/cache/inplay_odds/{nba,mlb,soccer,
soccer_intl,tennis}_price_series.parquet` (first tick per event as the last-resort proxy). Targets: the state
archives `data/cache/ingame/{mlb_pitch_states__*,soccer_states__*,tennis_states__*}.parquet` and
`nba_checkpoints_full.parquet`.

**WHY THIS ROW EXISTS.** On 2026-09-08 three per-sport model rows stopped INSUFFICIENT at the same premise:
S321 (NBA: no pre-start M0 column; 0/656 and 0/937 games), S325 (soccer: `p0` is Elo for all four leagues;
0 price joins), S326 (tennis: `p0` is walk-forward Elo; prices 2026-only, states end 2025; 0 overlap). The
program's M0 (last valid pre-start market-implied probability) is not archived as a table anywhere, although
several capture daemons and close corpora exist. Without an M0 table, bar C (astra 2026-09-08) cannot be
scored for any sport, so every model row is blocked on data plumbing, not on modelling.

**PREMISE (step 0, BINDING before-condition):** census every store above: path, n rows, date span, sports,
whether a PRE-START quote exists (a quote with timestamp < the event start, or `close_kind`), the event
key format, and the join fields (date, teams / player ids). PRINT the table. **If a per-sport pre-start M0
table with event keys joinable to the state archives already exists, the premise is FALSE: STOP, write the
memo, commit, report PREMISE FALSE.**

METHOD:
  1. **M0 TABLE BUILDER (`scripts/platformkit/ingame/prestart_m0_table.py`, <= 250 lines).** For each sport,
     emit `data/cache/ingame/prestart_m0__<sport>.parquet` (LOCAL, gitignored; the memo commits only its
     census) with: event_key (the state archive's game_id format), date, home, away (or player ids),
     p_prestart, quote_ts, start_ts, sec_before_start (negative = after start), source (store name),
     kind = PRE_START | AT_TIP (within 60 s after start) | FIRST_INPLAY (later first tick) | NONE, venue.
     Rule: prefer the latest quote strictly before start; else the earliest quote within 60 s after the
     start labelled AT_TIP; else the first in-play tick labelled FIRST_INPLAY. Team / player name mapping
     tables live in `domains/cross_sport_market/` (additive JSON; every unmapped key listed with n).
  2. **JOIN CENSUS.** Per sport x season: n events in the state archive, n joined with kind PRE_START / AT_TIP
     / FIRST_INPLAY / NONE, the median sec_before_start per kind, and the share of joined events whose
     `p0` (Elo) differs from p_prestart by > 0.05 (a plausibility screen, reported not gated). Table with n.
  3. **FORWARD CAPTURE PROPOSAL.** A <= 15-line PROPOSED change to the existing capture daemon(s) so the last
     pre-start quote per event is written to the same table going forward (soccer, tennis, MLB, NBA, WNBA);
     PROPOSED only (`docs/research/organization-sprint/S327_PROPOSED_prestart_capture.md`, gitignored; sha256
     in the memo). No daemon edit in this row.
  4. **TESTS.** A synthetic store with quotes before / at / after a known start: the builder picks the right
     kind and quote; an unmapped team is listed, never dropped silently; a rating column is never used.
  5. CHANGE NOTHING ELSE.

**HONEST LIMITATIONS to state, not discover:** AT_TIP and FIRST_INPLAY are proxies, labelled; venues differ
(kalshi / polymarket) and are not the sportsbook close; a 2026-only price archive cannot supply M0 for 2015-2025
tennis states or 2024-25 soccer states (report the empty cells; that is the finding); name mapping is manual.

ACCEPTANCE RULE:
  metric        = the store census; the per-sport x season join census with n per kind; the builder + tests;
                  the PROPOSED capture change
  before        = no M0 table; three model rows INSUFFICIENT on the same premise
  bar           = every store in the premise census is either used or excluded with a reason; the join
                  census covers every sport x season present in the state archives; kinds are labelled on
                  every joined row; tests pass; 0 ratings used as M0; 0 landed files edited
  n             = every event in every state archive; every store
  eye check     = NONE. Say that.
  must not move = every landed number; `src/`; the capture daemons; the registers/ledgers
  verdict       = **DONE** with the join census (empty cells are findings, not failures); **PARTIAL** with the
                  store that could not be read and why.
EVIDENCE: `docs/evidence/harness/S327_prestart_m0_table_2026-09-08.md` (<= 60 lines; VERDICT line 1; tables;
NOT VERIFIED; wall time; LF-normalised SHA-256s; the proposed ledger line
`2026-09-08 | data | S327 | <finding with n> | <VERDICT>`) + `store_census.csv`, `join_census.csv` under
`docs/evidence/harness/S327_prestart_m0_table_2026-09-08/` (each <= 5 MB; integer cells zero-padded).
TEST: `tests/platformkit/test_s327_prestart_m0_table.py`, alone. **NEVER a full pytest.** Every new file
<= 300 lines.
DIVISION OF LABOUR: the codex lane prepares the prereg (sealed alone: the selection rule, the 60 s AT_TIP
window, the mapping tables), the builder, the tests and the memo skeleton, and exits `PREPARED FOR FINISHER`
with the exact commands; it must NOT run the census on the real stores itself (Q1). Absent stores are
reported, never a stop.
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
