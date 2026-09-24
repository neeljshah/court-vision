# S409 schedule identity attestation

PREPARE. Construct-only reader; no linkage or qualification changes.

## Binding before-condition

Executed `git show master:<path>` and printed the exact numbered ranges below.
The ingame files reside under `scripts/platformkit/ingame/`.

`scripts/platformkit/execution/forward_capture_bridge.py`
```text
72: def _duplicated(schedule: list) -> set:
73:     """Positions whose (sport, game_id) or (sport, game_key) another entry also claims."""
74:     claims = [((g["sport"], g["game_id"]), (g["sport"], _key(g))) for g in schedule]
75:     ids, keys = Counter(i for i, _ in claims), Counter(k for _, k in claims if k[1])
76:     return {n for n, (i, k) in enumerate(claims) if ids[i] > 1 or keys[k] > 1}
77: 
78: 
79: def _resolve(game: dict, present: set, state_keys: dict, index: dict, candidates: dict) -> tuple:
80:     """Keyed entries link by exact identity; legacy ones by a unique directional candidate."""
81:     sport, key = game["sport"], _key(game)
82:     if key is False:
83:         return None, "invalid_schedule_game_key"
84:     if key is None:
85:         options = [k for k, t in candidates[(sport, game["game_id"])] if game["ticker"] in t]
86:         if len(options) == 1:
87:             return options[0], None
88:         return None, "ambiguous_keyless_candidates" if options else "keyless_candidate_absent"
89:     if (sport, key) not in state_keys:  # A key whose rows conflict is present, not absent.
90:         return None, "state_key_absent" if (sport, key) not in present else "state_key_conflicted"
91:     entry = index.get(game["game_id"])
92:     if entry is None or game["ticker"] not in entry["tickers"]:
93:         return None, "book_event_absent"
94:     event = state_keys[(sport, key)]
95:     if event is not None and event != game["game_id"]:
96:         return None, "linkage_disagreement"
97:     return key, None
```

`scripts/platformkit/execution/forward_schedule_writer.py`
```text
232:                 key = _text(game.get("game_key"))
233:                 stats["linked"] += 1
234:                 stats["link_paths"][key] = link_path
235:                 stats["game_key_sources"][key] = _text(game.get("game_key_source") or "state_archive")
236:                 candidates.append((dict(game_id=event, ticker=ticker, sport=sport, family=family, game_key=key,
237:                                         scheduled_start=game["scheduled_start_utc"], selected_at=selected), rule))
```

`scripts/platformkit/ingame/game_market_link.py`
```text
25: ALIASES: Dict[str, Dict[str, str]] = {"mlb": dict(_MLB_ABBR), "nba": dict(_NBA_ABBR),
26:                                     "soccer": {}, "tennis": {}, "nfl": {}, "ncaaf": {}}
27: LINK_METRICS = Metrics()
28: 
29: 
30: def alias(sport: str, abbr: Optional[str]) -> Optional[str]:
31:     """Apply the existing sport abbreviation aliases."""
32:     if not isinstance(abbr, str) or not abbr:
33:         return None
34:     return ALIASES.get(sport, {}).get(abbr.upper(), abbr.upper())
58: def team_code_from_ticker(ticker: str) -> Optional[str]:
59:     """Retain the outcome suffix as diagnostic evidence only."""
60:     match = _CODE_RE.match(ticker.rsplit("-", 1)[-1])
61:     return match.group(1) if match else None
62: 
63: 
64: def index_kalshi_events(rows: List[Dict[str, Any]], metrics: Optional[Metrics] = None,
65:                         source: str = "linker") -> Dict[str, Dict[str, Any]]:
66:     """Group captured rows and retain only consistent directional metadata."""
67:     metrics = metrics or LINK_METRICS
68:     idx: Dict[str, Dict[str, Any]] = {}
69:     for row in rows:
70:         if not isinstance(row, dict) or not isinstance(row.get("event_ticker"), str):
71:             metrics.drop(source, "market_row_shape_errors")
72:             continue
73:         event = row["event_ticker"]
74:         entry = idx.setdefault(event, {
75:             "date": parse_ticker_date(event, metrics, source), "series": row.get("series"),
76:             "team_codes": set(), "tickers": set(), "home_abbr": None, "away_abbr": None,
77:             "scheduled_start_utc": None, "metadata_conflict": False})
78:         ticker = row.get("ticker")
79:         if isinstance(ticker, str):
80:             entry["tickers"].add(ticker)
81:             code = team_code_from_ticker(ticker)
82:             if code:
83:                 entry["team_codes"].add(code)
84:         for key in ("home_abbr", "away_abbr", "scheduled_start_utc"):
85:             value = row.get(key)
86:             if value is None:
87:                 continue
88:             if key == "scheduled_start_utc":
89:                 value = _timestamp(value, metrics, source)
90:             else:
91:                 value = alias(row.get("sport", ""), value)
92:             if value is None:
93:                 entry["metadata_conflict"] = True
94:                 metrics.drop(source, "market_metadata_invalid")
95:             if entry[key] is not None and value != entry[key]:
```

`scripts/platformkit/ingame/local_state_capture.py`
```text
39:     return dict(sport=sport, game_key=item['game_key'], request_start_utc=request_start,
40:                 response_end_utc=response_end, http_status=receipt.get('http_status', 200),
41:                 source_ts=item.get('source_ts'), state=item.get('state'), state_changed=changed,
42:                 date=item.get('date'), home_abbr=item.get('home_abbr'), away_abbr=item.get('away_abbr'),
43:                 status=item.get('status'), capture_ts=response_end, tick_start_ts=capture_ts,
44:                 raw_sha256=digest, capture_version=CAPTURE_VERSION,
45:                 scheduled_start_utc=item.get('scheduled_start_utc'), date_reason=item.get('date_reason'))
```

`scripts/platformkit/ingame/local_capture_runner_row.py`
```text
44: def envelope(market: dict, kind: str, start: str, end: str, status: int) -> dict:
45:     """Shared additive row metadata; capture time is the response end."""
46:     return {"record_type": kind, "venue": "kalshi", "sport": market["sport"],
47:             "series": market.get("series_ticker"), "ticker": market.get("ticker"),
48:             "event_ticker": market.get("event_ticker"), "venue_status": market.get("status"),
49:             "capture_ts": end, "request_start_ts": start, "response_end_ts": end,
50:             "http_status": status, "capture_version": CAPTURE_VERSION}
63:     out.update(raw_market=deepcopy(m), book=deepcopy(m.get("orderbook", m.get("orderbook_fp"))),
102:                raw_market=deepcopy(market.get("raw_market", market)), book=deepcopy(body))
```

`scripts/platformkit/ingame/local_capture_state.py`
```text
46:                     continue
47:                 state, cadence = classify_state(market, sport, now, client.metrics.errors)
48:                 out.append({**market, "raw_market": deepcopy(market), "sport": sport,
49:                             "series_ticker": series, "event_title": event.get("title"),
50:                             "event_ticker": event.get("event_ticker", market.get("event_ticker")),
51:                             "state": state, "cadence_sec": cadence})
```

## Landed imports read before coding

Read the complete `scripts/platformkit/ingame/game_market_link.py` and
`scripts/platformkit/execution/venue_time.py`. Exact signatures relied on:
```python
def alias(sport: str, abbr: Optional[str]) -> Optional[str]:
def team_code_from_ticker(ticker: str) -> Optional[str]:
def index_kalshi_events(rows: List[Dict[str, Any]], metrics: Optional[Metrics] = None,
                        source: str = "linker") -> Dict[str, Dict[str, Any]]:
def parse_venue_time(value: object) -> float | None:
```
`ALIASES` contains abbreviation substitutions, not full-name translations.
The timestamp parser validates timezone syntax but truncates fractions, so the
new reader must retain the original fraction after shared-parser validation.

## Implementation and scope

Machine: local harness-h77 worktree only; fixture inputs, no archive/network/pod.
Owned module: `scripts/platformkit/ops/schedule_identity_attestation.py`.
Owned tests: `tests/platformkit/ops/test_schedule_identity_attestation.py` and
`tests/platformkit/ops/test_schedule_identity_attestation_1d.py` (fix 1d).
Only the owned Python files and this memo changed. Landed files are unchanged.

MLB is the only sport with a landed resolver name table. The module imports
`KALSHI_ABBR` from `scripts/platformkit/ingame/ingame_id_resolver_mlb.py` unchanged.
Declared aliases use each full name, its nickname, and its unambiguous city.
Split at the last word except red sox, white sox, and blue jays. The standalone
athletics entry has no city. Group cities by distinct normalized codes; Chicago,
Los Angeles, and New York have multiple codes and cannot establish one alone.
A nickname/full name supplies evidence; a bare ambiguous-city occurrence counts
as title_city_ambiguous. Matching is case-insensitive on word boundaries with
whitespace normalized, independently over all seven raw text fields, including
no_sub_title, and the existing event_title carrier.

MLB code vocabulary comes from that table plus landed abbreviation aliases.
Only declared uppercase codes supply token evidence. Every other uppercase
occurrence counts title_tokens_ignored, including clock tokens and repetitions.
Text counters count occurrences per inspected field/row/entry, not distinct games.
Names and tokens never borrow evidence from states or ticker codes. Since fix 1d
(AMENDMENT 3 ruling 3) title_team_names_unmapped is reserved for text with no
resolved code that hit a name-table token resolving to nothing (a bare ambiguous
city); any other text without a resolved code is title_evidence_absent. An unknown
name is never translated to a code. Other sports
(nba, nfl, soccer, tennis, ncaaf) have no landed resolver name table and stay
UNATTESTABLE by title_evidence_absent when state and ticker otherwise agree.

Receipt filtering, nanosecond precision, state conflicts, duplicate handling,
independent ticker evidence, swap detection, stable sorting and atomic writes
retain the candidate's behavior. generated_at is the required as-of cutoff.
The sidecar remains `<schedule.json>.attestation.json`, with zero production
callers and no qualification consequence. No execution quantities are consumed.

## FIX 1b

1. BLOCKING: uppercase token harvesting missed names and treated clock text as
   team codes. Added the declared MLB aliases, valid-code filtering, ignored-token
   and ambiguous-city counters, absent evidence for unsupported sports, and the
   amendment's refusal for unmapped names. The first test uses the verifier's
   verbatim TORBAL raw_market text, including the 6:35 PM EDT clause.
   Before editing the module, its exact failing output was:

```text
E       AssertionError: assert ['EDT', 'PM'] == ['BAL', 'TOR']
1 failed, 47 passed in 0.99s
```

   After the fix, the regression asserts E_title == ['BAL', 'TOR'], ATTESTED=1,
   REFUSED=0, UNATTESTABLE=0 and four ignored clock tokens across two book rows.
   All landed full names, every raw carrier, ambiguous cities, nickname/city
   split exceptions, token boundaries, unknown names, and unsupported sports
   have construct regressions. Base constructs now use MLB because the amendment
   requires absent title evidence for NFL. Existing behavioral checks remain.

2. CORRECTION: the memo omitted the supplied orchestrator BEFORE run. The
   minimal check before this edit failed with:

```text
AssertionError: CORRECTION: verbatim orchestrator BEFORE state is missing
```

   The verbatim BEFORE passage is recorded below. The same check now passes.
   The fix's real re-run belongs to the orchestrator; its count cells are blank.

## BEFORE: orchestrator real run (verbatim from verifier)

> the real run over all six scheduled games returned ATTESTED 0 / REFUSED 6 / UNATTESTABLE 0, reason state_vs_title_mismatch on every game, E_state == E_ticker on every game, E_title == ['EDT', 'PM'] on every game, ignored_record_type 127201, schedule_sha256 27465f64ca2a7ef232a1a3dfd6412f7c448905b9bc30b9c0217f40760eaddadd.

This is the supplied 2026-09-22 BEFORE result, not a run made by this fix lane.
For MLB it reports ATTESTED 0, REFUSED 6, UNATTESTABLE 0, with
state_vs_title_mismatch on every game. No BEFORE result was supplied for 2026-09-23.

## Fix-1b orchestrator real re-run (verbatim from verifier)

> Real re-run: ATTESTED 5 / REFUSED 1 / UNATTESTABLE 0; title_tokens_ignored 16520; title_city_ambiguous 2600; ignored_record_type 127201. MIACHC is REFUSED state_vs_title_mismatch with E_state ['CHC', 'MIA'], E_ticker ['CHC', 'MIA'], E_title ['MIA'] -- the venue's text names 'Chicago' without a nickname, so the ambiguous-city rule correctly maps it to nothing, and the title evidence is a consistent PROPER SUBSET, not a contradiction.

## Construct verdicts

Base fixture denominators are two entries; the verbatim TORBAL fixture has one.

| Fixture | ATTESTED | REFUSED | UNATTESTABLE | Reason |
|---|---:|---:|---:|---|
| Verbatim TORBAL | 1 | 0 | 0 | none |
| Matched MLB | 2 | 0 | 0 | none |
| Exchanged game_keys | 0 | 2 | 0 | schedule_identity_swapped |
| Ambiguous city only | 0 | 2 | 0 | title_team_names_unmapped |
| Unknown names or prose | 0 | 0 | 2 | title_evidence_absent |
| Unswapped doubleheader | 2 | 0 | 0 | none |
| Start 02:10Z, state date local | 2 | 0 | 0 | none |
| Clock text alone | 0 | 0 | 2 | title_evidence_absent |
| Unsupported sport | 0 | 0 | 2 | title_evidence_absent |
| No outcome suffix | 0 | 0 | 2 | ticker_codes_absent |
| Conflicting home codes | 1 | 1 | 0 | state_team_set_conflicted |
| Repeated identical run | 2 | 0 | 0 | byte-identical sidecar |

## FIX 1c

1. BLOCKING: reproduced MIACHC with title `Chicago wins` and rules `Miami vs Chicago ...`.
   The construct failed before the module edit:
```text
E         {'ATTESTED': 0} != {'ATTESTED': 1}
E         {'REFUSED': 1} != {'REFUSED': 0}
1 failed, 103 passed in 1.35s
```
   Non-empty title subsets now attest only when state and ticker sets agree.
   Attested partial entries carry title_partial=true and sorted title_codes_unresolved.
   by_sport counts partial games and each unresolved code once per attested game.
   Regression: MIACHC attests with ['CHC'] unresolved; two partial games count twice;
   swapped keys still refuse both games. Contradictions and empty titles keep their rules.
2. CORRECTION: the memo check reproduced `AssertionError: CORRECTION: verbatim fix-1b real re-run is missing`.
   The verbatim record now follows AMENDMENT 1 BEFORE above; the same check passes.
   Fix-1c real re-run cells remain blank for the orchestrator.
   After the module fix: `104 passed in 1.16s` (construct test file).

## FIX 1d

Verdict file `_verdict_s409_1d.md` (two Opus tiers, ACCEPT WITH CORRECTIONS);
rulings in spec AMENDMENT 3. Each failing case was reproduced on constructs
before the module edit, then re-run after it:

```text
BEFORE DH      ({'ATTESTED': 0, 'REFUSED': 2, 'UNATTESTABLE': 0}, [('dh1', 'schedule_identity_swapped'), ('dh2', 'schedule_identity_swapped')], {})
BEFORE LATE    ({'ATTESTED': 0, 'REFUSED': 0, 'UNATTESTABLE': 1}, [('late', 'state_teams_absent')], {})
BEFORE PROSE   ({'ATTESTED': 0, 'REFUSED': 1, 'UNATTESTABLE': 0}, [('p', 'title_team_names_unmapped')], {})
BEFORE BADDATE ({'ATTESTED': 0, 'REFUSED': 0, 'UNATTESTABLE': 1}, [('b', 'state_teams_absent')], {'month must be in 1..12': 1})
AFTER  DH      ({'ATTESTED': 2, 'REFUSED': 0, 'UNATTESTABLE': 0}, [('dh1', None), ('dh2', None)], {})
AFTER  LATE    ({'ATTESTED': 1, 'REFUSED': 0, 'UNATTESTABLE': 0}, [('late', None)], {})
AFTER  PROSE   ({'ATTESTED': 0, 'REFUSED': 0, 'UNATTESTABLE': 1}, [('p', 'title_evidence_absent')], {})
AFTER  BADDATE ({'ATTESTED': 0, 'REFUSED': 0, 'UNATTESTABLE': 1}, [('b', 'state_teams_absent')], {'invalid_state_date': 1})
```

1. CORRECTION (tier 1 item 1, tier 2 C1; ruling 1): a doubleheader is not a swap.
   None is dropped from the swap detector's admitted reasons, so only entries that
   already fail their own pairwise check can be swap-paired. Regression: an unswapped
   BAL/TOR doubleheader asserts ATTESTED 2 in both input orders; a different-team
   swap is still REFUSED schedule_identity_swapped on both games.
2. CORRECTION (tier 1 note 3, tier 2 C2; ruling 2): state rows are located by
   game_key on the UTC date of the start OR its venue-local date, both candidates,
   deduplicated. The venue-local date is the event ticker's date token (the forward
   schedule writer links on local date == ticker date), admitted only within one day
   of the UTC date. Rows on both dates merge; differing teams refuse as
   state_team_set_conflicted. Regressions: the 02:10Z start with state date
   2026-09-22 (and with 2026-09-23) attests; a conflict across the two dates refuses;
   a ticker date two days away is not a candidate. The earlier construct
   test_utc_schedule_date_and_absent_state now attests the -05:00 start and asserts
   state_teams_absent only for a state date on neither candidate.
3. CORRECTION (tier 1 note 4, tier 2 C3; ruling 3): the NON_NAMES word list is
   retired. No resolved code and no ambiguous-city hit is title_evidence_absent;
   title_team_names_unmapped only when an ambiguous city resolved to nothing.
   Regressions: 'Will the game go to extra innings', unknown full names, and
   "Postponed. Sacramento A's" are UNATTESTABLE title_evidence_absent; 'Chicago wins'
   and 'Los Angeles at New York' are REFUSED title_team_names_unmapped. Two unknown-name
   parameters moved from the old unmapped test to the absent test.
4. CORRECTION (tier 2 C4; ruling 4): a malformed state date counts the named reason
   invalid_state_date; the library message never enters record_counts. Regression:
   '2026-13-22', '2026-02-30' and '2026-09-00'.
5. CORRECTION (tier 1 item 2, tier 2 C5; ruling 5): the fix-1c real re-run is
   recorded verbatim in the handoff table below; the fix-1d and 2026-09-23 rows are
   left for the orchestrator.

The module stays at 300 lines. Notes N1-N6 are unchanged by ruling.

## Validation

Each test file ran separately with
`python -m pytest <file> -q -p no:cacheprovider`.

- `tests/platformkit/ops/test_schedule_identity_attestation.py`: 102 passed (fix 1d).
- `tests/platformkit/ops/test_schedule_identity_attestation_1d.py`: 16 passed (fix 1d).
- `tests/platformkit/execution/test_forward_capture_bridge.py`: 60 passed, unchanged.
- `tests/platformkit/execution/test_forward_capture_bridge_keyed.py`: 34 passed, unchanged.
- `tests/platformkit/execution/test_forward_schedule_writer.py`: 45 passed, unchanged.
- `python -m scripts.platformkit.ops.schedule_identity_attestation --help`: exit 0.
  This row has no self-check CLI flag; the construct tests provide its self-check.
- Contract preflight: nine PASS, zero FAIL over the four owned files (fix 1d), base
  master and `docs/evidence/tracking/specs/S409_spec.md`. All files are ASCII
  and at most 300 lines. The tracked diff is empty; the owned files are untracked.

## Orchestrator handoff

Run `python -m scripts.platformkit.ops.schedule_identity_attestation` with
`--schedule <schedule.json> --states <explicit-state-files> --books <explicit-book-files>`
and `--generated-at <zoned-as-of-time>`. The fix's real re-run is the
orchestrator's work. It must attest all six 2026-09-22 games, with MIACHC title_partial and ['CHC'] unresolved.

| Real re-run | ATTESTED | REFUSED | UNATTESTABLE | Per-sport/per-reason counts |
|---|---|---|---|---|
| Fix-1c, 2026-09-22 | 6 | 0 | 0 | MIACHC title_partial true, title_codes_unresolved ['CHC']; title_city_ambiguous 2600; title_tokens_ignored 16520; ignored_record_type 127201 |
| Fix-1d, 2026-09-22 | | | | orchestrator |
| 2026-09-23 | | | | orchestrator, after its games have played |


Orchestrator real re-run after FIX 1d (2026-09-23 17:05Z, from the h77 candidate over the real 2026-09-22 shards; the same
inputs as the AMENDMENT 1 and 2 runs; --generated-at 2026-09-23T17:05:00Z): exit 0; ATTESTED 6 / REFUSED 0 / UNATTESTABLE 0;
CINATL, TORBAL, CLEBOS, MILPHI, STLPIT attested with E_state == E_title == E_ticker; MIACHC ATTESTED with title_partial true
and title_codes_unresolved ['CHC'] (E_title ['MIA']); record_counts ignored_record_type 127201, title_city_ambiguous 2600,
title_tokens_ignored 16520 -- identical to the fix-1c counts, as AMENDMENT 3(5) requires. The 2026-09-23 schedule's run is
NOT VERIFIED until its games have played.

## NOT VERIFIED

- The fix-1c real re-run counts are the orchestrator's report, not rerun here;
  the fix-1d real re-run and any 2026-09-23 run are the orchestrator's.
- A swap WITHIN a doubleheader (same teams, same day) is undetectable from team
  evidence and attests both games; the ticker's time token would discriminate
  (a later row). A construct pins this limit.
- The venue-local date comes from the event ticker's date token; real late-evening
  starts and real doubleheader rows are not verified.
- Sports other than MLB on real rows; absent name tables supply no title evidence.
- Real archive coverage, network, pod, live captures, STOP files, or integration.
- Power loss beyond injected fsync/replace failures; concurrent writers.
- Independent final acceptance and a committed SHA.
