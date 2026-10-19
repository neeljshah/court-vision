Spend the thirty-minute session on recorder availability, the urgent NFL fixture ruling, and cloud-account control, in that order. Full recorder migration takes longer. [Plan][Recorder]

## 1. THE THREE THINGS ONLY YOU CAN DO THIS WEEK

**1. Protect recording and name one Windows operator. Proposed timebox: 15 minutes; actual duration UNKNOWN.** This unblocks capture, qualification, and subsequent calibration and execution-quality evidence. [Plan]

- On the current recorder, connect AC power. Open Windows Terminal as administrator and run the two documented commands below. Plug in the spare Windows laptop and make it available for preparation. [Recorder]
  ```powershell
  powercfg /change standby-timeout-ac 0
  powercfg /change hibernate-timeout-ac 0
  ```
- In your owner desktop session, name one operator and give this instruction: "Prepare eligible S561 then S598 books restarts as separate events, plus the S502 state restart. Require accepted code, the permitted window, and separate adoption evidence." These are work-item IDs; adoption means proving the running process uses the change. [Desk][Plan]
- Restarts require 06:00-16:00 UTC, between games, and the applicable process/resource checks. Keep the current recorder authoritative while the spare is qualified. [Desk][Plan]
- Reserve a later migration session: the older runbook estimates about one owner-hour plus copying; comparison, publication and recovery requirements remain additional gates. [Recorder][Recorder research]

**2. Resolve the NFL test-fixture rule. Proposed timebox: 5 minutes; actual duration UNKNOWN.** This releases the owner block on matching Washington/Jacksonville team codes before the documented October 4 collection opportunity. [Desk][NFL]

- Open `docs/operations/DESK_STATE.md`, section 6 item 3, and `docs/evidence/tracking/specs/S613_spec.md`. The blocked fixture is under `tests/platformkit/ingame/fixtures/s613_real/`; the preflight objects to verbatim timestamp fields, and a memo count also needs correction. [Desk][NFL]
- Give the landing operator the pick-one ruling below before **October 3, 12:00 UTC**. The operator must still clear review and the permitted identity-change sequence. [Desk]

**3. Confirm cloud access, existing routines and budgets. Proposed timebox: 10 minutes; actual duration UNKNOWN.** This supplies account facts agents cannot infer and supports a controlled work queue. [Plan][Cloud research]

- Open `claude.ai/code/routines`; inspect existing enabled routines and recent runs. The handoff reports earlier activation, while present activation is UNKNOWN. Resolve that discrepancy before creating another routine. [Desk][Cloud research]
- Open the Default cloud environment settings. Check its setup against `docs/operations/cloud/setup.sh`; actual checkout location and successful setup execution still need evidence. [Desk][Cloud research]
- Read each provider's account usage screen and give the operator the remaining allowance, reset time and observation time, without credentials. Accept or reject the proposed 20% reserve and one-queue policy below. [Plan][Cloud research]

## 2. DEADLINES

Dates below are UTC; these are locally documented planning dates, not freshly verified external schedules. [Plan]

| Date | Required disposition | What is lost if missed |
|---|---|---|
| **Oct 3, 12:00** | Resolve S613 and clear its remaining gates. | The planned advance declaration for the affected Oct 4 NFL games; later repair cannot recreate missing prospective observations. [Desk][NFL] |
| **Oct 3, before Oct 4 ~06:05** | S469 code step only after the final Oct 2 scoreboard and required review; then S625's declaration step. | The dependent sequence shifts; the prior receipt cannot be skipped. [Desk] |
| **Oct 4, before Oct 5 06:05** | S625 code step after the Oct 3 receipt. | Its planned effective window shifts. [Desk] |
| **Oct 7; before Oct 8 00:00** | Finish soccer readiness and the separately scheduled declaration updates. | The planned soccer launch loses required preparation; incompatible updates cannot be combined. [Desk][Plan] |
| **Oct 8, 12:00** | Soccer opt-in only after readiness and capture requirements pass. | Defer that collection opportunity; do not backdate admission. [Desk][Plan] |
| **Before Oct 19's next-day schedule run; before Oct 20** | NBA admission/capacity decision; R2 research declaration, respectively. | The planned NBA collection window or prospective research scope is at risk. [Desk][Plan] |
| **R2: actual MLB final-state receipt +72 hours; NBA Dec 20 cutoff, Dec 24 00:00 lock** | Preserve the already declared closing rules. | Late evidence cannot repair insufficient support within the locked study. [Plan] |

**October 4, 06:05 is only the earliest documented recorder-transfer opportunity. It is not a deadline or permission to transfer an unqualified host.** [Plan][Recorder]

## 3. DECISIONS

Recommendations below are proposals; existing sealed thresholds stay fixed. [Plan]

| Decision | Recommended default | If undecided |
|---|---|---|
| **S613: reviewed fixture-specific ruling, or defer?** | Permit a narrowly documented treatment preserving literal source timestamps only after review confirms unchanged acceptance requirements. Otherwise defer. | S613 stays blocked; the deadline still applies. [Desk][NFL] |
| **Recorder: spare Windows laptop or new VM?** | Spare laptop; current recorder remains the sole publisher until qualification and recovery pass. | Shared-host contention continues; transfer remains pending. [Plan][Recorder research] |
| **Accept one landing operator, two initial cloud builders and 20% quota reserve: yes/no?** | Yes, within existing access. Replacement automation activates only after its Windows rehearsal and recovery review. | Work continues within existing authorization; new dispatcher activation remains pending. [Plan][Red team] |
| **Soccer opt-in: yes/no?** | Yes only with the required evidence by the deadline; otherwise no for that opportunity. | Admission remains pending. [Desk][Plan] |
| **Prepare independent outage alerts and a private off-host archive: yes/no?** | Yes. Name the alert recipient and archive target. For the external missing-heartbeat check, use 30 minutes plus 20 minutes grace; its provider-specific clicks are UNKNOWN. | Independent alert delivery and restoration remain UNKNOWN. [Plan][Alerts] |
| **Activate additional authenticated capture, unresolved paper stages or served-artifact changes now: yes/no?** | No until their specific reviewed packages and owner decisions are complete. Credentials, process permission and data-use applicability remain separate requirements. | Those paths remain blocked; agents can continue independent preparation. [Desk][Plan][Recorder research] |

The alert endpoint belongs in recorder environment variable `COURTVISION_DEADMAN_URL`, outside repository files and logs. Configuration alone does not prove alerts work; agents must verify actual outage and recovery delivery. [Alerts]

## 4. WHAT THE AGENTS WILL DO WITHOUT YOU

The October 3-9 queue below is proposed work under existing authorization; current execution is UNKNOWN. [Plan][Cloud research]

| Work | Morning evidence to inspect |
|---|---|
| Reconcile exact candidates, repair named defects, review and land eligible changes through one operator. | Candidate/attempt inventory with separate review, landing and adoption states. A branch alone is insufficient. [Plan][Red team] |
| Repair capture provenance and bounded qualification; prepare eligible restarts. | `docs/evidence/forward/qualification/<date>...` and adoption receipts, including new process identities and advancing source rows. [Plan][Transfer] |
| Correct night completion and preserve unresolved dates through recovery. | `docs/evidence/forward/nights/<date>.json`, required outputs, and explicit missing/refused reasons. [Night dossier] |
| Reconcile game counts, exclusions, scoring and publication. | `docs/evidence/forward/daily/<date>.md`, with links to the dated evidence and confirmation that required files reached private trunk. [Desk][Transfer] |

**Start each morning with the dated daily report.** Require linked evidence for completed work and explicit unresolved items; a local receipt or successful exit does not establish publication. [Desk][Transfer]

## 5. WHAT IS NOT WORKING YET

- Reliable complete nights are unproved; the dated handoff records September 30 and October 1 as PARTIAL. [Desk]
- Night completion and recovery candidates still have substantive rejected requirements. [Night dossier]
- Automatic recorder adoption/publication and successful failed-adoption recovery remain unverified. [Transfer]
- The paper execution core remains blocked by its rejected shared event-journal dependency. [Core dossier]
- Sustained eligible sample collection and new calibration or execution-quality improvement remain UNKNOWN. [Plan][Recorder research]

## 6. WHAT TODAY'S PUSH ACTUALLY PRODUCED

Today's push produced a review and landing package: candidate identities, named defects, dependency order, conditional landing instructions and research corrections. Some components are ready as unused tooling; landing them alone changes no scheduled capture behavior. Separately, the desk handoff records S492 B, S502 and S469 A as landed, with S502 adoption pending and S469 A only an inert declaration. The supplied evidence does not prove a completed recorder transfer, reliable unattended recovery, sustained prospective collection or new calibration improvement. [Tooling dossier][Reporting dossier][Desk][Plan]

**NOT VERIFIED:** Current processes, installed tasks, account balances, routine activation, permissions and changes after the dossiers' snapshots are UNKNOWN. [Transfer][Cloud research]

[Plan]: C:/Users/neelj/nba-ai-system/.planning/codex_push_2026-10-02/out/px_x10.md
[Desk]: C:/Users/neelj/nba-ai-system/docs/operations/DESK_STATE.md
[Recorder]: C:/Users/neelj/nba-ai-system/docs/operations/RECORDER_LAPTOP_RUNBOOK.md
[NFL]: C:/Users/neelj/nba-ai-system/docs/evidence/tracking/specs/S613_spec.md
[Red team]: C:/Users/neelj/nba-ai-system/.planning/codex_push_2026-10-02/out/px_a10.md
[Recorder research]: C:/Users/neelj/nba-ai-system/.planning/codex_push_2026-10-02/out/px_t4.md
[Cloud research]: C:/Users/neelj/nba-ai-system/.planning/codex_push_2026-10-02/out/px_t7.md
[Night dossier]: C:/Users/neelj/nba-ai-system/.planning/codex_push_2026-10-02/out/px_d3.md
[Transfer]: C:/Users/neelj/nba-ai-system/.planning/codex_push_2026-10-02/out/px_d6.md
[Alerts]: C:/Users/neelj/nba-ai-system/.planning/codex_push_2026-10-02/out/px_d7.md
[Tooling dossier]: C:/Users/neelj/nba-ai-system/.planning/codex_push_2026-10-02/out/px_d8.md
[Core dossier]: C:/Users/neelj/nba-ai-system/.planning/codex_push_2026-10-02/out/px_d9.md
[Reporting dossier]: C:/Users/neelj/nba-ai-system/.planning/codex_push_2026-10-02/out/px_d10.md