GAP G176 | sport all | worktree a8 | log cx_g176_decoded_gate_across_sports
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md -- read it (A2, A7, Q8); self-check B.
RAILS: pod READ-ONLY and BATCHED; heavy work on the pod under nohup, never poll. NEVER kill, restart
or deploy over the daemon or keeper.

THE PROGRAM-LEVEL SUSPICION, raised in adjudication and NOT yet verified. Today's adjudication kept
the 0.90 tennis coverage bar on the decoded denominator and recorded tennis CLOSED AT LIMIT. An aside
in that reasoning, explicitly flagged as unverified, is worth a row of its own:

**MLB's ledger presence rate was 0.1565 against a 0.70 baseball `coverage_min`. If the padded decoded
formula fails baseball too, then tennis is not special and the decoded gate is failing the WHOLE
daemon path.** That would be a program-level fact, not a tennis fact, and it changes what the gate is
telling us: a gate that no sport can pass is not measuring quality, it is measuring the denominator.

**Do not treat that as established.** G164 showed the ledger's `coverage_pct` is a DIFFERENT quantity
from the harness coverage that decides `passed` -- the ledger figure is emitted-frame PRESENCE and
ignores `min_players`, while the gate uses `(per_frame >= min_players)` over a decoded-padded frame.
Comparing a ledger presence rate against a `coverage_min` is comparing two different metrics, so the
suspicion may dissolve on contact. Establishing that cleanly is a full success.

DO THIS:
  (a) Q8: read the per-sport `coverage_min` values from `tracking_harness.py` and quote them with
      file:line. Do not rely on the 0.90 / 0.70 / 0.60 figures repeated above.
  (b) Over the ELIGIBLE DENOMINATOR of every ledger row on the pod (there were 17 when this was
      written), report per sport: `rows`, `decoded_frames`, ledger `coverage_pct`, `passed`, and the
      failure heads. Name the denominator. Never a bare sample size.
  (c) For each row, state whether it failed on coverage specifically, as opposed to some other gate.
      A sport failing on ball_valid or track length is NOT evidence about the coverage denominator.
  (d) THE QUESTION: is there ANY sport, on ANY row, that passes the coverage gate on the decoded
      denominator? If yes, name it and the gate is discriminating. If no, say so plainly with the
      count, and state it as a measured fact about the current corpus rather than a claim about the
      gate's design.
  (e) Be careful not to conflate the two quantities (see above). If the ledger figure cannot answer
      the question because it is the wrong metric, SAY THAT and report what would answer it -- the
      gating quantity is discarded by `adjudicate`, which is exactly G164's finding, so the honest
      answer may be "not answerable from the ledger alone".

**DO NOT move, propose, or recommend a change to any `coverage_min` or any other bar.** This row
measures whether the gate discriminates; what to do about it is the orchestrator's call. Recommending
a value is an automatic REJECT.

ACCEPTANCE RULE:
  metric        = quoted per-sport coverage_min values; a per-row table of sport, rows,
                  decoded_frames, coverage_pct, passed and failure heads over the eligible
                  denominator; the count of rows passing the coverage gate
  before        = the suspicion that the decoded gate fails every sport is unverified, and the two
                  coverage quantities are easy to conflate
  bar           = NO pass bar. "Not answerable from the ledger because it holds the wrong quantity"
                  is a FULL SUCCESS and may be the correct answer.
  n             = every ledger row on the pod (CONSTRUCT, exhaustive); state the count
  eye check     = replaced by REPRODUCTION (Q7): quote each command with raw output
  must not move = every coverage_min and every other bar, the harness, the coordinate contract, and
                  every verdict
EVIDENCE: docs/evidence/tracking/g176_decoded_gate_across_sports_2026-09-03.md with the quoted bars,
the per-row table, the pass count, and a NOT VERIFIED list. Commit BEFORE reporting (A7).
TEST: one per-file test only if you add code. NEVER a full pytest.
COMMIT: explicit pathspec only, in a8, no push. Report the sha and how many rows pass the coverage gate.
NEVER PARK.
