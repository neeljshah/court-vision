GAP S351 | sport all (maker channel) | worktree harness-h6 | log cx_s351_runbook_compliance
# Paper-to-live operations runbook + record-keeping / venue-eligibility scaffold (audit 04 capabilities 12 and 13: MISSING)

SINGLE PROBLEM: docs/operations/ holds only pod/CV runbooks. There is no start/stop procedure, incident playbook, flatten
procedure, venue-outage response or daily reconcile checklist for the maker channel, no record-retention policy, and the
per-state venue-eligibility matrix lives only in a private note -- nothing in code can refuse to run where a venue is not
available.

BINDING BEFORE-CONDITION (re-run, quote): `ls docs/operations` shows no maker/trading runbook;
`ls scripts/platformkit/execution/venue_eligibility.py` fails.

CHANGE (NEW files only):
1. docs/operations/MAKER_CHANNEL_RUNBOOK.md: written FROM THE CODE, citing file:line for every procedure -- daily start (capture
   heartbeat check, ledger integrity, breaker state), paper session start/stop, the kill switch (the api kill switch is
   token-required and fails closed -- cite it, do not edit api/), quote pull conditions (quote_engine reasons), flatten and
   reduce-only deadlines, venue outage / suspended market / sequence gap response, restart recovery from the position event log,
   daily reconcile checklist (intents vs fills vs positions vs settlement), weekly gate-evidence checklist referencing
   docs/GO_LIVE_GATES.md, and an incident log template. Where the code has no mechanism yet, write "NOT IMPLEMENTED" plus the row
   that owns it -- never describe a control that does not exist.
2. scripts/platformkit/execution/venue_eligibility.py (<= 200 LOC, stdlib, pure): `check(venue, state_code, as_of) ->
   {"allowed": bool, "reason": str, "source_date": str}` reading a small JSON table
   scripts/platformkit/execution/venue_eligibility_table.json whose rows carry state, venue, status in
   {available, not_available, contested, unknown}, source, source_date. FAIL CLOSED: unknown state, unknown venue, status other
   than available, or a table row older than max_age_days all return allowed = False. Ship the table with EVERY status set to
   "unknown" and a header note that the OWNER fills it from a dated primary source -- the builder must not assert the legal status
   of any state. The operator state is a required explicit argument or env CV_OPERATOR_STATE; absent -> allowed False.
3. docs/operations/RECORD_KEEPING.md: what is retained (raw capture, intents, order events, fills, fees, settlements, model and
   fee-schedule versions, config hashes), retention periods as OWNER-DECISION placeholders, where each lives, and a plain
   statement that tax treatment is an owner + professional question this repo does not answer.
4. tests/platformkit/execution/test_venue_eligibility.py: every fail-closed path + one available path with a synthetic table.

CONTROLS: documentation + a fail-closed gate; no measured number; no legal conclusion anywhere. ACCEPTANCE: per-file test
passes; every file:line citation in the runbook resolves (the builder greps each one and pastes the check). Diff = NEW files
only. Vocabulary follows contract Q6; automated scan required. Memo docs/evidence/harness/S351_runbook_compliance_2026-09-21.md
ends with a NOT VERIFIED list.
