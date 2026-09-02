# S38 -- envelope follow-ups (b) (c) (d); (a) documented only

**Verdict: ACCEPT. 50-probe envelope 16 GREEN / 34 RED -> 21 GREEN / 29 RED.**
No assert was weakened (VERIFIER_CONTRACT Q3) -- the one test change ADMITS a fifth
status the contract already documents and adds a STRICTER check on it. Every one of
the 29 remaining reds is a human-gated P-row: 28 x `OK_NO_STALENESS_DAYS` (P1) and
1 x `OK_NO_SOURCE_ARTIFACT` + `OK_NO_AS_OF` (P3, system_health).

Files this lane owns and changed:
`scripts/platformkit/answers/resolver_registry.py`,
`scripts/platformkit/intel_query/compose_scout.py`,
`scripts/platformkit/intel_query/compose_comparables.py`,
`tests/platformkit/mcp_server/test_envelope_contract.py`, this memo.
Human-gated check: none of these is under `src/`, `kernel/`, `api/`, `intel/` or
`scripts/team_system/` (`.claude/rules/human-gated-paths.md`), and
`scripts/platformkit/**` is named there as a safe build area. No PROPOSED diff was
needed -- the resolver tree lives entirely under `scripts/platformkit/`.

## Before -> after (the same command, both measured on this box today)

    python -m pytest tests/platformkit/mcp_server/test_envelope_contract.py -q -p no:cacheprovider

| run | result | probes green / red (of 50) |
|---|---|---|
| BEFORE (HEAD, this lane's diff `git stash`ed off) | `34 failed, 17 passed in 98.64s` | **16 / 34** |
| AFTER  (this lane's diff applied) | `29 failed, 22 passed in 103.18s` | **21 / 29** |

(51 tests = 50 probes + 1 probe-file shape test, which passes in both runs.)

**Drift correction vs the S27 memo (Q8):** S27 recorded 15 green / 35 red. Re-measured
at HEAD before touching anything, the same test gives **16 green / 34 red** -- probe
**E04** ("how much money can we make beating the closing line") is now correctly
`refused` and passes. That is S27's NEW GAP 5 closing underneath us, by a producer
outside this lane; it is NOT a result of this diff (it is green in the BEFORE run).
The honest denominator for this lane's own work is therefore 16 -> 21, **+5 probes**.

## The five probes this lane turned green

| probe | tool | was | cause fixed |
|---|---|---|---|
| A02 | ask (nba rating_attribute) | `NOTOK_NO_NOTE` | (b) |
| A07 | ask (soccer rating_attribute) | `NOTOK_NO_NOTE` | (b) |
| A08 | ask (soccer mechanism_effect) | `BAD_STATUS:'ambiguous'` + `NOTOK_NO_NOTE` | (c) |
| S04 | scouting_report (soccer, team profiles only) | `NOTOK_NO_NOTE` | (b) |
| S05 | scouting_report (nba, unresolvable player) | `NOTOK_NO_NOTE` | (b) |

## (b) every `no_data` carries a `note`

Grep of the `no_data` emitters behind those probes, then the two branches that were
silent (every other `no_data` in the resolver tree already carries a `note`, `reason`
or `missing` -- checked with `grep -rn "no_data" scripts/platformkit/answers/`):

1. `scripts/platformkit/answers/resolver_registry.py:1175-1181` -- the
   `player_stat` / `rating_attribute` branch returned
   `{status, category, sport, detail}` and no `note`, so a consumer got NO_DATA with
   the reason buried inside `detail`. Now emits `note` via a new
   `_ask_lookup_note(r, query, sport)` that names the reason per `answer_lookup`
   status (`no_data` = no profiles built for the sport; `no_entity` = no name
   matched; `no_attribute` = entity resolved but no registered attribute matched,
   with the count and first 12 available; `ambiguous` = the candidate list), plus a
   `source_artifact` via `_ask_profiles_source(sport)` (the
   `data/cache/profiles/<sport>_*_profiles.parquet` glob `answer_lookup` actually
   reads -- a glob, not one file, because it loads every profile parquet for the
   sport). `detail` is kept verbatim: purely additive (B2).
2. `scripts/platformkit/intel_query/compose_scout.py:257-264` -- the
   "player found on NO scouting axis" `no_data` carried a `missing` LIST but no flat
   `note`. `missing` is kept; a `note` naming the same miss (0 of N concept axes, no
   VERIFIED shooter facet, no raw attribute rows, and the parquet it read) is added.
3. `scripts/platformkit/answers/resolver_registry.py:757` -- `mechanism_effect`'s
   zero-row `no_data` had a `source_artifact` and no `note`; added.

## (c) `ambiguous` -- the fifth status, admitted AND made stricter

`docs/AI_CONSUMER_CONTRACT.md:78` already documents it ("Multiple DIFFERENT
mechanisms match a fuzzy query -> `status: 'ambiguous'` with a `candidates` list").
The S27 envelope enumerated four statuses, so every real `ambiguous` scored
`BAD_STATUS`. Adjudication: **admit it**, because the contract is the spec and the
implementation matches the contract; the envelope was the thing that was wrong.

Admitting it alone would have LOOSENED the test, so the same commit adds a check the
other not-ok statuses do not carry: an `ambiguous` envelope must have BOTH a `note`
(the shared not-ok rule) AND a `source_artifact` (`AMBIGUOUS_NO_SOURCE_ARTIFACT`) --
an answer that lists candidates must say what it read them from. The one shipped
`ambiguous` emitter that lacked both, `resolver_registry.mechanism_effect:774`, now
emits the ledger path and a note naming the match count and the candidate list. The
two `ambiguous` emitters that already complied (`compose_scout:227`,
`compose_comparables:121`) were not touched.

Net effect on the test: +1 admitted status, +1 new violation code. No existing
violation code, bound or assert was removed or relaxed.

## (d) comparables: `as_of` is the corpus's date, not the wall clock

`compose_comparables._envelope` stamped `as_of = datetime.now(...)` on every answer
although the answer is read off `data/cache/profiles/nba_player_profiles.parquet`
(built 2026-07-26). Fixed in the ONE function every branch of that module routes
through:

- `as_of` = the corpus's own date -- the parquet mtime, via the existing
  `compose_scout._as_of` (reused, not re-implemented);
- `corpus_staleness_days` = how far that sits from now (already in the test's
  `_META_NUMERIC` allowlist, so a not-ok envelope may carry it);
- `computed_at` = the wall clock, as its own separate key;
- corpus absent -> `as_of` falls back to the call time and `corpus_staleness_days` is
  `None` (an unbuilt corpus has no date to report). The now-unused `_now()` helper
  was deleted.

Measured: C01's violations go from `OK_ASOF_IS_WALL_CLOCK` + `OK_NO_STALENESS_DAYS`
to `OK_NO_STALENESS_DAYS` only. C01-C03 stay RED on P1 alone. A pinned corpus is not
refused on age -- it reports its age.

## (a) `staleness_days` -- DOCUMENTED ONLY (P1, human)

Not emitted by this lane. The only implementation in the repo is
`scripts/platformkit/mcp/gate_manifest_tool.py`, which is not wired into
`tools.TOOLS`; wiring it and restarting the MCP server is P1
(`MCP_ADVANCE_2026-09-01.md` s2), a human step. 28 of the 29 remaining reds are this
single cause, spread over 12 of the 13 tools.

## The 29 remaining reds, by cause (exact, re-measured)

| cause | n | probes | owner |
|---|---|---|---|
| `OK_NO_STALENESS_DAYS` | 28 | A01 A06 A09 A11 A13 · S01 S02 S03 · C01 C02 C03 · M01 M02 M03 · W01 W02 W03 W04 · R01 R02 R03 R04 R05 · X01 X02 X04 X05 X06 | **P1 (human)** |
| `OK_NO_SOURCE_ARTIFACT` + `OK_NO_AS_OF` | 1 | H01 (`system_health`) | **P3 (human)** |

Two probes carry a SECOND violation on top of P1, both pre-existing and both outside
this row's scope: W01-W04 `OK_ASOF_IS_WALL_CLOCK` (P2, `winprob_dispatch.dispatch`
stamps `_now_iso()` over corpora 78-81 days old -- the same class (d) fixed for
comparables, but `winprob_dispatch` is a separate P-row) and X06
`OK_ASOF_UNPARSEABLE: '2026-09-02T14:10:16.438907+00:00 (no rows)'` (S27 NEW GAP 6).

## Per-file tests (all green, all in master)

    scripts/platformkit/answers/test_mechanism_effect.py            19 passed in 1.30s
    scripts/platformkit/answers/test_resolver_registry_routing.py   37 passed in 1.01s
    tests/platformkit/intel_query/test_compose_comparables.py        6 passed in 0.96s
    tests/platformkit/intel_query/test_compose_scout.py             11 passed in 7.25s
    tests/platformkit/mcp_server/test_envelope_contract.py          29 failed, 22 passed in 103.18s

A5 (readers of every touched field): `as_of` and `source_artifact` are RENDERED by
`answers/contract_client.py:38-92` and described by `mcp_server/tools.py:132,235`;
both read the keys by name and both keys still exist with the same types -- only
comparables' `as_of` VALUE changed. `answers/mcp_smoke.py:40` already listed
`ambiguous` in `VALID_STATUS` and already required a `no_data` reason at :97-99, so
this diff moves the shipped surface toward the smoke checker, not away from it. No
key, status value or field was renamed or removed (B2 clean).

## NOT VERIFIED

- **(a) is not fixed, only documented.** 28 of 50 probes stay RED for it. Nothing in
  this diff emits `staleness_days`, and this lane may not wire P1 or restart the MCP
  server.
- **P2 (win_probability) and P3 (system_health) untouched** -- named, not repaired.
  The (d) fix is comparables-only; `winprob_dispatch.dispatch` still stamps the wall
  clock on 4/4 sports.
- **Cross-box portability:** 50/50 outcomes were measured on THIS box only, and S27
  already recorded two artifacts changing underneath a run. E04 flipping green
  between S27 and this lane is a live demonstration; a re-run elsewhere can differ.
- The `note` texts added in (b) were checked against the probes that exercise them
  (A02 A07 S04 S05); the `no_attribute` and `ambiguous` branches of
  `_ask_lookup_note` are exercised by no probe in the fixed 50 and are unverified on
  live data.
- `corpus_staleness_days` is derived from the parquet MTIME, not from a build stamp
  inside the corpus. A file copied or re-touched without a rebuild would report a
  fresher corpus than it is.
- Calibration language only (Q6): no dollar, ROI, profit or edge claim anywhere in
  this memo, the diff or the ledger line. The one mention of the refusal path is a
  guard's name, in a refusal context. RED is the honest deliverable; 29 remaining
  reds are a measurement, not a failure.
