# S349 preflight binding

PREPARE-ONLY: constructed infrastructure checks; no scored comparison.
Machine: local C:/Users/neelj/nba-harness-h2; CPU fixture tests only.
Vocabulary follows contract Q6; automated scan required.

Before-condition: Select-String reproduced contract_preflight.py:220:
`return True, "no --spec given", []`.
`git ls-files '*lane_commit*'` returned no repository hook copy.
The external hook was read only; its nonzero continuation matches the spec.

Changes: opt-in --strict rejects missing specifications, validates LF-normalized
prereg seals and committed content before scores, and verifies source pins.
Source pins use one repo path and one sha256: digest on the same line;
malformed or ambiguous pins fail. Existing check names and order are retained.
The proposed hook adds strict/spec arguments and blocks nonzero exits unless
the explicit override is set. The patch remains unapplied.

Reproduction from the worktree root, with TMP/TEMP and pytest basetemp directed
inside this worktree and PYTHONDONTWRITEBYTECODE=1:
`python -m pytest scripts/platformkit/tracking/test_contract_preflight_strict.py -q -p no:cacheprovider`
`python -m pytest tests/platformkit/test_contract_preflight.py -q -p no:cacheprovider`

Validation: existing per-file tests passed (24 tests). The initial new-file run
found a CRLF patch formatting failure; LF normalization corrected it. A subsequent
run passed 49 tests, including all hook exit/override combinations. The final
run passed all 50 tests, including root-level source pins and unpinned
specification prose coverage. All five delivery files passed ASCII, LOC and
automated Q6 checks. The patch base matched the read-only external hook.
Construct enumeration is the full
parametrized test collection: missing/absent spec; absent/broken/duplicate seal;
LF/CRLF seal; each score detector with and without committed prereg; missing or
changed prereg; spec/prereg source pins valid, mismatched, absent or malformed;
non-strict replay against HEAD; proposed patch application and constructed hook
execution; ASCII, LOC and vocabulary scans.

Contract B: additive opt-in checks; no schema field removed, no module retired,
no claim queue changed, no sampled metric, no threshold changed, no deployment.
Contract Q: construct-only, no scored comparison or charged trial; source identity
and prereg prerequisites tested. No calibration performance is asserted.

NOT VERIFIED
- Orchestrator application and live execution of the external hook.
- Scored calibration comparisons, real prereg histories or corpus behavior.
- Verifier reproduction in the landing tree and commit creation.
