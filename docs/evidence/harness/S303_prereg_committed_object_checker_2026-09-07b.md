# S303 committed-object checker preregistration

## Scope

This additive S303 attempt creates only a committed-object checker under scripts/platformkit, its focused tests, and dated S303 evidence. The eight legacy reader files and every existing preregistration remain byte-identical.

## Acceptance

- For each of the eight preregistered reader-to-anchor mappings, the checker selects the committed object when a temporary repository working file contains different bytes.
- Fallback occurs only after git cat-file -e proves the requested object path absent from a repository with a committed HEAD.
- A missing working file after an absent object is reported as absent. A non-repository root, bad revision, unavailable Git, or unreadable object is an error and never absence.
- Six retained anchor seals are checked from committed bytes. A mismatch is reported and is never repaired.

## Boundaries

No existing reader, preregistration, register, ledger, data path, deployment surface, flag, or threshold is changed. This is an unscored local test-audit construct. The frozen +0.004 bar is unchanged for scored rows.

## Verification

The focused S303 test exercises all eight dirty-content cases plus fallback, absent, non-repository, bad-revision, and unreadable-object behavior. The PlatformKit LOC rail is run separately. This preregistration is sealed from its own LF-normalized bytes above the seal line; no commit is created in this sandbox.

SHA256_SEAL: 04997d7e2b2e8e8731986ff99bc850fcbfbf2cadfca7554663035b7293f31b1d
