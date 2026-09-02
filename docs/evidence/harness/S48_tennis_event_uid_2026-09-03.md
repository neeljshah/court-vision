# S48 tennis `event_uid` -- ACCEPT (premise FALSIFIED, defect real, fix landed)

Contract: `docs/evidence/tracking/VERIFIER_CONTRACT.md`, sections B and Q.
Attempt 1. Calibration evidence only -- no dollar, ROI, profit or edge claim.
The S03 bars (ATP 84.4 / WTA 71.2) are NOT re-adjudicated here; the new rates
below are reported as an instrument reading, and S03 stays CLOSED AT LIMIT.

## Verdict

ACCEPT. The register's stated cause is FALSIFIED (Q8) and the observed defect is
real but lives one layer down. `event_uid` lands as an additive 1:1 key on
`odds.parquet` and on both spines; `coverage_report("tennis", key="event_uid")`
takes `ambiguous_event_id_drop_count` from 186 to 0.

## Step 0 -- premise (Q8): FALSIFIED

The row says the id "is built from players + season, collapsing same-pairing
rematches". Measured on disk, it is not:

```text
ingest_sackmann.py:233 / wta_corpus.py:145
  event_id = f"{YYYYMMDD tourney start}-{tour}-{tourney_id}-{p1_id}-{p2_id}-{match_num}"
```

Tournament and date are ALREADY in the id, and both builders already run a
deterministic dedup pass (`ingest_sackmann.py:246-251`, `wta_corpus.py:162-167`).
So the SPINE id collision count is zero, measured:

| file | rows | distinct `event_id` | colliding ids | colliding rows |
|---|---:|---:|---:|---:|
| `matches.parquet` (ATP spine) | 30,616 | 30,616 | **0** | **0** |
| `wta_matches.parquet` (WTA spine) | 11,270 | 11,270 | **0** | **0** |
| `odds.parquet` | 33,952 | 33,859 | **93** | **186** |

Reproduced by `python -m domains.tennis.event_uid` (the `report()` census).

## Step 1 -- the real cause: the odds JOIN, not the id

`ingest_tennisdata_join.join_odds` walks tennis-data rows and, for each, picks
the best Sackmann match inside `_DATE_WINDOW_DAYS = 20` (:57, :272-284). Nothing
stops two tennis-data rows from two DIFFERENT tournaments claiming one Sackmann
match. Measured over the 93 groups: 93/93 differ in `tournament_td` AND in
`date_td`, 65/93 also in `round_td`, and 0/93 tie on date gap.

```text
20150104-atp-2015-339-105449-105453-20  2015-01-07  Brisbane International  2nd Round
20150104-atp-2015-339-105449-105453-20  2015-01-24  Australian Open         3rd Round
   spine row: 2015-01-04 atp Brisbane R16 Steve Johnson vs Kei Nishikori
```

Attribution rule (deterministic, computable from `odds.parquet` alone because the
id's first 8 characters ARE the tourney start date): inside a colliding group the
row whose `date_td` is nearest that start date keeps `event_uid == event_id`;
every further claimant becomes `<event_id>@<YYYYMMDD>-<tournament slug>`.
Evidence that this picks the true row, over the 93 groups: winner median date gap
2 days vs loser 15 days; the winner's tournament name agrees with the spine's
35/93 by naive substring against the loser's 1/93 (sponsor names differ, e.g.
"Sony Ericsson Open" vs "Miami", so 35/93 is a floor, not the accuracy).

## Step 2 -- rebuild determinism

- **Spines: rebuild PROVEN deterministic and used.** With the new builder code,
  `build_matches(out_dir=<tmp>, tours=["atp"], start_year=2015, end_year=2025)`
  and `build_wta_corpus(out_path=<tmp>)` reproduced 30,616 and 11,270 rows, with
  `list(new.columns) == [*old.columns, "event_uid"]` and every pre-existing
  column `DataFrame.equals` True (0 changed columns). Those tmp artifacts were
  then copied over the live files. NOTE the invocation: the CLI DEFAULT
  (`tours="atp,wta"`, 1968-2026) would emit a COMBINED frame and does NOT
  reproduce the ATP-only file on disk.
- **Odds: rebuild NOT possible from any committed path, so a derivation was
  written instead.** `ingest_tennisdata._cli` reads only
  `data/domains/tennis/_raw/tennisdata/{tour}_{year}.xlsx` (:224-226); that
  directory holds `atp_2015..2026.xlsx` and **no** `wta_*.xlsx`, while the live
  `odds.parquet` carries 8,054 WTA rows. The WTA workbooks sit in
  `data/domains/tennis/wta/_raw_td/` and `grep -rn "_raw_td" --include=*.py` over
  the repo returns **no matches** -- no committed builder consumes them. The
  migration is therefore a derivation from existing columns
  (`python -m domains.tennis.event_uid --apply-odds`), and it refuses to write
  unless the column set is exactly `[*before, "event_uid"]` and every
  pre-existing column survives `DataFrame.equals` (`event_uid.py:_apply`).
- **Gate corpus:** rewriting the spines tripped `corpus_cache`'s source-sha
  guard, so `build_gate_corpus("tennis")` was re-run (that module was NOT
  edited -- LANE V owns it). Rebuilt frame: 41,886 rows, identical column list,
  0 columns changed vs the pre-rebuild copy.

## Step 3 -- `coverage_report("tennis")`, both keys

Default is unchanged and reproduces the S03 landing to every digit.

| | `key=None` (default, `event_id`) | `key="event_uid"` (opt-in) |
|---|---:|---:|
| denominator | 41,886 | 41,886 |
| joined | 33,766 | 33,859 |
| unjoined | 8,120 | 8,027 |
| join_rate | 0.806140476531538 | 0.8083607888077162 |
| `ambiguous_event_id_drop_count` | **186** | **0** |
| bad_price_drop_count | 6 | 6 |
| null_close_count | 75 | 76 |
| scored | 33,685 | 33,777 |
| brier_devig_close | 0.19736835157376564 | 0.19734542370075697 |
| brier_p_base | 0.21620174524743463 | 0.21620286387496576 |

Per `corpus_unit` (never pooled; denominator = the full spine, S35 unmoved):

| unit | denominator | joined (default) | pct | joined (`event_uid`) | pct | S03 bar |
|---|---:|---:|---:|---:|---:|---:|
| ATP | 30,616 | 25,764 | 84.1521 | 25,831 | **84.3709** | 84.4 |
| WTA | 11,270 | 8,002 | 71.0027 | 8,028 | **71.2334** | 71.2 |

`event_uid` Briers, ATP 0.198508 vs p_base 0.216328 and WTA 0.193609 vs
0.215802: the devigged close still beats the corpus baseline on both units. This
is a calibration comparison only.

The `event_uid` rates land exactly on the "distinct spine rows, odds kept-first"
row of the S03 table (25,831 / 8,028) -- an independent confirmation that the
nearest-date attribution picks the same row, and that the 93 recovered rows are
the 93 that S03 dropped rather than new ones. `joined` rises by exactly 93 and
the denominator does not move.

S03's verdict is not mine to change. Read against those bars the instrument now
reads ATP 84.3709 (below 84.4) and WTA 71.2334 (above 71.2); no bar was moved,
lowered, or re-derived by this lane.

## Step 4 -- what landed

Additive only; `event_id` is untouched everywhere and every existing reader was
grepped (`MATCHES_REQUIRED_COLS` is used subset-wise in 3 test files; no test in
the repo asserts an exact column list on any of the three parquets; the only
importers of `close_join` are its two test files).

- NEW `domains/tennis/event_uid.py` (149 lines): `add_spine_event_uid`,
  `add_odds_event_uid`, the additive `_apply` migration, the `report()` census
  and a CLI.
- `domains/tennis/ingest_sackmann.py` + `domains/tennis/wta_corpus.py`: one call
  each, after the existing dedup, so the builders emit `event_uid` from now on.
- `domains/tennis/ingest_tennisdata.py`: `build_odds` appends `event_uid` after
  the stable sort; `ingest_tennisdata_join._empty_joined_df` gains the column so
  the empty-frame schema matches.
- `scripts/platformkit/eval_gate/close_join.py` (299 lines, under the cap):
  `_named_spine`/`_joined_spine_first`/`_joined`/`coverage_report` take an
  OPT-IN `key`; default behaviour is byte-identical; the report gains one key,
  `join_key`. A missing key raises `KeyError` rather than falling back. Soccer,
  which declares no `spine_files`, rejects a non-default key.
- NOT touched: `scripts/platformkit/combo/corpus_cache.py` (LANE V), every
  harness threshold, `data/registry/`, the FWER ledger, any feature flag.

## Commands

```text
python -m pytest domains/tennis/test_event_uid.py -q                      6 passed
python -m pytest scripts/platformkit/eval_gate/test_close_join_tennis.py -q  7 passed
python -m pytest scripts/platformkit/eval_gate/test_close_join_soccer.py -q  4 passed
python -m pytest tests/platform/test_tennis_ingest_sackmann.py -q        23 passed
python -m pytest tests/platform/test_tennis_ingest_tennisdata.py -q      60 passed
python -m pytest tests/platform/test_wta_corpus.py -q                    30 passed
python -m domains.tennis.event_uid            # census, all three parquets
```

Soccer regression: `coverage_report("soccer")` still reports denominator 16,322,
joined 16,322, join_rate 1.0, brier_devig_close 0.23946005675766663,
brier_p_base 0.2627028248079339 -- identical to the S02/S03 landings.
`gate_corpus_states("tennis", "2015-01-01", "2015-12-31")` still returns 3,157
states with `vintage: SYNTHETIC`, matching S03.

## NOT VERIFIED

- The nearest-date attribution is a HEURISTIC, not a proven ground truth. It is
  supported by the 2-day vs 15-day gap separation and the 35/93 vs 1/93 name
  agreement; no row was checked against an external match record.
- The 93 displaced odds rows are NOT re-attached to their true spine rows. They
  now carry a suffixed `event_uid` that joins to nothing, so under the opt-in key
  they are simply unjoined. Whether each has a real spine row, and whether that
  row already holds a price, is unmeasured.
- The join defect itself is NOT fixed: `join_odds` can still let two tennis-data
  rows claim one Sackmann match. `event_uid` makes the result unambiguous
  downstream; it does not make the upstream join one-to-one. A named follow-up.
- `odds.parquet` was migrated by derivation, NOT rebuilt: no committed code path
  can reproduce its 8,054 WTA rows. The pre-existing columns were asserted
  unchanged at migration time, but there is no independent rebuild to check them
  against.
- The spine rebuild determinism was proven only for the recorded invocation
  (ATP-only 2015-2025 / WTA defaults); the CLI defaults do not reproduce the
  files on disk.
- `event_uid` on the spine equals `event_id` exactly, so it is redundant there
  today; it exists so one key name works on both sides of the join.
- `gate_corpus_states` was NOT given the `key` parameter (no caller needs it), so
  every state today is still built on the default `event_id` path.
- No prereg was sealed (Q1), no ledger row charged (Q2), no K read, no walk-
  forward / CPCV ran (Q4), no AHEAD claimed (Q5). This is corpus infrastructure.
- The Briers are unweighted in-sample calibration comparisons on the joined rows.
- No pod deploy (B5), no `data/registry/` write, no flag flip.

## Contract self-check

- B1 nothing excluded from a reported metric: the 8,027 unjoined, 6 bad-price,
  76 null-close and 0 ambiguous rows all sit inside the 41,886 denominator.
- B2 additive: one appended column on three parquets and one appended report key
  (`join_key`); no rename, no removal; readers grepped.
- B3 an odds row with no spine match falls through as unjoined, never quarantined.
- B4 no failure path. B5 no deploy. B6 no module moved or retired.
- B7 the metric is the full corpus, not a head slice. B8 no self-fit.
- B9 denominators are the two full spines, 30,616 and 11,270.
- B10 no threshold moved; the S03 bars are quoted at their spec values and not
  re-adjudicated.
- Q1/Q2 no prereg, no charge. Q3 no bar lowered. Q4/Q5 nothing scored OOS, no
  AHEAD. Q6 calibration language only; no retracted figure appears. Q7 the 93
  groups are enumerated exhaustively (CONSTRUCT), and the corpus metrics are
  whole-corpus reproductions, not samples. Q8 the premise was re-measured FIRST
  and is reported FALSIFIED.
