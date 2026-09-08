# S298 preregistration supplement: attempt-2 scoring clauses

This sealed supplement is committed ALONE and BEFORE the first S298 metric of
attempt 2. It supplements, without rewriting,
`docs/evidence/harness/S298_rare_count_mixture_2026-09-07_prereg.md`
(commit 287ae3aca, seal
`906ef129f74c860192046e1c60d21fffb2dd9c98a780efc766f2b30597be082b`). That
preregistration's premise, the two exact source parquets, the CPCV design, the
four scored families, the PMF support and tail cutoff, the six fixed
comparisons, the discrete log-score sign convention, the Holm-adjusted paired
95 percent lower-bound bar, and its SINGLE-WINDOW status all remain unchanged
and are NOT restated as new commitments here. No bar is moved.

## Clauses fixed before scoring

1. INNER-SELECTION DIAGNOSTIC GRANULARITY. The sealed preregistration records
   the deterministic inner strictly-past walk-forward log-score selection "per
   stat and outer fold". The committed candidate 99d4e78c9 instead recomputed
   it once per held-out state. Measured on the real corpus, that recomputation
   is 132,952,773 prior-window fits at 41.7 us per fitted PMF across four
   families and two stats, or about 12.3 hours, which exceeds the pod job
   budget. This supplement fixes, before any metric, that the diagnostic is
   computed exactly ONCE per stat and outer fold, from that fold's
   evaluator-supplied train states in date order, and is stamped unchanged on
   every forecast in that fold. It stays a selection diagnostic only: it
   removes, omits and relabels no outer comparison, every family including the
   worst is still scored and published, and the six fixed comparisons and their
   bar are untouched.

2. SECONDARY SUMMARY EMISSION (verifier CORRECTION 1 of
   `docs/evidence/harness/S298_VERIFY_2026-09-07.md`). The already-sealed
   secondary diagnostics are now aggregated into the JSON summary, per stat and
   family: mean discrete log score, mean ranked probability score, mean
   predicted zero mass, observed zero rate, the absolute difference of those
   two (zero reliability), the mean per-state zero absolute error, the
   randomized-PIT mean, and the KS distance of the sorted randomized PIT from
   uniform. These are summaries of quantities already scored per state. They
   add no comparison, no family and no threshold.

3. PER-FOLD COUNT RAIL (verifier CORRECTION 1). Each CPCV split reports its
   held-out state count, its held-out game-cluster count and its train size in
   the JSON summary. A fold with fewer than 30 held-out game clusters raises
   and stops the run rather than being scored. The preregistration attributed
   this rejection to the shared evaluator; the evaluator does not implement it,
   so the route asserts it directly.

## Declared non-claims and known limits

The CPCV train set straddles the test block on both sides, but every fit in
this route uses only train states STRICTLY EARLIER than the test state. The
earliest date group therefore has no strictly-past train state at all: every
one of its held-out states falls back to the empty-history forecast, in which
all four families place essentially all mass on zero and the paired improvement
is approximately zero by construction. Those states are RETAINED in every
denominator and reported, never dropped after their outcomes are known; the
count is published per fold. This dilutes every comparison toward zero and is
stated as a limit of the sealed design, not corrected after the fact.

Any NULL, BEHIND, REJECT or CLOSED AT LIMIT outcome is a valid result. The
verdict remains SINGLE-WINDOW on one corpus window; no promotion follows from
it. Only new dated artifacts under the `2026-09-07` stem are written; nothing
under `data/`, no register, no ledger row other than the single appended
RESULTS_LEDGER line, and no existing artifact is rewritten.

S298_SUPPLEMENT_SEAL_SHA256=fa854d69bb279e4570403005ac7a7b593b74629bd2d9125de1315e9a369e5a8a
