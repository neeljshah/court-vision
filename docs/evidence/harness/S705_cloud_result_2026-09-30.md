# S705 cloud result -- 2026-09-30 (continuous disk + log guard)

PAPER ONLY. Calibration and ops language only. Row: S705 (docs/evidence/harness/
AUTOMATED_PAPER_DESK_ARCHITECTURE_2026-09-30.md section 2; one-off override section 3a).
Branch: `cloud/S705-2026-09-30` (from trunk bb34a09c). Commits:
- b5050b33: build
- b107ff6a: fix pass 1
- the correction commit that carries this memo.

Spec + AMENDMENT 1: `docs/evidence/harness/S705_spec_2026-09-30.md`. Machine: cloud clone,
Python 3.11.15. No network host was contacted, nothing under data/ was written, and no register
or DESK_STATE edit was made.

## Status: BUILT, VERIFIED -- both tiers ACCEPT WITH CORRECTIONS (after one REJECT + one fix pass). Not landed.

## Premise (Q8, re-measured before any edit): CONFIRMED
- `capture_supervisor.py:204-212` reads free space only when a child starts (including restarts
  after backoff), against a 2000 MiB floor.
- `tools/desk_bin/hidden_launch.py:23` opens `--log` with `"ab"` and never bounds its size.
- No `ops/disk_guard.py` existed.

## Change (new files only; every must-not-move file is byte-identical to bb34a09c)
- `scripts/platformkit/ops/disk_guard.py` (219 LOC). It declares integer thresholds in decimal
  bytes:
  - disk warn below 10 GB free, refuse below 5 GB free (above the supervisor's 2000 MiB floor)
  - log growth warn above 50 MB/h
  - archive growth warn above 1.5 GB/day
  - rate interval must be 60 s to 2 days
  - receipt size cap 64 KiB

  `evaluate()` is pure and returns `{decision ok|warn|refuse|unknown, reasons[], defer_night,
  log_growth, rotation_proposals[], skipped[]}`. `defer_night` is True only on `disk_refuse`.
  A missing input is `unknown`, never 0 and never a refusal (B3). `run()` reads through injected
  seams (`disk_usage`, `stat`, `scan`, `realpath`) and writes only the ASCII receipt (unique temp
  file in the same directory, fsync, then `replace_with_retry`). A receipt that is protected,
  outside the root, or a symlink is refused and recorded as `receipt_write_failed`.
- `scripts/platformkit/ops/disk_guard_paths.py` (99 LOC):
  - Protected check: casefolded COMPONENT prefixes `("docs","evidence")` and `("data",)`. It
    checks both the lexical path and the native realpath, and applies to the base log and to
    every sibling `.1` to `.5`.
  - Rotation plan: a shift in the style of RotatingFileHandler. It is a PROPOSAL only, with
    `precondition: writer_stopped`.
  - The guard never deletes, renames or truncates anything.
- `docs/evidence/harness/S705_tick_hook_PROPOSED_2026-09-30.md` (NOT APPLIED) covers three things:
  - the nights-only gate in `paper_desk_tick.py`
  - relocating `--log` to `logs\desk\` (gitignored at `.gitignore:180`)
  - the owner procedure for carrying out a proposal between launches
- Tests: `tests/platformkit/ops/test_disk_guard.py` (249 LOC) and `test_disk_guard_paths.py`
  (153 LOC).

Consequence to state plainly: the three real hidden-launch logs sit under
`data\cache\capture_supervisor\`. The run override protects that path, so the guard size-reads
those logs for the growth rate but never proposes rotating them. **In production the rotator is
INERT until the PROPOSED relocation lands.**

Doc correction (contract tier): `evaluate()` takes no `root` argument, unlike the spec body
signature. The path check lives in `observe()` and `classify()`. After fix pass 1, `evaluate()`
proposes only rows that `observe()` marked `checked=True`.

## Tests (one file per process, final tree)
| command | result |
|---|---|
| `python3 tools/desk_bin/run_files.py . tests/platformkit/ops/test_disk_guard.py` | 54 passed |
| `python3 tools/desk_bin/run_files.py . tests/platformkit/ops/test_disk_guard_paths.py` | 34 passed |
| `python3 tools/desk_bin/run_files.py . tests/platformkit/test_loc_rail_scope.py` | 1 passed |

Bar: all cases pass (n = 88, CONSTRUCT; before = 0, module absent). Headline cases, reproduced
independently by the contract tier:
- a 2.5 GB `disk_usage` seam gives `refuse`, `defer_night` True, `disk_refuse`, in ONE `run()`
  call;
- a 60 MB log with `.1` to `.5` present projects exactly `.1` to `.5`, marks `.5` would_drop, and
  leaves the directory listing, sizes, mtime_ns and sha256 unchanged;
- the three real Windows `--log` argv values from `paper_desk_config.json` are all skipped as
  `protected_path_skipped`, and none is proposed.

`git status --short --ignored data docs/evidence` was empty before and after every run.

## Mutants (scratch copy only; each turns at least one named case red)
| mutant | killed by |
|---|---|
| refuse `<` -> `<=`; defer on warn | test_disk_boundaries[5000000000-warn-disk_low] |
| warn `<` -> `<=` | test_disk_boundaries[10000000000-ok-None] |
| LOG_KEEP 6 / 4 | test_60mb_log_proposes_five_files_and_changes_nothing |
| realpath branch removed (lexical only) | test_symlink_into_protected_is_skipped |
| realpath skipped for any backslash root/path | test_backslash_name_through_symlinked_dir_into_data_is_skipped, test_posix_root_with_backslash_still_resolves_symlinks |
| case-sensitive root / path compare | test_classify_lexical_posix[DATA/x.log-...] |
| `..` not collapsed | test_classify_windows_style[...logs\..\data\x.log-...] |
| string startswith compare | test_classify_lexical_posix[database/x.log-None] |
| missing free -> 0; disk_unknown -> ok | test_bad_free_is_unknown_never_refuse[None] |
| missing prior size -> 0 | test_per_log_unknown_does_not_mask_another_high |
| interval bounds removed | test_bad_prior_or_clock_is_rate_unknown_no_warn[prior2-...] |
| rate `>` -> `>=` | test_log_growth_rate_boundary[50000000-False] |
| receipt protected check removed | test_receipt_refused_under_protected_or_outside[data/r.json] |
| sibling check removed | test_symlinked_sibling_into_data_skips_the_whole_family |
| scan follows symlinks | test_archive_scan_read_only_and_error_is_unknown |
| symlinked-receipt refusal removed | test_symlinked_receipt_is_refused |
| allow_nan=True | test_unserialisable_receipt_is_a_reason_not_a_crash[bad0] |
| TypeError not caught | test_unserialisable_receipt_is_a_reason_not_a_crash[bad1] |
| checked gate removed | test_unchecked_row_is_never_proposed |
| temp outside target dir | test_receipt_temp_is_in_target_directory |

Builder run: 24 of 24 killed. Adversarial tier: 38 mutants. The survivors are M21, M24, M29,
which are equivalent, and M39 (realpath parsed in the path's own flavour), which is harmless
on this host; it is filed as a NEW GAP below.

## Verifier tiers (independent Opus sub-agents; codex is not available in this environment)
- **Pre-build critic:** REVISE with 19 items, all folded into AMENDMENT 1.
- **CONTRACT tier (A/B/Q + spec):**
  - Pass 0 on b5050b33: ACCEPT WITH CORRECTIONS. A symlinked receipt target was not refused
    (item 14), and this memo was absent (A7).
  - Pass 1 on b107ff6a: ACCEPT WITH CORRECTIONS. Only the memo was still open; this file closes it.
- **ADVERSARIAL tier:**
  - Pass 0 on b5050b33: REJECT, with three defects:
    1. A backslash name on POSIX skipped the realpath check, so `lnk/x\y.log` through a symlink
       into data/ was proposed.
    2. A symlinked receipt was accepted.
    3. A `TypeError` from `json.dumps` crashed `run()`.

    It also noted that `evaluate()` trusted unchecked rows. All four were fixed in b107ff6a,
    with 8 cases added.
  - Pass 1 on b107ff6a: ACCEPT WITH CORRECTIONS. Correction R1: a POSIX root whose own name
    contains a backslash still skipped the realpath check. The builder applied R1 after that
    verdict, in the commit carrying this memo: only a drive-letter or UNC root on POSIX is
    treated as unresolvable. The R1 case was added, and the mutant that restores the old gate
    is killed. R1 was not re-verified by a tier, because the limit of one re-verify was used.

## NOT VERIFIED
- The recorder disk: real free bytes, real log sizes, real archive growth.
- The tick hook on Windows, including "disk_refuse within ONE TICK" end to end. The cloud run
  shows it for one `run()` call only.
- The `--log` relocation. Rotation stays inert in production until it lands.
- Any proposal execution.
- The Windows-native branch of `classify()`, where `os.name == "nt"` and realpath runs on NTFS.
  It has not been run on Windows.
- Python 3.10 on the laptop.

## NEW GAP lines (from the tiers; not fixed here)
- NEW GAP: on POSIX, a path outside the root that differs from the root only in case is treated
  as inside the root, because the root components are casefolded. It is still subject to the
  protected check.
- NEW GAP: seam failures other than OSError crash `run()`. Examples: a NUL byte in a path gives
  ValueError, and garbage returned by `stat` is not handled.
- NEW GAP: `rotation_plan` accepts `present` values outside 1..LOG_KEEP.
- NEW GAP: Windows name aliasing (`data.`, 8.3 short names, dotless i) is caught only by the
  native realpath of an existing file.
- NEW GAP: mutant M39 (flavour of the realpath parse) survives. No test pins the native parse.

PORTABLE: yes (code + construct tests). The hook and relocation are WINDOWS.
