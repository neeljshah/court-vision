**Only S666 is ready to land.** I reviewed the eight local refs read-only and ran no tests. The other seven have result-changing defects, incomplete row requirements, or fail-open behavior. Citations below refer to files at the named branch ref.

### Branch reviews

- **S660 - HOLD.** `scripts/platformkit/ingame/kalshi_ws_signer.py:205-220` checks the credential destination only once. A file appearing after that check can be overwritten by `:153` and deleted by `:218`; `:217-220` also swallows cleanup failure. The same replace call lacks the Windows retry helper. `tests/platformkit/ingame/test_kalshi_ws_signer.py:281-283` hashes checkout bytes of a file without an LF rule, so CRLF checkout can fail the test. Master has changed the branch's `docs/operations/cloud/setup.sh` path since the merge base.

- **S663 - HOLD.** `scripts/platformkit/ops/latency_ledger_io.py:134-143,203-217` skips missing sport directories and days, then can write an exit-zero receipt with an incomplete or empty quantile denominator. `tests/platformkit/ops/test_latency_ledger_mid.py:145-153` covers a missing root, not a missing sport or day. The required real-archive replay is marked unverified in `docs/evidence/harness/S663_cloud_result_2026-09-30.md:64-68`. The writer called at `latency_ledger_io.py:214-215` uses bare `os.replace` in `exec_quality_audit_io.py:222`. The offset sign described in `S663_spec_2026-09-30.md:37` conflicts with S664's definition; current absolute-value exclusion masks that mismatch.

- **S664 - HOLD.** `scripts/platformkit/ops/clock_offset.py:198-225,243-268` has no seven-day coverage check or breach issue action. `docs/evidence/harness/PROPOSED_S664_tick_hook_2026-09-30.md:56-60` says the issue opener is unbuilt, so the register's seven-day acceptance cannot be met. `clock_offset.py:131-138` tries only the first DNS address, potentially reporting unmeasured despite a reachable second address. `tests/platformkit/ops/test_clock_offset.py:300` checks runtime, not SNTP correctness.

- **S695 - HOLD.** S664 defines true time as local time plus offset (`scripts/platformkit/ops/clock_offset.py:14-18`), but `scripts/platformkit/ops/clock_guard.py:173` assigns samples to nights using uncorrected local time. A fast clock can put a pre-cutoff refusal into the next night; the 45-second test at `tests/platformkit/ops/test_clock_guard.py:38-50` never crosses the cutoff. An existing unreadable journal becomes `OFFSET_UNMEASURED` at `clock_guard_cli.py:79-98`, after which `clock_guard.py:201-206` permits the night. `clock_guard_cli.py:32` also uses bare `os.replace`.

- **S666 - LAND.** `scripts/platformkit/execution/risk_delta.py:153-208` keeps unmapped legs separate and computes the bounded scenario grid. `tests/platformkit/execution/test_risk_delta.py:49-81,263-273` checks hedging, unmapped legs, and 10,000 books against an independent grid. I found no defect in the branch diff.

- **S667 - HOLD.** The registered per-family cap is missing: `scripts/platformkit/execution/risk_limits.py:43-45` declares only six scopes, `:94-96` rejects an added family scope, and `:221-234` cannot report one. The required archived-night replay is still unverified (`docs/evidence/harness/S667_cloud_result_2026-09-30.md:82-85`); `tests/platformkit/execution/test_risk_limits.py:294-300` exercises synthetic sequences.

- **S668 - HOLD.** `scripts/platformkit/execution/risk_breakers_gate.py:34-39` accepts `check_caps()["reducing"]` in reduce-only mode. That flag ignores already resting same-side orders (`position_caps.py:37-46`), so a further order can increase worst-case exposure while the breaker permits it. `risk_breakers.py:217-225` also lacks the registered BOOK_GAP and S695 clock-state inputs. Its fault harness calculates breach-to-quiet from declared latency rather than observing cancellation (`risk_breakers_faults.py:143-155`), so that metric cannot catch failed cancel delivery. Windows risks remain at `risk_breakers_io.py:47` (bare replace) and `tests/platformkit/execution/test_risk_breakers.py:21-29,62-64` (raw checkout-byte hashes).

- **S669 - HOLD.** If every log record lacks a valid family, `scripts/platformkit/execution/risk_receipt.py:249-255` returns no receipts and `risk_receipt_io.py:153-161` prints success without creating the requested artifact. The registered fill-cause and queue-variant split is absent from `risk_receipt.py:219-220` and `risk_receipt_marks.py:92-120`. `tests/platformkit/execution/test_risk_receipt.py:150-159` checks the worst-cell peak against the path produced by the same code, so that assertion cannot establish correct risk values. `risk_receipt_io.py:101` uses bare `os.replace`.

Across the diffs, I found no seal-pinned edit, `data/registry` write, enabled feature flag, removed field or evidence file, file over 300 lines, market-beating claim, or embedded private-key literal. Apart from S660's setup script, master has not changed the paths these branches touch since their merge bases.

| branch | verdict | must-land-after | top defect | fix size (S/M/L) |
|---|---|---|---|---|
| S660 | HOLD | none | Credential path race and destructive cleanup | M |
| S663 | HOLD | S664 for measured offsets | Missing shards can produce a success receipt | M |
| S664 | HOLD | none | Seven-day gate and issue action absent | M |
| S695 | HOLD | S664 | Skewed timestamp assigned to wrong night | M |
| S666 | LAND | none | None found | - |
| S667 | HOLD | S666 | Per-family cap absent | M |
| S668 | HOLD | S666, S695 for full row | Reduce-only can permit increased exposure | L |
| S669 | HOLD | S666; S667/S668 for full receipt inputs | Success without artifact; fill split absent | L |

**Landing order:** Land S666. After fixes and verification, S660 is independent; S664 precedes S695 and measured-offset use in S663. S667 follows S666. S668 follows S666 and S695; S669 follows the risk inputs it is meant to report.