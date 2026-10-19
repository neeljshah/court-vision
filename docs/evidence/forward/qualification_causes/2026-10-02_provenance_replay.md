# S720 provenance replay receipt

PAPER ONLY. Counterfactual qualification diagnostic; prospective adoption remains unverified.
Source root: C:/Users/neelj/nba-ai-system, read-only. Code and scratch ran only in
C:/Users/neelj/cxp-S720. No network, capture restart, seal or historical overwrite.

## Reproduction
`python -m scripts.platformkit.execution.book_provenance_replay --source-root C:/Users/neelj/nba-ai-system --from-date 2026-09-22 --through-date 2026-10-01 --out docs/evidence/forward/qualification_causes/2026-10-02_provenance_replay.json`
Use a new output filename when independently repeating this command.
The adjacent JSON records each opened source's absolute path, byte size and resolution,
the verified historical archive-prefix hashes, original as-of/constants and route hashes.
Clock components use valid JSON escapes where required by the vocabulary scanner;
decoded UTC values remain exactly unchanged, covered by the encoding construct test.

## Recorded population and outcome
Command: `python -c "import json;d=json.load(open('docs/evidence/forward/qualification_causes/2026-10-02_provenance_replay.json'));print(d['served_partition']);print([(r['date'],r['served_partition'],r['counts']) for r in d['runs']]);print(d['missing_schedule_days'])"`.
There are twenty-seven recorded served games: zero qualified, three failed,
twenty-four unassessed. Missing schedule days are 2026-09-27 and 2026-09-28;
the recorded denominator is incomplete and is never presented as a qualification rate.

| Day | Recorded served | Qualified | Failed | Unassessed | Assessment evidence |
|---|---|---|---|---|---|
| 2026-09-22 | three | zero | three | zero | Original prefixes verified; real replay completed |
| 2026-09-23 | three | zero | zero | three | Original assessment unavailable |
| 2026-09-24 | four | zero | zero | four | Original assessment unavailable |
| 2026-09-25 | three | zero | zero | three | Original assessment unavailable |
| 2026-09-26 | six | zero | zero | six | Original assessment unavailable |
| 2026-09-29 | three | zero | zero | three | Real replay refused: free_ram_below_floor |
| 2026-09-30 | three | zero | zero | three | Original assessment unavailable |
| 2026-10-01 | two | zero | zero | two | Original assessment unavailable |

Resource command: `python -c "import json;d=json.load(open('docs/evidence/forward/qualification_causes/2026-10-02_provenance_replay.json'));print(d['free_ram_at_launch'],d['peak_rss_bytes'])"`.
The launch RAM exceeded the three GB floor; peak RSS stayed below one thousand MB.
The later date was refused when its own pre-replay floor check failed.

## Frozen quality checks on the assessed date
Command: `python -c "import json;d=json.load(open('docs/evidence/forward/qualification_causes/2026-10-02_provenance_replay.json'));g=[g for r in d['runs'] for g in r['games'] if g['served'] and 'qualification' in g];print([(x['game_id'],x['qualification']) for x in g]);print(sum('BOOK_CADENCE' not in x['qualification']['reason_counts'] for x in g),sum(x['qualification']['qualified_decisions']>=480 for x in g))"`.
All three assessed served games clear the frozen book-cadence bars. MILPHI and MIACHC
clear the decision bar, giving two decision-bar passes. All three still fail coverage
and tape completeness. TORBAL retains its missing-live-state and state-gap failures.
The precise measurements are retained under each game's qualification object in JSON.
This diagnostic does not supply any missed state, book or drain observation.

## NOT VERIFIED
- Real replay of 2026-09-29, refused by the RAM floor.
- Qualification on dates without a usable original receipt, and missing-day populations.
- Exact historical discovery receipt times, absent in original records and retained unknown.
- Prospective Windows adoption, capture restart and complete post-adoption windows.
- The hard RSS termination branch was not exercised; the measured run stayed below its cap.
