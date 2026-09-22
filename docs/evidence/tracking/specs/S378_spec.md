GAP S378 | sport all (maker channel) | worktree harness-h35 (master-based) | log cx_s378_fee_certification_gate
# Fee certification gate: no fee-netted number while the fee module disagrees with its own documented schedule (design: ASTRA_ROUND13 section 1 row 5)

SINGLE PROBLEM: row S364 certified scripts/platformkit/execution/venue_fees.py against dated fixtures and found 4 of 39 checks
mismatching: a raw fee just above a cent boundary is not rounded up (a one-cent undercharge per such order) and the module computes
in binary floats. That module is OWNER-CONTROLLED and must not be edited. Today nothing stops a replay from publishing fee-netted
markout computed with an undercharging fee.

BINDING BEFORE-CONDITION: `ls scripts/platformkit/execution/fee_certification_gate.py` fails, and
`python -m scripts.platformkit.execution.fee_time_certification --help` exits 0 (read that module first; quote its public
functions and the shape of its report in the memo -- the gate consumes that report, it does not re-implement the fixtures).

CHANGE (NEW files only; venue_fees.py and fee_time_certification.py are NOT edited):
1. scripts/platformkit/execution/fee_certification_gate.py (<= 300 LOC, stdlib + the two landed modules): `certify() ->
   CertificationStatus` runs the landed certification in-process and returns: certified (bool), checks_total, mismatches_total,
   mismatch fixture ids, the SHA-256 of venue_fees.py and of the fixture set, evaluated-at UTC. `require_certified(mode)`: mode
   "refuse" (the default) raises FeeCertificationError when not certified; mode "bounded" returns the status plus
   `undercharge_bound_per_order = Decimal("0.01")` ONLY when every mismatch is one of the two known classes (cent-boundary
   ceiling; binary float representation below 1e-9) and raises for any other mismatch class -- a new kind of disagreement is never
   bounded. `conservative_fee(module_fee, status) -> Decimal`: the module fee converted with Decimal(str(x)), ceiled to the cent,
   plus the bound when the status is not certified; a zero, negative, NaN or infinite module fee raises (never trusted). Every
   fee-netted figure produced under "bounded" mode must carry the label string the gate returns (it names the bound and the
   fee-module SHA-256). CLI: `--status` prints counts only and exits 0 certified / 3 not certified.
2. tests/platformkit/execution/test_fee_certification_gate.py: certified path, the two known mismatch classes -> bounded, an
   unknown mismatch class -> refuse in both modes, the conservative fee at and just above a cent boundary, zero / NaN / infinite /
   negative refusal, Decimal end to end (no float arithmetic in the gate), strict-int counts, the label content, and a test that
   the gate's verdict changes when the fee module's SHA-256 changes (inject the hash function).
3. docs/research/organization-sprint/PROPOSED_S378_venue_fees_decimal_correction_2026-09-21.md: the exact Decimal correction for the
   OWNER to apply to venue_fees.py (local-only path; never committed), with the four failing fixtures before / after.
4. Memo docs/evidence/harness/S378_fee_certification_gate_2026-09-21.md.

CONTROLS: PREPARE only, NEW files only, construct / fixture tests, no network, no measured fill or markout number. ACCEPTANCE:
per-file test passes; --help and --status work; diff = NEW files only; <= 300 LOC; ASCII; contract Q6 vocabulary; the memo ends
with a NOT VERIFIED list. The pod is OFF.
