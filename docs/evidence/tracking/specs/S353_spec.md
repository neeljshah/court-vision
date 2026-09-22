GAP S353 | sport all (Kalshi discovery) | worktree harness-h7 | log cx_s353_series_scope_status
# Kalshi market discovery filters status == "open" but live markets report "active": the shared pod-path discovers ZERO markets

SINGLE PROBLEM (found by the S341 capture lane on 2026-09-21 against the real venue): scripts/platformkit/ingame/
kalshi_series_scope.py `fetch_open_markets` keeps only rows whose status equals "open". The live API returns "active" for a
tradable market, so the function returns nothing -- the pod capture path (S334) would be blind the day the pod returns. The
S341 local runner works around it with its own discovery copy (local_capture_runner_row.discover_sport).

BINDING BEFORE-CONDITION (re-run, quote): `grep -n "\"open\"" scripts/platformkit/ingame/kalshi_series_scope.py` shows the
filter; and from the local archive, the distinct market status values actually observed:
`grep -o "\"status\": *\"[a-z_]*\"" data/cache/ingame_books_local/kalshi/mlb/*.jsonl | sort | uniq -c | sort -rn | head`
(data/ is absent in a worktree: print ABSENT-IN-WORKTREE for that command and rely on the census the orchestrator pastes below).
ORCHESTRATOR CENSUS (main data tree, 2026-09-21): see the dispatch note appended at the end of this spec.

CHANGE (ADDITIVE, contract B2 -- the existing function name, signature and return shape stay):
1. scripts/platformkit/ingame/kalshi_series_scope.py: introduce a module constant TRADABLE_STATUSES = frozenset({"open", "active"})
   and filter on membership; statuses outside the set are COUNTED and returned in a new optional diagnostics out-parameter or a
   sibling function `fetch_open_markets_with_diagnostics` (never silently dropped without a count). No other behaviour change.
2. tests: extend or add a per-file test beside the existing kalshi_series_scope tests (find them with
   `git ls-files | grep -i series_scope`): a fixture with open / active / closed / settled / unknown rows asserts that open +
   active are kept, the rest are excluded AND counted, and that the old all-"open" fixture output is byte-identical.
3. Memo docs/evidence/harness/S353_series_scope_status_2026-09-21.md: quote the observed status census, and list every other
   module that compares a Kalshi market status to the literal "open" (`grep -rn "== \"open\"\|== 'open'" scripts/platformkit/ingame
   scripts/platformkit/execution`), each with a one-line verdict (same defect / not a market status / already handles active).
   Do NOT fix those in this row; they become follow-up rows.

CONTROLS: infrastructure row; no measured calibration number. ACCEPTANCE: the per-file tests pass; diff touches only the one
module + its test + the memo. Vocabulary follows contract Q6; automated scan required. Memo ends with a NOT VERIFIED list.
The pod is OFF: ignore any pod instruction.

DISPATCH NOTE (orchestrator census, main data tree, 2026-09-21 ~14:55 CDT): over data/cache/ingame_books_local/kalshi/mlb/2026-09-21.jsonl
the market status values observed are: "active" x 1123, "open" x 0. kalshi_series_scope.py compares to the literal "open" at :98
and also SENDS status=open as a query parameter at :73 -- verify from the public API reference whether the query filter value
"open" is still the accepted one for listing tradable markets (the S341 runner lists successfully; read how
scripts/platformkit/ingame/local_capture_runner_row.py discover_sport queries) and keep request and response filters consistent.
