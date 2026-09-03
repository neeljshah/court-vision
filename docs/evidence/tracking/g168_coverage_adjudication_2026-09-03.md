# G168 coverage adjudication -- denominator limit

Contract: [VERIFIER_CONTRACT.md](VERIFIER_CONTRACT.md), including A2, A7,
section B, Q3, Q7, and Q8. This row uses the three landed inputs named by the
specification without re-deriving them: G164's three coverage quantities,
G161's committed rally labels, and G153/G156a's proof that `decoded_frames`
can reach real ledger rows. It changes no code, field, harness, denominator,
eligibility rule, coordinate contract, verdict, or threshold.

## Q8 current reach re-measurement

At the read-only, batched pod census for this row, the current append-only
ledger contained **12 physical rows and zero tennis rows**. Thus it contains
**zero tennis rows carrying a positive `decoded_frames` value**. The only
current tennis raw table is `tennis_smoke` (`tracking_data.csv`, 1,861 rows);
it has no matching ledger row. The retained local ledger has the older tennis
rows `tennis_06` and `tennis_09`, neither with `decoded_frames`.

The exhaustive eligible denominator for the requested per-table comparison is
therefore **0 tennis table/ledger pairs carrying a decoded-frame denominator**.
Table IDs satisfying that predicate: **none**. This falsifies the premise that
the G153/G156a producer result by itself made a tennis comparison computable:
their real denominator-bearing rows were non-tennis. No decoder count was
estimated, no table was re-tracked, and no process was stopped or restarted.

## The three coverage quantities

G164 establishes that these are distinct quantities and must not share an
ambiguous `coverage_pct` label:

| Quantity | Numerator / denominator | Present tennis denominator-bearing tables | 0.90 adjudication |
| --- | --- | ---: | --- |
| Harness, emitted frames | Frames with at least `min_players` / emitted frames | 0 | **Meetable on its own emitted-frame denominator**: G164's landed direct-evaluation example is 1.0. It is not a decoded-frame comparison and supplies no current tennis table/ledger pair here. |
| Harness, decoded frames | Frames with at least `min_players` / decoded frames after padding | 0 | **Not meetable for the reference clip's whole-clip denominator, CLOSED AT LIMIT.** Even perfect rally solving is capped at 0.3767; margin to 0.90 is -0.5233 (Wilson range -0.5763 to -0.4673). |
| Ledger completeness | Decoded frames that emitted any row / decoded in-play frames | 0 | **Not meetable for the reference clip's whole-clip denominator, CLOSED AT LIMIT.** The same perfect-rally cap is 0.3767; margin to 0.90 is -0.5233 (Wilson range -0.5763 to -0.4673). |

No current per-table numerical row can be printed beneath those headings: the
exhaustive denominator is zero. In particular, the passing emitted-frame
example cannot be relabelled as the decoded-frame quantity, and a ledger
presence rate cannot be relabelled as the pass-deciding harness quantity.

## Reference-clip rally normalisation (reused G161 labels)

This uses G161's committed first-pass labels, not a new label pass and not
G34's different-clip share. G161 reports 113/300 = **0.3767** rally-view share
(Wilson 95% CI [0.3237, 0.4327]) and blind same-rater agreement 49/50 =
**0.980** (Wilson [0.8950, 0.9965]). The agreement limits how precisely any
rally-normalised figure can be read; it is agreement, not independent
validation.

| Reference-clip measure | Rally-normalised value | Interval carried from G161 | 0.90 adjudication |
| --- | ---: | ---: | --- |
| Declaration coverage among estimated rally-view frames | 0.2396 | [0.2086, 0.2788] | Not meetable; point margin -0.6604. |
| Geometry-usable coverage among estimated rally-view frames | 0.1246 | [0.1084, 0.1449] | Not meetable; point margin -0.7754. |

G161's point rally share puts the best possible whole-clip score at 0.3767,
which is 2.39 times below 0.90 (and even the Wilson upper bound 0.4327 remains
2.08 times below it). These are denominator-limit statements only.

## Required reproduction and limit

Q7 calls for reproduction rather than an eye check. A raw-CSV three-column
reproduction is **NOT VERIFIED** because there are zero tennis
table/ledger pairs with the required decoded denominator, and G164 shows the
pass-deciding decoded-frame harness result is discarded rather than recoverable
from the retained raw CSV plus ledger. Constructing a surrogate denominator,
or treating the emitted-frame or ledger quantity as that discarded quantity,
would be circular and non-auditable. The complete current census above is the
applicable exhaustive reproduction for `n = 0 (CONSTRUCT)`.

## Adjudication

**CLOSED AT LIMIT for every whole-clip denominator: the unchanged 0.90 bar is
not meetable on the reference clip.** The emitted-frame harness quantity can
be meetable because its denominator excludes un-emitted frames, but it is a
different G164 quantity and not a substitute for either whole-clip quantity.
The only open question for the orchestrator is which existing, unchanged
denominator definition the 0.90 gate is intended to adjudicate; this row makes
no recommendation or change.

## Verifier-contract self-check

### A

- **A1:** No code changed, so no new per-file test applies; no full suite ran.
- **A2:** Per the specification, the three landed G164/G161/G153-G156a inputs
  were not re-derived. The fresh, read-only batched current census independently
  reproduced the operative reach fact: zero tennis ledger rows and zero tennis
  denominator-bearing table/ledger pairs.
- **A3 / Q7:** `n = 0 (CONSTRUCT)` is exhaustive and Q7 replaces an eye check
  with the census reproduction; no head-slice evidence is used.
- **A4:** Counted physical ledger rows and named every reachable tennis raw
  table/ledger identity relevant to the predicate.
- **A5-A6:** Evidence-only change; no reader, schema, module, deployment, or
  archive landing is involved. Commit uses explicit pathspecs.
- **A7:** All repository evidence paths named here are checked before commit.

### B

| Check | Self-check |
| --- | --- |
| B1 | Clear: the complete eligible set is explicitly zero; no failed rows were excluded. |
| B2-B6 | Clear: no code, schema, field, reader, gate, claim path, deployment, or module changed. |
| B7 | Clear: exhaustive census, no render sample. |
| B8 | Clear: no fitted residual is offered as independent evidence. |
| B9 | Clear: no recycled unit is used; the zero comparison set is named rather than converted into a rate. |
| B10 / Q3 | Clear: the 0.90 bar and every threshold are byte-unchanged; unmeetable whole-clip results are labelled CLOSED AT LIMIT. |

## NOT VERIFIED

- Any numerical three-column tennis table row: none currently carries the
  required decoded-frame denominator.
- A raw-CSV three-column tennis reproduction: impossible on the same zero set;
  no surrogate was made.
- The discarded daemon-path harness quantity for any historical row.
- A denominator-bearing tennis daemon product after the census timestamp.
- Any bar change, alternate bar, rally-scoped bar, or corrected bar.
