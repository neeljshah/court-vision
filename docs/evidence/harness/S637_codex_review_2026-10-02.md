### S637 - HOLD

The binding base specification requires all five owned test files green in both environments (`docs/evidence/tracking/specs/S637_spec.md:17-18`). The cloud amendment instead excludes DATA_ABSENT failures from the acceptance bar (`docs/evidence/harness/S637_spec_2026-10-02.md:9-13`).

The result still shows two failing progress-ledger tests and two failing replay-file tests after the change (`docs/evidence/harness/S637_cloud_result_2026-10-02.md:27-35`). Calling the reduced subset green moves the acceptance bar contrary to B10/Q3. The real-state proof is also vacuous on the clean cloud host because absent files compare as `None == None` (`S637_cloud_result_2026-10-02.md:55-60`).

Additionally, the branch grows Python test files to 416 and 526 lines (`S637_cloud_result_2026-10-02.md:43`), violating the 300-line rail.

| private/cloud/S637-2026-10-02 | HOLD | - | acceptance bar moved; Python files exceed 300 lines | L |
6. Do not land S700, S701, S702, S707, or S637 until their HOLD findings are resolved.
