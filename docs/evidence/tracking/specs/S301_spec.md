GAP S301 | sport all | worktree aXX | log cx_s301_unique_state_key_routes
CONTRACT: docs/evidence/tracking/VERIFIER_CONTRACT.md sections B and Q (Q1-Q9) and the B5 NOTE -- read first.
CONTEXT: routes are cpcv_engine.cpcv_evaluate, walkforward.walk_forward, and
  cpcv_distribution.cpcv_evaluate_distributional; none rejects duplicate state keys.
S277 attempts exposed this failure mode; S271 is not yet landed and is not evidence.
PREMISE (step 0): show 0/3 routes raise on an exact duplicate state key today (a 4-row fixture with one duplicate
  passes through each route; print the record counts).
CHANGE (step 1): additive module scripts/platformkit/eval_gate/state_key_guard.py (<= 120 lines) with
  assert_unique_state_keys(states) raising ValueError("duplicate state key: <key>"), wired into each of the three
  routes ONLY as an additive pre-check behind a keyword argument that defaults to the CURRENT behaviour (off), so
  existing callers and archived numbers are unchanged; S-rows opt in. Test tests/platformkit/eval_gate/
  test_unique_state_key_routes.py: each route raises on an exact duplicate when the guard is on, accepts two games
  at one wall-clock time, and reproduces its fixture score byte-identically with the guard off.
  Seal a prereg FIRST as its own commit (LF; seal = SHA-256 of the STAGED bytes above the seal line via git show
  :<path>, verified with git show HEAD:<path>; the seal TEST reads the FILE, normalizes CRLF to LF, hashes above
  the seal line). Never write data/ or docs/research/; never rewrite an existing artifact (new dated filenames);
  engines and every existing module byte-identical unless the CHANGE names the file (SHA-256 printed).
WHERE: local construct only. POD: n/a; above 500 MB use ~/bin/pod_run <aN> --fetch <outputs> -- <command>.
ACCEPTANCE RULE (the verifier applies exactly this and nothing else):
  metric        = per route: raises on exact duplicate (guard on); accepts simultaneous distinct games; fixture
                  score identical with guard off (max abs diff)
  before        = 0/3 routes reject duplicate keys (audit section D)
  bar           = 3/3 raise on duplicate; 3/3 accept simultaneous games; 3/3 max abs diff = 0 guard off vs today
  n             = 6 (CONSTRUCT: three routes x two fixtures, enumerated exhaustively)
  eye check     = n/a (S-row); reproduction = verifier reruns the test file and one guard-off replay per route
  must not move = split constants, purge, embargo, defaults; every archived artifact; nothing charged
NON-TAUTOLOGY: the duplicate fixture and the simultaneous-games fixture differ only in game_id.
EVIDENCE: docs/evidence/harness/S301_unique_state_key_routes_2026-09-04.md + JSON.
TEST: exactly tests/platformkit/eval_gate/test_unique_state_key_routes.py; run only that file.
REPORT: 3x3 table, engine SHA-256 before/after, test line, SHA. No push. NEVER PARK.
