# S679 cloud result -- 2026-09-30

Row: S679 (governance: reviewer-independence ledger field), QUANT-GRADE slate rank 23, run as the section 3a
one-off override. Branch: `cloud/S679-2026-09-30` from trunk 89218a73. Commits: 4b0ef696 (build and spec),
8f0cf963 (fix round 1), then a docstring wording fix and this memo.
Spec with AMENDMENT 1: `docs/evidence/harness/S679_spec_2026-09-30.md`. Machine: cloud clone, Python 3.11.15.

## Status: BUILT, VERIFIED (both tiers ACCEPT WITH CORRECTIONS; fixes re-verified ACCEPT). Not landed. PORTABLE: yes.

## Premise (Q8, measured before any edit)
CONFIRMED. The measured file is `docs/evidence/RESULTS_LEDGER_SYSTEM.md` at 89218a73:
- sha256 d11634a02c66a630f053fcc7105e124b5ae604b4c6f87f4195a615f3c5513667
- 927 lines, 917 dated data lines, dated 2026-09-01..2026-09-30

0 of the 917 lines match `human[:=] ?none`, and the two `review:` hits (lines 657 and 667) are free prose. The
ledger does not say that its reviewers are model agents working under one operator.

## Change (new files only; the ledger is NOT edited on this branch)
- `scripts/platformkit/ledger_audit/ledger_review_lint.py` (180 LOC). A read-only linter; CLI
  `python -m scripts.platformkit.ledger_audit.ledger_review_lint [--ledger P]`. Exit codes: 0 clean,
  1 violations, 2 unreadable. It never writes a file.
- `tests/platformkit/ledger_audit/test_ledger_review_lint.py` (182 LOC, 46 construct cases).
- `tests/platformkit/ledger_audit/fixtures/s679_results_ledger_system_89218a73.md.gz`: a frozen snapshot of the
  ledger (gzip of the exact bytes above, 332,689 B).

Token (additive text; no column is added, renamed or repurposed, per contract B2):
`[review: tiers=contract+adversarial; family=claude-opus; human=none]`

The token must be the last text of the second-to-last field, so a line ends `...] | <commit>`. The row's
`human: none` is written as `human=none` inside the token (AMENDMENT 1 item 10).

Slugs have the form [a-z0-9][a-z0-9.-]*. `none` never appears in a list with another slug. A slug may not
contain any of the following, because each would move a reader's count:
- an S-id
- a run of 7-40 hex characters
- `verified`, `landed`, `deployed` or `applied`

Scope and cut:
- Every dated line is checked when it is dated 2026-10-01 or later, or when it follows (in file order) the
  first such line.
- The one exemption is the exact six-field auto line that `ledger_hook.py:65` writes.
- Violation codes: MISSING, MALFORMED, DUPLICATE, TOKEN_IN_COMMIT_FIELD, TOKEN_MISPLACED, FIELD_COUNT (fewer
  than 5 fields), BAD_DATE.
- BAD_DATE is not bound to the cut. It flags a date that is not on the calendar and, after the first data
  line, any row containing ` | ` that is not a dated data line. The real ledger has 0 of either.

Readers checked (A5). Using the token in the specified position changes nothing that any of these extract:
- `ledger_sha_audit.py`: DATA_RE, SHA_RE, SID_RE, fields[-1]
- `usage_dashboard.sh:25,28`: `$NF`, the `| hook |` grep, the verified count, the `| (LANDED|ACCEPT)` and
  `| (REJECT|...)` greps
- `loop_status.sh:37-38`: row count and ship count
- `ledger_hook.py:63`: sha dedup
- `tools/desk_bin/harness_tools/land_generic.py`
- the lander and verifier prompts

## Tests (one file per process)
| command | result |
|---|---|
| `python3 tools/desk_bin/run_files.py . tests/platformkit/ledger_audit/test_ledger_review_lint.py` | 46 passed |
| `python3 -m scripts.platformkit.ledger_audit.ledger_review_lint` (tracked ledger) | exit 0: data_lines=917 pre_cut=917 checked=0 violations=0 |
| `python3 tools/desk_bin/run_files.py . tests/platformkit/test_loc_rail_scope.py` | 1 passed |

Acceptance, as the row states it:
- A new line dated 2026-10-01 without the token is rejected (MISSING).
- All 917 older lines pass without being edited.
- The ledger's bytes are the same before and after a run.

Mutants, each confirmed by at least one tier and by the builder: M1 (backdating guard) 1 red, M2 (every hook-area
line exempt) 4, M3 (token accepted anywhere) 1-2, M4 (cut 09-01) 9-10, M4b (cut 10-02) 9-10, M5 (`none` in a
list) 2, M6 (exempt on the marker alone) 5. Also red: every slug guard, each hook-shape sub-condition,
FIELD_COUNT, MIN_FIELDS=6, TOKEN_MISPLACED, DUPLICATE, both BAD_DATE branches, the BOM strip, and splitlines
in place of the LF split. Equivalent mutants (all cases stay green, by construction): the trailing `\r` strip,
because every field is stripped, and utf-8 in place of utf-8-sig in main, because lint_text strips the BOM too.

The ledger, HARNESS_GAPS_2026-09-03.md, DESK_STATE.md, scripts/platformkit/tracking/ and tools/desk_bin/ are
byte-identical to 89218a73 (`git diff --quiet`).

## Verifier tiers (independent Opus sub-agents; codex is not available in the cloud; the builder did not verify itself)
- **Pre-build critic: REVISE, 12 items**, all folded into AMENDMENT 1:
  - frozen snapshot fixture
  - token placement and reserved slugs
  - exact hook shape
  - cut-boundary cases
  - BAD_DATE
  - backdating limit named
  - CRLF
  - premise count corrected 928 -> 927
  - `human=` form
  - FIELD_COUNT
  - deliberate over-inclusion stated

  With AMENDMENT 1 the spec runs to 53 lines. The template's 40-line cap applies to the dispatched spec, which
  was 35 lines.
- **CONTRACT tier (A/B/Q plus the spec): ACCEPT WITH CORRECTIONS.** It reproduced 37/37, the CLI, the snapshot
  sha and M1-M6 + M4b. Corrections:
  - (1) this memo was missing (A7); it is now written.
  - (2) slugs `landed`, `redeployed` and `applied` would move the loop_status.sh:38 ship count; FIXED.
- **ADVERSARIAL tier: ACCEPT WITH CORRECTIONS.** 33 mutants, 29 killed. Survivors:
  - `\r` strip: equivalent
  - MIN_FIELDS=6: FIXED (5-field case added)
  - `human=` accepting a list: FIXED
  - no guard on the human slot: FIXED

  It ran 23 probes. Corrections applied: BAD_DATE scope stated in the docstrings; lines split on LF like the
  line-based readers; a leading BOM ignored, which closes the post-cut line-1 escape.
- **Fix-round re-verification** (a fresh Opus sub-agent, contract and adversarial combined): **ACCEPT**. 46/46.
  Every spec mutant and every survivor mutant is red. It raised one wording nit about BAD_DATE's scope, which
  the docstring now fixes. The fix was checked by the builder only (46 passed).

## Named limits (NON-TAUTOLOGY)
- The linter checks that the token is present and well-formed. It cannot tell whether `human=none` or the tier
  list is TRUE.
- Backdating is guarded only after the first line dated on or after the cut. A first October line dated
  2026-09-30 or earlier escapes. Producers already use different clocks: the hook uses local time,
  land_generic uses UTC, and hand-written prose uses the program day.
- A hand-written line in the exact hook shape escapes the token check. The exemption is decided by the line's
  shape, not by where it came from.
- Some lines look like data but are not data lines under `^\d{4}-\d{2}-\d{2}\s*\|` and are skipped: a line
  with no pipe, `x|y` without spaces, or full-width pipes.
- Every line dated after the cut is checked, including ops lines that carry no verdict. This over-inclusion
  is deliberate (AMENDMENT 1 item 12).

## NOT VERIFIED
- The effective-date cut on the laptop copy of the ledger. It has an uncommitted owner edit, which this clone
  cannot see. A laptop run of the CLI must show violations=0 before any line dated on or after 2026-10-01 is
  appended.
- The Windows / Py3.10 run. The code is stdlib-only and path-agnostic, but it was not run there.
- Wiring. Nothing calls the linter: no hook, tick, pre-push or lander step. Wiring it is a later laptop step.

## NEW GAP lines (no id allocated; ids come from NEXT_GAP_ID only)
- NEW GAP: the producers do not write the token yet: land_generic.py and the lander and verifier ledger-line
  templates. The first non-hook line dated 2026-10-01 or later will fail the linter until they do.
- NEW GAP: the hook exemption is decided by shape, not by provenance.
- NEW GAP: rows that look like data but fail the data-line regex are not checked after the cut.
