GAP S323 | sport all | worktree aX | log cx_s323_adapter_contract_leak_test

**HARNESS ROW (S register; astra 2026-09-08 "one harness, many adapters").** `src/`, `kernel/`, `api/` and
`intel/` are READ and IMPORT only. Build in `scripts/platformkit/eval_gate/` and `domains/<sport>/`. NEVER
write `data/registry/`, never flip a flag, never claim an edge (calibration language only), never edit a
landed memo, `docs/evidence/HARNESS_GAPS_2026-09-03.md` or `docs/evidence/RESULTS_LEDGER_SYSTEM.md`.

**WHERE THIS ROW RUNS:** LOCAL only (conda `basketball_ai`; print the interpreter line). Inputs: the NBA
checkpoints parquet (`data/cache/inplay_odds/nba_checkpoints_full.parquet`, read columns) and the MLB /
soccer / tennis in-play price parquets under `data/cache/inplay_odds/` (read columns; report which exist).

**WHY THIS ROW EXISTS.** Every per-sport model row (S321 NBA, MLB base-out, soccer remaining-goal, tennis
serve/set recursion, KBO/NPB, cross-sport pooling) needs the SAME evaluator with sport-specific state, and the
landed harness has no declared adapter contract: S295 found `walkforward.py` leaves strict redaction off by
default and callbacks can close over raw arrays; S301 added the duplicate-key guard; S304 the as-of joiner
guards. Without a contract, every new sport re-discovers the leak surface. This row writes the contract, a
validator, and the planted-leak test that proves an adapter is honest, then measures which fields each
existing corpus can supply (the honest census that gates the non-NBA rows).

**PREMISE (step 0, BINDING before-condition):** grep `scripts/platformkit/eval_gate/` and `domains/` for an
existing adapter schema / contract (`file:line`); print the columns of each in-play parquet found. **If a
declared multi-sport adapter contract with a validator and a planted-leak test already exists, the premise
is FALSE: STOP, write the memo, commit, report PREMISE FALSE.**

METHOD:
  1. **CONTRACT (`scripts/platformkit/eval_gate/adapter_contract.py`, <= 250 lines).** A typed schema (plain
     dataclasses / a dict spec, no new dependency): sport, league, rule_version; canonical game_id, team ids;
     season, corpus; target_id, line, class_order, settlement_rule, void_rule; event_id, sequence;
     event_time, received_at, feature_available_at, prediction_at; a per-sport state block (period/clock OR
     inning/base_out/count OR point/game/set/server); score, status, unknown_flags, provenance; M0 with
     source and time; ML with source and time; candidate and null probability vectors; outcome with
     known_at; state_key; exclusions; weights; fold_id; input/code/seal hashes. Labels live in a separate
     frame from features. Grain: one oriented target per venue per tick; paired sides merged; whole-game
     grouping; each adapter declares its maximum feed delay for the embargo.
  2. **VALIDATOR (`validate(features, labels) -> report`)**: required fields present, monotone times
     (received_at <= feature_available_at <= prediction_at < known_at), duplicate keys (S301), cross-fold
     duplicate games, paired-side conflicts, unknown-flag rules; returns ACCEPT or a list of violations.
  3. **PLANTED-LEAK TEST (`test_s323_adapter_contract.py`).** Inject: a next-event field with future
     availability; a final-outcome field disguised as a feature; a duplicate game across folds; a future
     raw outcome with a forged early timestamp (caught only by truncation replay: predictions on the prefix
     must be byte-identical); a clean control. Bar: every injection rejected before fitting; the clean
     control accepted; prefix predictions byte-identical (wire through `walkforward.py` with strict
     redaction on -- a PROPOSED default change for S295 stays proposed).
  4. **ADAPTERS + CENSUS.** `domains/basketball_nba/ingame_adapter.py` mapping the NBA checkpoints parquet to
     the contract (<= 200 lines; runs the validator on the real frame, n ticks / n games / n violations);
     for MLB, soccer and tennis parquets a census-only adapter that reports each contract field as
     AVAILABLE / DERIVABLE / UNAVAILABLE with n (never fabricate M0 or outcomes; soccer/tennis lack
     games.parquet -- state it). Table: sport x field.
  5. CHANGE NOTHING ELSE; no landed evaluator default changes.

**HONEST LIMITATIONS to state, not discover:** timestamp validation cannot certify a feed that rewrites its
history; the census is field presence, not data quality; the NBA adapter is the only one that can be
validated end to end today.

ACCEPTANCE RULE:
  metric        = premise prints; the contract; the validator report on the NBA frame (n); the planted-leak
                  test results (5 cases); the sport x field census table with n
  before        = no declared adapter contract; leak guards scattered across S295/S301/S304
  bar           = 5/5 planted cases behave as specified (4 rejected, 1 accepted; prefix byte-identical); the
                  NBA adapter validates with every violation listed (n); the census covers every contract
                  field for every parquet found; all tests pass; 0 landed defaults changed
  n             = every contract field x every parquet found; the full NBA frame
  eye check     = NONE. Say that.
  must not move = every landed number and default; `src/`; `data/`; the registers/ledgers
  verdict       = **DONE** if the bar holds; **PARTIAL** with the item that failed and why.
EVIDENCE: `docs/evidence/harness/S323_adapter_contract_2026-09-08.md` (<= 60 lines; VERDICT line 1; tables;
NOT VERIFIED; wall time; LF-normalised SHA-256s; the proposed ledger line
`2026-09-08 | harness | S323 | <finding with n> | <VERDICT>`) + `census.csv`, `nba_validation.csv` under
`docs/evidence/harness/S323_adapter_contract_2026-09-08/` (each <= 5 MB; integer cells zero-padded to 6 digits).
TEST: `tests/platformkit/test_s323_adapter_contract.py` plus `scripts/platformkit/eval_gate/test_walkforward.py`
and `test_leak_contract.py`, each alone. **NEVER a full pytest.** Every new file <= 300 lines.
DIVISION OF LABOUR: the codex lane prepares the prereg (sealed alone: the field list, the five planted cases,
the census rule), the contract, the validator, the adapters, the tests and the memo skeleton, and exits
`PREPARED FOR FINISHER` with the exact commands; it must NOT run the real-frame validation or census (Q1).
COMMIT: explicit pathspec only. ASCII stdout. Prereg sealed as its OWN commit first (embed the seal: last
line `SEAL sha256 <hex>` over the LF-normalised bytes above it). **NEVER PARK.**

VERSION 2026-09-08
