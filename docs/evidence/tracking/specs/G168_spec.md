GAP G168 | sport tennis | worktree a5 | log cx_g168_coverage_adjudication
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it, including A2, A7, Q3 and Q8;
self-check section B before reporting. **Q3 is the rule this row lives or dies by: a bar found
unmeetable is reported CLOSED AT LIMIT, NEVER lowered.** Read it before writing a line.

THIS IS THE ADJUDICATION G147 STOPPED ON, AND IT IS NOW COMPUTABLE. G147 stopped at its own stop
condition on 2026-09-02 because no gate-eligible table carried an auditable decoded-frame denominator,
and G147-CORR then showed the block was a producer gap rather than a matter of waiting. Three things
landed today that change the position, and you must start from all three rather than re-deriving them:

  - **G164**: `coverage_pct` is THREE different quantities. The LEDGER's is
    `manifest.summary.completeness` = decoded frames that emitted ANY row over decoded in-play frames,
    which never consults `min_players` and gates nothing. The HARNESS quantity that decides `passed`
    is `(per_frame >= min_players).sum() / n_frames` over a frame PADDED to the decoded count, and
    `adjudicate` DISCARDS it on return. A direct `evaluate()` call computes the same formula over
    EMITTED frames, and that is what every census and hand check in the program has been reading.
  - **G161**: the local reference tennis clip's rally-view share is **113/300 = 0.3767, Wilson 95 pct
    [0.3237, 0.4327]**, hand-labelled against a pre-committed rule, with blind self-agreement
    **49/50 = 0.980** [0.8950, 0.9965]. Labels are committed under `docs/evidence/tracking/g161_rally/`.
  - **G153/G156a**: `decoded_frames` now reaches real daemon ledger rows -- 4 of 4 when last counted.

WHAT TO PRODUCE:
  (a) The comparison G147 wanted, built correctly this time. For every tennis table you can reach that
      carries a decoded-frame denominator, report side by side: the harness quantity over EMITTED
      frames, the harness quantity over DECODED frames, and the ledger's completeness. Three columns,
      named unambiguously, because G164 showed they are different metrics and not one metric at
      different scales. State the ELIGIBLE DENOMINATOR of tables. Never a bare sample size.
  (b) Reuse G161's committed labels to add the rally-normalised column for the reference clip. Do NOT
      re-label and do NOT import G34's 41.7 pct from a different clip as this clip's denominator.
      Carry the Wilson interval through and say plainly that the label agreement of 0.980 bounds how
      precise any rally-normalised figure can be.
  (c) THE ADJUDICATION ITSELF. Against the unchanged 0.90 bar, state for each denominator whether it
      is meetable, and by what margin. G161 already implies whole-clip coverage caps near 0.38 on that
      clip even with perfect solving, so a whole-clip denominator is unreachable by more than 2x.
      **Say so and STOP THERE. Do not propose a lower bar, a different bar, a rally-scoped bar, or a
      "corrected" bar.** Recommending which denominator the bar SHOULD use is a change to the bar's
      definition and is out of scope for this row -- name it as an open question for the orchestrator
      instead. The retraction this program suffered came from exactly this temptation.
  (d) If you cannot reach enough tennis tables with a denominator to compute anything, that is a FULL
      SUCCESS. Report the count you could reach, name the tables by id, and say the adjudication
      remains time-blocked on new tennis rows -- but check first, because G147-CORR was itself a
      correction of a "just wait" claim that turned out false.

DO NOT change the 0.90 coverage bar, the harness, `_with_decoded_denominator`, `build_decode_manifest`,
`min_players`, the coordinate contract, the eligibility definition, or any verdict. Do not re-track.

ACCEPTANCE RULE:
  metric        = per-table three-column coverage comparison with the eligible denominator named; the
                  rally-normalised column with its interval; a meetable / not-meetable statement per
                  denominator against the unchanged 0.90
  before        = G147 stopped because no eligible table carried a denominator; G164 has since shown
                  the framing itself was wrong and there are three quantities, not two
  bar           = NO pass bar for this row. Success is the comparison computed and the adjudication
                  stated. "Unreachable against a whole-clip denominator, CLOSED AT LIMIT" is a full
                  success. Proposing a new bar value is an automatic REJECT.
  n             = every reachable tennis table carrying a decoded-frame denominator (CONSTRUCT,
                  exhaustive); state the count and name the tables
  eye check     = replaced by REPRODUCTION (Q7): recompute at least one table's three columns by hand
                  from its raw CSV and show the arithmetic
  must not move = the 0.90 coverage bar, every threshold, the harness, the coordinate contract, the
                  eligibility definition, and every verdict
EVIDENCE: docs/evidence/tracking/g168_coverage_adjudication_2026-09-03.md with the comparison table,
the rally-normalised column, the hand reproduction, the adjudication statement, and a NOT VERIFIED
list. Commit BEFORE reporting (A7).
CAUTION: another session commits into main concurrently. Work in your worktree, explicit pathspecs.
TEST: exactly one new per-file test if you add code; run only that file. NEVER a full pytest.
POD: READ-ONLY, BATCHED reads only. A daemon and keeper are LIVE; never kill or restart them. Heavy
decode goes on the pod under nohup, never locally -- the local box is RAM-constrained and a lane was
killed at 1.4 GB today.
COMMIT: explicit pathspec only, in a5, no push. Report the sha.
NEVER PARK: do not poll your own jobs in a blocking loop; never end waiting.
