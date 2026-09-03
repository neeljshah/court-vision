GAP S174 | sport mlb+nba | worktree a17 | log cx_s174_frozen_spec_v2_drop
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q -- read it first. S-row: eye check = n/a.
CONTEXT: S171 falsified the premise that period-grain corpora can be built locally (mlb_inning period/total 0/178
games with a period line; nba_quarter_shape period/spread 0/1,593; zero inning/period/quarter tickers across
21.87M price rows). The orchestrator decided the honest exit for S73: a VERSIONED frozen-spec bump that marks the
two families DROPPED. Nothing is deleted; v1 stays byte-identical under its pin; the FWER ledger is never touched.
PREMISE (step 0): locate the frozen family spec DATA module (grep FWER_FAMILIES_SPEC / load_families / the
s14-families-v1 pin 62702554f6e57ec9f3182e8edc1e4d6a109a3b41 under scripts/platformkit/foundry and combo); quote
the two family definitions (mlb_inning: mlb/period/total, 6 members; nba_quarter_shape: nba/period/spread, 15
members) and the current pin computation; measure: families in v1 = N1, members = M1.
LIMIT (step 1): n/a (CONSTRUCT).
CHANGE (step 2): ADDITIVE ONLY. Add spec_version "s14-families-v2" alongside v1: v2 = v1 plus a status DROPPED
with reason "no period market in any local store (S171 2026-09-04)" on the two families; load_families()
keeps its current default (v1, unchanged pin, unchanged return) and accepts version="s14-families-v2" to return
the v2 view (dropped families excluded from the active list but retrievable with a dropped=True flag); every
reader (runner, tiers, family_bars, seed_queue --frozen) stays on v1 -- do NOT change any reader; an explicit
opt-in flag or argument may be ADDED (default OFF) but nothing flips. Record the v2 pin (sha256 of the canonical
v2 payload) in the memo.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = (i) v1 pin sha unchanged; (ii) families dropped in v2 / 2 and members / 21; (iii) readers changed
  before        = v1 pin 62702554f6..., 0 dropped, N1 families
  bar           = (i) byte-identical pin and byte-identical load_families() default output; (ii) exactly 2
                  families / 21 members marked DROPPED in v2, N1 - 2 active; (iii) 0 readers changed (grep every
                  importer of load_families and diff their call sites vs master); construct test for all three
  n             = N1 families (CONSTRUCT; every family enumerated)
  eye check     = n/a (S-row); reproduction = the verifier loads v1 and v2 and diffs the family lists
  must not move = the v1 pin, every threshold, every tier bar, the 18-row FWER ledger, every reader
NON-TAUTOLOGY: v2 is a superset record (status added), never a filtered copy that loses history.
EVIDENCE: docs/evidence/harness/S174_frozen_spec_v2_drop_2026-09-04.md -- the two definitions, v1/v2 pins, the
importer list with unchanged call sites, NOT VERIFIED list. ASCII only. Calibration language only.
TEST: one new per-file test under tests/platformkit/foundry/ (construct: pin unchanged, 2/21 dropped in v2, default
unchanged); run it plus the existing frozen-spec / family-bars test files one at a time.
COMMIT: explicit pathspec in the worktree, no push; never touch the register or the ledger. Report the sha.
NEVER PARK; finish with the report + SHA.
