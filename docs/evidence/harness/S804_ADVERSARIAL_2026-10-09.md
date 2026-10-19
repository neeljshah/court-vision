# S804 adversarial verifier (tier 2) -- 2026-10-09 (PAPER ONLY)

| round | head | verdict | survivors (non-equivalent) | fix |
|---|---|---|---|---|
| 1 | c1ab24266 | REJECT (12/14) | M13 unescaped dot, M14 date shape `.*` | cfc881bb9 adds traversal, subdir and Xjson paths |
| 2 | cfc881bb9 | REJECT (14/20) | M10/M10c prefix, M15 digit counts, M16 `W?`, M17 `_full_selection`, M18 dash | 197af844a adds explicit paths |
| 3 | 197af844a | REJECT (9/15) | N1 re.I, N2 `[Ww]`, N7 `W[0-9]{1,2}`, N8 `startswith("week")` | 4e367326c adds a near-miss generator (delete, X insert, case swap) and step names |
| 4 | 4e367326c | REJECT (10/20) | `\d`, `jsonl?`, `[W-]`, optional prefix, `[0-9A-Z]`, name.strip, path lstrip/strip/backslash | 65a586256 widens the alphabet and adds the bare weeks/ path |
| 5 | 65a586256 | REJECT (5/15) | `[0-9_]`, `[0-9a]`, `json|txt`, `maker|taker`, `weeks|archive`, `[-_]W`, `.json(.tmp)?`, name.replace | 32483e13c CODE: regex deleted; exact equality with derived week_path(day) |
| 6 | 32483e13c | REJECT (16/19) | M6 year from as_of.year, M17 day_after(day, 2) (M1 +6 equivalent) | 28f8db7c8 adds the 2025-2027 paper_night cross-check |
| 7 | 28f8db7c8 | ACCEPT (15/17 new + M6, M17 killed) | none that break a clause | -- |

Round 7 survivors, all judged not to break a clause:
- N3: `continue` changed to `break`. Only differs when the week step pins a second artifact; paper_night declares one. Advisory gap.
- N8: exempt only the first rolling item. Equivalent, because the week path is pinned once.
- N6: KILLED week step enters the loop. This is the S711 guard on an untouched line, not an S804 clause.
- N4: counter set to True. Cosmetic.
Round 6 cross-check: the original week_path against paper_night._steps' expression (real parse_venue_time and budget template) gave
3,285 comparisons over 2025-2027 with 3 as_of forms each, and 0 disagreements.
Final git status after every round: clean. The builder's own mutant loops (s811/mut804*.py) confirmed each round's survivors killed before re-tiering.

Contract tier: ACCEPT on c1ab24266 (V1-V6). Final ACCEPT on 28f8db7c8 (V1-V11): real 10-06 and 10-07 rolling 1, 10-08 unchanged,
master raises on 10-07, 105 tests passed across 6 files. The tier flagged a literal non-ASCII digit in the test; it was fixed in 8cf82ecfe
by an escape (24 passed).
