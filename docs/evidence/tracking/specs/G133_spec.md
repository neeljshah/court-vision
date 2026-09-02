GAP G133 | sport tennis | worktree a5 | log cx_g133_eligible_growth_forecast
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A7; self-check section B
before reporting. This turns a WAIT into a forecast and a decision. Read
docs/evidence/tracking/g131_jump_statistic_policy_attempt2_2026-09-02.md and
g109_eligible_table_census_2026-09-02.md first.
THE SITUATION, established by two refusals rather than asserted. The harness jump statistic cannot
be chosen because too few tables reach the gate: G107 refused at 6 eligible, G109 counted 8 of 196,
G131 counted **8 of 203** and confirmed that G127's five salvage paths all OVERLAP with those eight
and add nothing. The bar is 10. So the question is TIME-BLOCKED, not analysis-blocked, and the only
live route to a bigger denominator is NEW games that reach court_feet.
WHY TENNIS IS THE ONLY ROUTE, from measurement: G47 measured tennis at 0/15 coordinate-contract
rejections -- it is the sole sport that reaches court_feet. The four-sport reachability programme
found soccer unreachable (0/100), football unreachable (a third direction in 0/60) and baseball
1/80 = 1.3 pct; basketball's figure was retracted after the G126 audit and is being re-censused as
G130, and in any case no basketball clip has ever been promoted to court_feet. G114 established that
tennis's five legacy tables are honestly unrepairable and G122 has now fixed source retention going
forward.
ANSWER THIS, as a forecast with its assumptions on the table:
  (a) MEASURE the tennis pipeline rate. From the bridge logs and the pod ledger, how many tennis
      games have been acquired, staged and TRACKED per hour since the bridge was repaired at
      03a34eef8 this evening? State the window you measured and the counts at each stage, because
      the acquisition, staging and tracking rates are different numbers and only the last one
      matters.
  (b) MEASURE the conversion rate that actually counts: of recently tracked tennis games, what share
      become JUMP-GATE ELIGIBLE -- not merely tracked, not merely court_feet, but reaching the jump
      statistic. G109's bucket vocabulary is the right frame. A game that tracks and then fails the
      coordinate contract or lands under G80's 30-frame floor does not help.
  (c) FORECAST how long until the eligible count reaches 10, with the arithmetic shown and the
      assumptions named. If the honest answer is "the observed conversion rate is too low or too
      noisy to forecast from", say that -- a forecast built on two data points would be worse than
      none.
  (d) NAME THE LEVERS that would speed it up, and be concrete and honest about each. The known
      constraints, all measured today: the workstation has roughly 2.3 GB free of 15.1 GB so
      download parallelism cannot safely rise while lanes are running; the tennis queue suffers
      HTTP 403 failures that need a cookie refresh only the user can do; queue duration floors are
      already long at 3600 s for tennis. Do NOT change any of these -- report which would move the
      number most and what each costs.
  (e) STATE THE ALTERNATIVE PLAINLY: if tennis cannot realistically deliver 10 eligible tables in a
      useful timeframe, then the jump-statistic bar of 10 is itself the thing to reconsider, and
      that is an orchestrator adjudication, not a lane's. Say whether you think the bar or the
      corpus is the thing that should move, and why, in one paragraph. Do NOT change the bar.
DO NOT change any threshold, the bar, any queue file, the bridge, the cookie jar, or the coordinate
contract. Do not mass-download. NEVER KILL ANYTHING ON THE POD.
ACCEPTANCE RULE:
  metric        = tennis games tracked per hour since the bridge repair, the tracked-to-eligible
                  conversion rate, and a forecast to 10 eligible with assumptions stated
  before        = eligible stuck at 8 across three censuses (6, 8, 8); route to 10 unknown
  bar           = NO pass bar. Success is the rates measured with their windows and denominators and
                  either a forecast with its assumptions or an honest statement that the data cannot
                  support one. "Too few data points to forecast" is a full success.
  n             = state the measurement window and the counts at each pipeline stage separately
  eye check     = n/a. Reproduction = the ledger rows and bridge log lines you counted, cited by
                  timestamp so the count can be rechecked.
  must not move = every threshold, the 10-table bar, every queue file, the bridge, the cookie jar,
                  the coordinate contract, and every pod process
EVIDENCE: docs/evidence/tracking/g133_eligible_growth_forecast_2026-09-0X.md with the per-stage
rates, the conversion rate, the forecast or its refusal, the lever assessment, the bar-versus-corpus
paragraph, and a NOT VERIFIED list. Commit derived tables under
docs/evidence/tracking/g133_forecast/ BEFORE reporting (A7).
CAUTION: several lanes today wrote evidence into the MAIN working tree and one dropped ledger rows
another session appended. Work inside your worktree and commit there.
TEST: exactly one new per-file test if you add code; run only that file. Never a full pytest.
POD: READ-ONLY. Never kill anything -- the daemon and seven bridge lanes are live and the corpus is
changing while you measure, which is why you must state your window.
COMMIT: explicit pathspec only, in a5, no push. Report the sha.
SHARED MODULE: none.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
