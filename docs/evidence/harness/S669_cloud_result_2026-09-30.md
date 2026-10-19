# S669 cloud result (2026-09-30) -- risk_receipt

Row: S669 (risk receipts), slate QUANT_GRADE_BUILD_SLATE_2026-09-30.md section 2, one-off override section 3a.
Branch: cloud/S669-2026-09-30, started FROM origin/cloud/S666-2026-09-30 (S666 risk_delta is not on trunk yet;
S669 imports it read-only). S667 / S668 are built in parallel elsewhere; this branch touches none of their files.
PORTABLE: yes (code + construct tests on the Ubuntu cloud clone; fixtures only, no data/, no venue or sports host).
Execution-quality measurement only: contracts, seconds, probability points per contract. No claim of any kind
about performance against a market.

## Verdicts

| tier | who | verdict |
|---|---|---|
| pre-build critic | independent Opus sub-agent | REVISE, 20 items, all folded as AMENDMENT 1 in the spec |
| CONTRACT (A/B/Q + spec) | independent Opus sub-agent, did not build | ACCEPT WITH CORRECTIONS (0c470a7c) |
| ADVERSARIAL (probes + 26 mutants) | independent Opus sub-agent, did not build | ACCEPT WITH CORRECTIONS (0c470a7c, re-checked 226732f4) |

Codex is not available in the cloud; each tier was a separate Opus sub-agent with no build role. Neither
tier returned REJECT, so no second verification round was due. The corrections were applied by the builder
in commits 226732f4 and the memo commit, re-run per file, and the adversarial survivors were re-mutated by
the builder in a scratch copy (all now killed, table below). The corrections themselves were NOT
re-verified by a third independent agent.

## What was built (new files only)

- scripts/platformkit/execution/risk_receipt.py -- per (night, family) receipt: per game peak / time-average
  absolute inventory, band seconds and shares, time in breach, worst-cell and net-delta paths (risk_delta),
  opportunities, refusals by scope with shares, cap_bound, fill share, markout, breakers, quote reasons,
  reconciliation.
- risk_receipt_replay.py -- PaperAccount subclass replay (log_path=None, input log never rewritten), scope
  attribution of cap_refused (per_order / per_ticker / per_game / global), reconciliation against the log's
  RECORDED outcomes.
- risk_receipt_marks.py -- fill-weighted markout at 10 s / 60 s / settle (markout_causal, gross of fees),
  Decimal game-cluster bootstrap (seed 7, 5,000 draws), INSUFFICIENT under 30 games; breaker latency
  (nearest rank p50 / p90, max); reason counts.
- risk_receipt_io.py -- append-only atomic ASCII sorted-key JSONL (temp + fsync + os.replace + dir fsync;
  identical line no-op, differing line for a key refuses, both files pre-checked before any write), sidecar
  (limit-table sha256, input sha256 + bytes by basename, code sha256), full-path currency-key guard, CLI.
- tests: test_risk_receipt.py, test_risk_receipt_io.py, _s669_fixtures.py. Spec: S669_spec_2026-09-30.md.

`git diff --stat origin/cloud/S666-2026-09-30 HEAD` lists new files only; paper_account.py,
paper_account_log.py, position_caps.py, position_exposure.py, position_reducers.py, risk_delta.py,
markout_causal.py, markout_causal_windows.py, exec_policy_stats.py and every seal-pinned file are unchanged.

## Tests (one file per process), final head

- `python3 -m pytest tests/platformkit/execution/test_risk_receipt.py -q -p no:cacheprovider` -> 27 passed
- `python3 -m pytest tests/platformkit/execution/test_risk_receipt_io.py -q -p no:cacheprovider` -> 27 passed
- `python3 -m pytest tests/platformkit/test_loc_rail_scope.py -q -p no:cacheprovider` -> 1 passed

Before: module absent (import fails), so every construct test fails on the old code.

## Construct cases (n = enumerated, CONSTRUCT)

Hand-computed 2-game fixture (_s669_fixtures.night_receipts; recomputed independently by the CONTRACT tier):
g1 peak 3 at t10, time-average (3x40 + 2x50)/100 = 2.2, bands 0 = 10 s, 1-4 = 90 s; g2 window [20, 60]
(last receipt), average 2x35/40 = 1.75; opportunities 4, fills 3, fill share 0.75, reserve refusal share 0.25,
cap_bound per_game; markout 10 s (3x5 - 1x5 - 2x2)/6 = 1.0, 60 s = 10.0 (2 no_tick_in_window),
settle (3x60 - 1x55)/4 = 31.25 (1 game_end_missing); breach 50 s against a declared g1 limit of 2.
Other cases: recorded-outcome reconciliation, tampered log -> MISMATCH with RECORDED totals reported,
different caps -> MISMATCH, input log byte-identical after a run, per_ticker-only refusal, multi-scope
refusal, NONE cap_bound, after_game_end (and a receipt exactly at game_end is inside), zero-length window
-> NOT_SUPPLIED, band edges, 29 games INSUFFICIENT / 30 games interval (pinned), leg-map delta and
worst-cell paths, breaker latency with a negative latency counted, night-level vs family rows, missing
inputs NOT_SUPPLIED (never 0), limit-table refusal shares, permutation invariance, malformed line and
invalid family counted (night_unattributed_outcomes), fill share by distinct order, max_wait window,
two families, settle mark_not_after_fill; currency-key guard (real receipt clean, 9 mutant keys refused,
markout level and nested lists checked, whole-token match, full-path exemption), append-only conflict,
torn file, fsync/replace order, CLI byte-identical re-run with sidecar hashes, CLI conflict writes nothing,
ASCII outputs.

## Corrections applied after the tiers

1. Reported n_fills and refusal totals now come from the log's RECORDED outcomes (A1.18); replay values are
   kept beside them as *_replayed; by_scope stays replay-attributed (meaningful when reconcile is OK).
2. `markout` removed from the data-keyed exemptions; exemptions are now full paths, not key names
   (a schema key named `invalid` under `units` is checked).
3. Bootstrap sums in Decimal (A1.9).
4. Zero-length window -> time_in_breach_s NOT_SUPPLIED (A1.8).
5. Night-level unattributed outcomes (malformed_line, invalid_family) in every family receipt.
6. A per-receipt copy of UNITS (a mutation test exposed that receipts shared the module dict).
7. Tests added for adversarial survivors M7, M12/M15, M16, M18, M19, M21, M25, M26; builder re-mutation in a
   scratch copy: M12, M16, M18, M21, M25, UNITS alias, zero-window breach -> all killed.

## NOT VERIFIED

- Reconciliation against a real paper_account receipt log (no data/ in the clone).
- The fill-refusal scope branch (risk_receipt_replay.py `_refusal_scopes` fill path, mutant M13): neither the
  builder nor the adversarial tier could produce a fill `cap_refused` through PaperAccount under consistent
  caps (reserves already count open quantity in the worst case), so the branch is untested.
- time_in_breach_s is structurally 0 under the replay caps; it carries information only when an S667
  limit table is passed as breach_limits (S667 not landed).
- S667 limit_refusals and S668 breaker_trips input shapes are declared here, not matched to the built
  S667 / S668 outputs.
- No runtime caller; no wiring into any runner.

## NEW GAP lines (for the orchestrator; no id invented)

- NEW GAP: receipt append and sidecar append are two separate atomic steps; a crash between them leaves a
  receipt without its sidecar (both are pre-checked, so a conflict never half-writes).
- NEW GAP: breach time is meaningful only with an S667 table; add breach_limits to the S667 landing.
