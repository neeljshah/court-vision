# S684 cloud result -- 2026-09-30 (desk-improve routine, ONE-OFF override pinned to S684, Opus, Ubuntu cloud clone)

Row: S684 (evaluation-subset honesty census; slate docs/evidence/harness/QUANT_GRADE_BUILD_SLATE_2026-09-30.md
section 2 row S684, override section 3a). Branch `cloud/S684-2026-09-30` from trunk e1b3bcdc.
Spec: docs/evidence/harness/S684_spec_2026-09-30.md (body + AMENDMENT 1 critic, 2 builder, 3 and 4 verifier corrections).
Register row and docs/operations/DESK_STATE.md NOT edited on this branch (override). REPORT-ONLY: no seal-pinned
file, PREREG, scoreboard or schedule receipt touched. Calibration language only; nothing here compares the desk
with any market beyond the receipt's own Brier numbers. PORTABLE: yes (code and construct tests); the real
multi-night run is WINDOWS (recorder box).

Agents: codex is not available in the cloud, so every review tier was an INDEPENDENT Opus sub-agent that did
not build the code (spawned with the Agent tool; each saw only the repo and its own prompt).

## Verdicts

| Tier | Agent | Verdict |
|---|---|---|
| Pre-build critique (astra) | independent Opus sub-agent | REVISE, 17 items -> all folded as AMENDMENT 1 |
| CONTRACT pass 1 (A, B1-B10, Q1-Q9 + spec) | independent Opus sub-agent | ACCEPT WITH CORRECTIONS (memo missing; C13 checked only 4 of the precedence order; non-Z hour; non-object liquidity) |
| ADVERSARIAL pass 1 (53 mutants, probes, fuzz) | independent Opus sub-agent | ACCEPT WITH CORRECTIONS (NaN crash, Brier > 1 bounded, forward/ symlink hole, 13 surviving mutants) |
| CONTRACT pass 2 (re-verify, final) | independent Opus sub-agent | ACCEPT WITH CORRECTIONS (memo wording of the test count only) |
| ADVERSARIAL pass 2 (71 mutants, re-verify, final) | independent Opus sub-agent | ACCEPT WITH CORRECTIONS (non-dict tick refused from the CLI; null liquidity accepted; 4 test gaps) |

Pass-2 corrections were applied as AMENDMENT 4 (two one-line code guards plus tests), with no third verify
round because the limit is one re-verify. After A4 the builder re-ran the pass-2 survivors: N5, N5b, N6,
N8e, N8f, N8g and null-liquidity all turn the file red. N9 (main catching only ValueError/OSError)
still survives. It looks equivalent after A3/A4, since no reachable input raises TypeError or
AttributeError into main any more, but no verifier re-checked that.

## PREMISE (Q8, re-measured on trunk e1b3bcdc)

PREREG_2026-09-24.json: "no maximum age is enforced by this row". PREMISE HOLDS.

## 09-24 census (tracked receipt; docs/evidence/subset_census/S684_census_2026-09-24.json)

Inputs (A9): docs/evidence/forward/scoreboard/2026-09-24.json 3,443,097 bytes; the full_selection schedule
1,159 bytes; its .census.json 4,585 bytes; sha256 of each is in the receipt. The CONTRACT tier regenerated the
receipt byte-identical twice on Ubuntu with the same raw inputs and serializer.
On Windows, the 09-24 scoreboard bytes match that receipt (3,443,097 bytes;
sha256 2f8a2a7d6b4c2d80466520ccce4e3442fe22cbff57039450acf94e82d959ef06),
but the schedule is 1,197 bytes and its census is 4,769 bytes because their checked-out
line endings differ. Their local sha256 values are
b04e490f7241f45209bf7323a3f316e91535a8f1819f6c1f1c8485bd746d325d and
6791a855d59359c282261c29fc36a1c104ad28e5e36624a585d6f16942f52fe3, respectively.
Windows paths also use backslashes, and the previously tracked receipt has CRLF. The
computed `nights` object is identical across these inputs; raw provenance and serialized
bytes are platform dependent. The compact regeneration retains the hashes and sizes of
the bytes actually read on the host that writes it.

Arm A book age (ticks[].mid_age_us), mlb, 1,991 scored ticks, 4 games (every game has ticks in every bucket):

| Bucket | <= 5 s | <= 30 s | <= 5 min | older | unknown |
|---|---|---|---|---|---|
| ticks | 461 | 59 | 352 | 1,119 | 0 |
| share | 0.2315 | 0.0296 | 0.1768 | 0.5620 | 0 |

So 56.2 pct of the scored ticks on 09-24 used an arm A mid older than 5 minutes. Receipt counts pass through:
tick_refused:book_absent 23, model_state_refused 343.

Coverage: schedule universe (full_selection, denominator of record) 4 games, covered 4, uncovered 0,
out_of_universe 0 -> "no uncovered games". Census universe (games_seen minus outside_utc_date) mlb N = 9, and nfl 0
(no nfl universe). Liquidity: UNKNOWN (no tracked source).

Status per universe: 96 rows (48 cells x Brier/log loss). 12 are BOUNDED and 84 WITHHELD: no_eligible_ticks 48,
unbounded_loss 16, contrast_not_bounded 16, target_is_arm_input 4. The 4 top-level contrasts rows are all
contrast_not_bounded. The bound is a worst-case (loss 0 or 1 for every unobserved game) interval on the
GAME-WEIGHTED Brier over the universe. The headline tick-weighted mean is not bounded. The schedule universe equals the
selection on 09-24 (SELECTION_EQUALS_UNIVERSE), so its intervals do not measure bias against the broader slate.
The census interval is the informative one.

| Arm | Segment | Target | Ticks | Games | Tick-weighted | Game-weighted | Fresh share | Schedule (N=4) | Census (N=9) |
|---|---|---|---|---|---|---|---|---|---|
| A | pre-live | outcome | 572 | 3 | 0.3619 | 0.3545 | 0.0052 | [0.2659, 0.5159] | [0.1182, 0.7848] |
| B_lag | pre-live | outcome | 548 | 3 | 0.3622 | 0.3545 | 0.0055 | [0.2659, 0.5159] | [0.1182, 0.7848] |
| B_lag | pre-live | mid | 548 | 3 | 0.0000 | 0.0000 | 0.0055 | [0.0000, 0.2500] | [0.0000, 0.6667] |
| A | early | outcome | 597 | 4 | 0.3275 | 0.3055 | 0.7337 | [0.3055, 0.3055] | [0.1358, 0.6914] |
| B_lag | early | outcome | 596 | 4 | 0.3279 | 0.3052 | 0.7349 | [0.3052, 0.3052] | [0.1357, 0.6912] |
| B_lag | early | mid | 596 | 4 | 0.0001 | 0.0001 | 0.7349 | [0.0001, 0.0001] | [0.0000, 0.5556] |
| A | middle | outcome | 386 | 4 | 0.2998 | 0.2826 | 0.0415 | [0.2826, 0.2826] | [0.1256, 0.6812] |
| B_lag | middle | outcome | 386 | 4 | 0.2662 | 0.2550 | 0.0415 | [0.2550, 0.2550] | [0.1133, 0.6689] |
| B_lag | middle | mid | 386 | 4 | 0.0049 | 0.0042 | 0.0415 | [0.0042, 0.0042] | [0.0018, 0.5574] |
| A | late | outcome | 436 | 4 | 0.0947 | 0.0871 | 0.0092 | [0.0871, 0.0871] | [0.0387, 0.5943] |
| B_lag | late | outcome | 436 | 4 | 0.2100 | 0.1937 | 0.0092 | [0.1937, 0.1937] | [0.0861, 0.6416] |
| B_lag | late | mid | 436 | 4 | 0.0434 | 0.0399 | 0.0092 | [0.0399, 0.0399] | [0.0177, 0.5733] |

Reading: on 09-24 every census interval is wider than 0.45. At N = 9 with n <= 4, the selected subset
cannot pin the full-slate game-weighted Brier. The fresh share is below 5 pct in every segment except early. This is
SINGLE-WINDOW (one night, one sport). No max-age rule is proposed here. Any proposal goes to the arm A owner's next
prereg amendment.

## Files (all NEW; git diff e1b3bcdc..branch has additions only)

- scripts/platformkit/evidence/subset_census.py (222 lines): the CLI and the per-night census.
- scripts/platformkit/evidence/subset_census_bound.py (125 lines): the buckets, the reason precedence and the bound.
- tests/platformkit/evidence/test_subset_census.py (300 lines): 13 functions, 15 collected tests, cases C1-C19 (CONSTRUCT).
  On trunk code it fails at collection (ImportError), per the CONTRACT tier.
- docs/evidence/subset_census/S684_census_2026-09-24.json (the receipt). It is not under harness/, because harness/** ignores *.json and force flags are forbidden.
- this memo and the spec.

## Tests (one file per process)

| Command | Result |
|---|---|
| `python3 tools/desk_bin/run_files.py . tests/platformkit/evidence/test_subset_census.py` | 15 passed (final branch) |
| `python3 tools/desk_bin/run_files.py . tests/platformkit/test_loc_rail_scope.py` | 1 passed |
| `python3 tools/desk_bin/run_files.py . tests/platformkit/evidence/test_exec_evidence_series.py` | 5 passed (neighbour, unchanged) |
| `python3 tools/desk_bin/run_files.py . tests/platformkit/test_s140_loc_rail.py` | 1 failed / 2 passed, identical on trunk (ModuleNotFoundError statsmodels in this clone; pre-existing, not S684) |

Regenerate the receipt with:
`python3 -m scripts.platformkit.evidence.subset_census --scoreboard docs/evidence/forward/scoreboard/2026-09-24.json --universe docs/evidence/forward/schedules/2026-09-24_maker_forward_full_selection.json --out <path>`.
Compare the parsed `nights` object with the tracked receipt and verify each input hash and
size against the local raw file. Serialized bytes can differ by platform. An --out under
docs/evidence/forward/ is refused.

## Filed as suggestions (not rejections)

- A tick-weighted bound needs per-game expected tick counts for uncovered games (a qualification-side field).
- A tracked per-game liquidity source for the whole slate, so the liquidity comparison is not UNKNOWN.

## NOT VERIFIED

- The real per-bucket counts and bounds for every night other than 09-24. Nights 09-22, 09-23 and 09-25 onward
  (including 09-29 and 09-30) have no scoreboard receipt in the clone; the receipts live on the recorder box. The
  real run is WINDOWS: one night at a time, following the slate's 400 MiB cap.
- Census-universe N for non-MLB sports (09-24 has no scored nfl game, and nfl N = 0).
- Liquidity for covered and uncovered games (UNKNOWN; no tracked source).
- Tick-coverage-within-game (the 12-32 pct COVERAGE_LOW figure). This is out of scope; qualification owns it.
- Landing on trunk and Windows per-file runs. A laptop session lands the branch.
- The N9 mutant equivalence claim (builder's reading; not re-verified by a tier).
