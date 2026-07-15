# edge_engine -- the information-edge MACHINE

The pipeline that turns unstructured real-world sources into ONE bounded, leak-free,
pre-line-move adjustment on an EXISTING model knob -- and lets the gate decide
SHIP/REJECT honestly.

THESIS (binding): the edge is NOT a better prediction (the market is efficient on
PRICE). It is a PROPRIETARY + PREDICTIVE + TIMELY input the market has not priced
yet, MANUFACTURED by intelligence-at-scale (an LLM extracting unstructured sources
faster/more completely than the market), then COMBINED into one bounded net
adjustment that fires only BEFORE the line moves.

HONESTY RAILS (enforced in code, non-negotiable):
- The LLM extracts FACTS + an EXTRACTION confidence ONLY. There is NO probability
  field by construction; the LLM never authors a number that enters a prediction.
- Every signal carries an availability_timestamp; the vintage guard asserts it <
  line/pred time. A fact known only after the move is hindsight, not an edge.
- NO edge is CLAIMED. The eval_gate is the JUDGE; an honest REJECT is a SUCCESS.
  No $/ROI/+EV/"money printer" language anywhere.

---

## The pipeline: source -> extract -> vintage -> score(gate) -> combine

```
  real feeds / fixtures
        |
        v
  [1] SOURCE        source.py        SourceAdapter -> NewsItem (stamped captured_at)
        |                            FileSource / MockSource (offline, hermetic)
        |                            LiveSource (STUB; wiring a real feed is HUMAN-RUN)
        v
  [2] EXTRACT       extract.py       LLM-in-one-box reads NewsItem text -> typed FACTS
        |                            extract_llm() = STUB (no live API in CI)
        |                            extract_rule() = deterministic keyword fallback
        v
  [3] VINTAGE       schema.py        validate_signal: required fields, enum membership,
        |           schema_source.py confidence in [0,1], ISO timestamps, and the
        |                            honesty rail -- NO banned outcome/price field on a
        |                            FACT row or inside value_facts.
        |           to_signal:       asserts availability_ts >= source captured_at
        |                            (a fact cannot predate the document that stated it).
        v
  [4] SCORE         score.py         score_candidate: feeds the candidate through the
        |           (the JUDGE)      REAL eval_gate READ-ONLY --
        |                              - walk_forward (leak-free expanding window + purge
        |                                + embargo + vintage assertion),
        |                              - condition the SHIN-devigged close with a single
        |                                BOUNDED logit adjustment, slope fit INSIDE the
        |                                training window only (scheme-prior pattern),
        |                              - restrict scoring to the confirmed-before-line-move
        |                                subset (off-subset returns the close unchanged),
        |                              - brier_skill_score + clustered Diebold-Mariano.
        |                            SHIP iff BSS>0 AND DM p<alpha AND n>=min_n; else
        |                            an honest REJECT (recorded as success).
        v
  [5] COMBINE       combine.py       combine / combine_all: fuse N already-SHIPPED weak
                                     signals for ONE (knob, subject) into ONE clamped
                                     multiplier --
                                       eff = 1 + sum_i(gate_weight_i * conf_i * lean_i),
                                     hard-clamped to the knob's TIGHT band, FIRES only
                                     when |combined lean| >= threshold AND every
                                     contributor is known < line_move_ts (one hindsight
                                     row REFUSES the whole fusion -- no partial leak).
                                     Weak/conflicting evidence -> 1.0 = a NO-OP (the
                                     honest default). The LLM authored none of these
                                     numbers; the gate assigned every weight.
```

The output of [5] is a single bounded multiplier on an EXISTING knob (pace / off_eff /
def_eff / minutes_load / total_pts). It is NOT a prediction; the deterministic
downstream model computes every number a forecast sees.

---

## What is reused READ-ONLY (never reimplemented)

- `scripts/platformkit/freshness/` -- the X1 seed: the LLM-extract-FACTS-only contract,
  the `extracted_at` vintage key, `as_of_reader.assert_vintage` (the leak guard),
  `proxy_quarantine` / `is_fallback_proxy` (post-hoc reconstructions = OPTIMISTIC upper
  bound, never a headline). `combine.py` imports `assert_vintage` directly.
- `scripts/platformkit/eval_gate/` -- the JUDGE: `walkforward.walk_forward`,
  `scoring.brier` / `brier_skill_score`, `dm_test.diebold_mariano` (clustered).
  `score.py` imports these READ-ONLY.
- `scripts/platformkit/ledger/` -- the forward-CLV record (probabilities + outcomes
  ONLY, no $ column). A SHIP verdict is not valid until recorded here with a pred_ts
  before the line move.

This machine GENERALIZES the freshness injury/lineup special-case into a sport-blind
adapter contract: any new source plugs into [1] without touching the gate/extractor.

---

## Running it

Per-file tests only (the full suite freezes the box). From the repo root, run each
test file the same way (swap the filename), e.g.:

```
python C:/Users/neelj/anaconda3/envs/basketball_ai/python.exe -m pytest \
  scripts/platformkit/edge_engine/test_source.py -q
```

Full file list: `test_source.py`, `test_extract.py`, `test_schema.py`,
`test_schema_source.py`, `test_score.py`, `test_combine.py`,
`test_schedule_fatigue_map.py`, `test_cli.py`, `test_facts_store.py`,
`test_injury_daemon.py`, `test_injury_facts.py`, `test_news_facts.py`.

The hermetic path (FileSource/MockSource -> extract_rule -> validate -> score ->
combine) runs with zero network and zero secret, so leak-free behaviour is asserted
deterministically.

---

## What is HUMAN-RUN / time-bound before any dollar can be claimed

- LIVE FEED: `LiveSource` is a STUB. Wiring a real X filtered-stream / presser-ASR /
  weather API / multi-book tape (with server-stamped captured_at, dedupe by source_id,
  no back-dating) is a human-gated step. Forward-capture only; backfill is quarantined.
- LIVE LLM CALL: `extract_llm()` is a STUB. Wiring `instructor.from_anthropic` with a
  key from env is human-run; CI never calls the API.
- REAL HISTORICAL TIMESTAMPED CORPORA (>=2, walk-forward): every PREDICTIVE verdict.
  Some corpora are PAID feeds (The Odds API / Action / VSiN / UmpScorecards archives).
- FORWARD CLV: the only honest proof of timeliness -- recorded in `ledger/` with a
  pred_ts before the line move, graded against the realized close. Time-bound.
- EXECUTION / SPEED LAYER: routing the fired adjustment to a placeable bet inside the
  5-15 min (or seconds, for steam) window is a separate human-gated build.

The deliverable is the MACHINE. No edge is claimed until a candidate passes
the gate on real data with forward CLV.
