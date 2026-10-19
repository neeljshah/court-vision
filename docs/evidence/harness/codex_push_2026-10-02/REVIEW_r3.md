Five branches are HOLD; three are LAND AFTER FIX. None is already on master.

Static review only: no tests, code probes, writes, checkout, fetch, or network. References below identify files at each branch head. Branch names abbreviate `private/cloud/S<id>-2026-09-30`.

Across all eight branches: changes are additions; touched-path reverse diffs against master are empty. No seal-pinned edits, registry writes, enabled flags, removed fields/files, oversized files, `.gitattributes` appends, or secret-like literals were found.

**S670 - HOLD**

- **Missing horizons can produce false TRUSTED results.** `scripts/platformkit/execution/series_gate.py:122` accepts an absent/null horizon; line 174 drops that game before calculating missing share. Removing adverse games' horizon blocks can leave sufficient positive games and zero reported missing quantity. This violates B1 despite the spec permitting omission. Fix: require explicit horizon accounting, mark absent evidence INSUFFICIENT, and retain excluded-game counts. `tests/platformkit/execution/test_series_gate_fix.py:36` tests missing fields and the entire `h` block, but misses this partial-block case.
- **The public API bypasses configuration validation.** `scripts/platformkit/execution/series_gate.py:220` trusts any supplied `cfg`. Lowering games/fills to 3 and corpora to 1 without changing the hash lets three constant-positive games satisfy the gate. Fix: apply the same hash, shape, and minimum checks to supplied dictionaries as to loaded files. `tests/platformkit/execution/test_series_gate.py:184` checks only `load_config`, leaving this bypass untested.

No unlanded code prerequisite or separate Windows defect found.

**S698 - HOLD; must land after corrected S670**

- **Rejected evidence still receives TRUSTED status.** `scripts/platformkit/eval_gate/stage_gate.py:199` applies evidence-validity protection only at PAPER. REPLAY/SHADOW receipts rejected for prereg mismatch or reused games can still report `trust_state="TRUSTED"`. Fix: require `_evidence_ok` for the computed stage before exposing its trust state. `tests/platformkit/eval_gate/test_stage_gate.py:40` and line 120 check blocked advancement but never assert that rejected evidence is untrusted.
- **Receipt-controlled binning can conceal calibration error.** `scripts/platformkit/eval_gate/stage_gate.py:60` accepts arbitrary bins without policy-bound boundaries. Two 100-state bins with prediction/outcome sums `(30,50)` and `(70,50)` yield ECE 0.2; merging them yields 0 and can change promotion without changing policy. Fix: bind bin definitions to the hashed policy and validate receipt bins against them. The arithmetic assertion at `tests/platformkit/eval_gate/test_stage_gate.py:93` does not test this substitution.

The shipped OWNER_TBD policy blocks promotion beyond REPLAY, but does not repair these defects. S670's defects are also inherited.

**S671 - HOLD**

- **Completed orders remain eligible for self-trade prevention.** `scripts/platformkit/execution/fill_model_venue_rules.py:118` checks scheduled lifetime without remaining quantity; line 169 runs this before fill simulation. A YES order filled before a later NO order arrives can incorrectly cancel that NO order. Fix: process prior fills before evaluating self-trade prevention. `tests/platformkit/execution/test_s671_venue_rules.py:58` lacks the completed-predecessor case.
- **Rejected amendments cancel valid predecessors.** `scripts/platformkit/execution/fill_model_venue_rules.py:87` truncates the original order before replacement validation at line 169. A rejected post-only amendment therefore removes subsequent fills from the still-valid original order. Fix: truncate an atomic amendment's predecessor only after acceptance; preserve separate cancel-new semantics.
- **Order-group enforcement handles only the first trip.** `scripts/platformkit/execution/fill_model_venue_rules.py:176` limits processing to one trip; line 179 excludes previously tripped groups. Orders accepted after the window can exceed the limit again without cancellation. Fix: process successive trip/reset windows. The test at `tests/platformkit/execution/test_s671_venue_rules.py:92` does not exercise a second trip.
- **CRLF-sensitive test.** `tests/platformkit/execution/test_s671_latency_grid.py:25` hashes working-tree fixture bytes against an LF digest without an applicable LF attribute. Fix: explicitly hash LF-normalized bytes and document that convention.

No unlanded code dependency. The event-order defects require correction and review before landing.

**S672 - LAND AFTER FIX**

- **The refusal test can delete existing laptop data.** `tests/platformkit/ingame/test_s672_reading_guards_io.py:158` targets `REPO/data/s672_refused_probe.json`; lines 162-166 delete it and sibling artifacts regardless of who created them. Fix: use `tmp_path/data`, run with `cwd=tmp_path`, and remove manual repository cleanup.
- **A nonexistent archive produces a successful empty report.** `scripts/platformkit/ingame/s672_reading_guards_cli.py:90` silently globs a missing directory; line 135 returns success. Fix: reject a supplied non-directory before producing artifacts and add a missing-directory CLI assertion.

The numerical tests independently check coefficients/bootstrap calculations. No concrete numerical defect or unlanded dependency found.

**S674 - LAND AFTER FIX**

- **Windows symlink privilege is assumed.** `tests/platformkit/governance/test_model_card_check.py:172` unconditionally creates a symlink. Fix: catch `OSError` around that operation, skip specifically for Windows error 1314, and re-raise other errors.

Two limits must remain explicit:

- `scripts/platformkit/governance/model_card_index.py:85` and line 106 discard numeric signs before receipt matching. A sign-reversed comparison can pass the checker. This is documented/spec-permitted, so passing does not establish signed numerical fidelity.
- `scripts/platformkit/governance/model_card_check.py:148` permits PENDING artifact verification. A successful checker exit does not complete artifact-hash or prereg/seal verification.

Other hash checks normalize line endings. No unlanded dependency found.

**S675 - HOLD**

- **Constant decimal series can receive BETTER.** `scripts/platformkit/eval_gate/multiplicity_haircut.py:69` recognizes zero variance only through floating-point standard deviation. Equal values such as three `0.1` game means can acquire tiny positive variance from rounding, creating an enormous statistic and passing the combined checks at line 123. Fix: return raw p=1 when all game means are exactly equal, retaining the arm in K. Add `[0.1] * 3`; `scripts/platformkit/eval_gate/test_multiplicity_haircut.py:68` tests only `[0.2] * 40`. This finding is static numerical analysis, not an executed reproduction.
- **CRLF-sensitive provenance test.** `scripts/platformkit/eval_gate/test_multiplicity_haircut.py:99` hashes raw source CSV bytes against an LF digest. Fix: hash LF-normalized bytes and identify the digest accordingly.
- **Python 3.10 timestamp incompatibility.** `scripts/platformkit/eval_gate/multiplicity_haircut.py:156` passes terminal-`Z` timestamps directly to `datetime.fromisoformat`, which the specified laptop Python 3.10 does not accept. Fix: normalize terminal `Z` to `+00:00` and test equivalence.

No unlanded dependency found.

**S676 - HOLD**

- **JSON `null` disables the dead-man alarm.** `scripts/platformkit/ops/deadman_check.py:93` skips schema validation when parsing returns `None`; line 96 also skips coverage checks. With a timely or unknown commit timestamp, line 108 reports `ok`. Fix: call `schema_errors(value, day)` for parsed null as well. Add a null-heartbeat case requiring failure; `tests/platformkit/ops/test_slo_status_s676.py:157` currently tests an invalid dictionary only.

The writer uses the existing atomic helper. Standalone code has no unlanded prerequisite. Tick/push/delivery integration remains proposed and unverified at `docs/evidence/harness/S676_cloud_result_2026-09-30.md:153`; landing this code does not complete the every-tick AD-1 requirement.

**S677 - LAND AFTER FIX**

- **Valid grouped queues are rejected.** `scripts/platformkit/ops/postmortem_link_check.py:34` accepts one hash after `S<row>:`; the producer at `scripts/platformkit/ops/paper_desk_issue_ledger.py:265` emits comma-separated hashes. Fix the grouped regex arm to `S\d+: [0-9a-f]{16}(?:, [0-9a-f]{16})*\s*$`. Extend the fixture at `tests/platformkit/ops/test_postmortem_link_check.py:70` with two hashes.

`tests/platformkit/ops/test_postmortem_link_check.py:205` depends on current repository issues and wall time, with a frozen seed cutoff at line 208; later escalation can invalidate it. The missing requested S502 postmortem is explicitly recorded at `docs/evidence/harness/S677_cloud_result_2026-09-30.md:78` and must remain open. No unlanded code dependency found.

| branch | verdict | must-land-after | top defect | fix size (S/M/L) |
|---|---|---|---|---|
| S670 | HOLD | None | Missing horizons can produce false TRUSTED | M |
| S698 | HOLD | Corrected S670 | Rejected evidence retains TRUSTED status | M |
| S671 | HOLD | None | Completed orders trigger self-trade prevention | M |
| S672 | LAND AFTER FIX | None | Test deletes pre-existing data | S |
| S674 | LAND AFTER FIX | None | Windows symlink privilege assumed | S |
| S675 | HOLD | None | Constant series can receive BETTER | S |
| S676 | HOLD | None for standalone code | Null heartbeat reports success | S |
| S677 | LAND AFTER FIX | None | Valid grouped queue rejected | S |

**LANDING ORDER**

After their listed fixes: S672, S674, S677.

Keep S675, S676, S671, S670, and S698 held pending correction and review. Once cleared, those first four are independent; S698 must follow corrected S670.