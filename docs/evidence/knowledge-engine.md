# The Hypothesis-to-Verdict Knowledge Engine -- folklore in, pre-registered verdicts out

> Sports folklore goes in; leak-free, pre-registered verdicts come out; and the nulls are
> published as first-class results, not buried. The single truth-source for any figure below is
> [docs/JOB_EVIDENCE_PACKET.md](../JOB_EVIDENCE_PACKET.md) section G. Where a later working-tree
> recount reads higher than the packet's committed count, both are shown and labeled -- the
> packet stays the truth-source. No dollar/edge/ROI is claimed anywhere on this page; a NULL is
> market-efficiency evidence, and an honest REJECT is a success.

---

## The claim

"Teams on a back-to-back shoot worse." "Momentum is real." "Home dogs cover." Sports is drowning
in folklore, and almost none of it is tested against leak-free data. This system turns each belief
into a pre-registered hypothesis, runs it through the same refutation gate every signal faces, and
records the verdict -- CONFIRMED, NULL, REJECT, or NOT_TESTABLE -- in an append-only ledger, one
per sport. The engine has been drained across all four sports: no open, untested beliefs are left
in a backlog. Roughly half of the testable folklore survives locally; the rest is null or
not-testable, and every null is kept and published rather than deleted. That honest shape is the
point.

---

## How a hypothesis travels: seed -> gate -> ledger -> resolver receipt

**Seed.** A hypothesis enters either from a cited external source or from the zero-LLM
self-proposal cycle. The literature-to-verdict loop ran twice in one overnight session:
21 hypotheses seeded from cited sources (12 in round one, 9 in round two) and closed the same
session, each landing a real verdict rather than a cherry-picked positive
(commits `e500a0d6`, `1bc7d622` seed; a chain of closers records the verdicts).

**Gate.** Every candidate passes the same leak-free ship gate the signal loop uses --
expanding walk-forward (all folds must improve), a null-shuffle permutation control requiring
z >= 3, an ablation against the full model, train-median imputation, and a Benjamini-Hochberg
FDR correction for multiple comparisons (`src/loop/gate.py`). Most candidates correctly get
rejected. The interaction factory is the gate at composition scale: it takes confirmed
single-mechanism findings and composes them into two-way interaction candidates, then adjudicates
every one -- 146 rows at the packet's committed count, the large NULL/NOT_TESTABLE majority being
the gate doing its job.

**Ledger.** The verdict is appended to `domains/<sport>/knowledge/validation_ledger.jsonl` with
its effect size, sample n, p-value, corpus, and source note on the row. The ledger is append-only
and audited: a dedupe pass found 42% of rows (135 of 321) were exact-content duplicates from a
missing guard at the shared writer, and the fix added a content-identical guard plus a one-time
documented squash with per-sport backups (commit `78d503ee`) -- verified afterward that the
ledgers kept growing under concurrent writers with zero new duplicates.

**Resolver receipt.** An answer never free-associates a plausible-sounding basketball belief.
The deterministic resolver reproduces the ledger's own numbers byte-for-byte and refuses any
unregistered question. Live-verified this session:

```
$ python -m scripts.platformkit.answers.contract_client "does b2b_rest_penalty hold up" --sport nba
CONFIRMED_LOCAL  effect=-1.73  n=4732  p=0.0056
source: domains/basketball_nba/knowledge/validation_ledger.jsonl
```

Those numbers are copied from the ledger row, not computed on the fly. The same rows feed a
queryable "what affects what" effect graph (555 nodes / 296 edges at the packet's count), every
edge a verbatim ledger row -- no new statistics invented at answer time.

---

## The honest tallies

**Truth-source (packet HEAD, 2026-07-10):** 197 combined ledger rows across the four sports --
89 confirmed, 74 honest NULLs, and 34 not-testable/other. A large NULL share is the expected
shape of a real audit, not a shortfall.

**Later recount (working tree, 2026-07-22 -- the ledger grows under the live autoloop, so this
reads higher):** 287 combined rows -- NBA 85, MLB 86, soccer 64, tennis 52. Rolled up by verdict
family: 129 confirmed, 31 not-testable, 127 tested-but-not-confirmed. That is a 50.4% survival
rate over the 256 testable hypotheses -- about half the folklore holds up locally, half does not
([`mechanism_survival.json`](../../scripts/platformkit/analytics_showcase/out/mechanism_survival.json)).

Once the interaction-factory composition ledger is included alongside the four sport ledgers, the
nulls dominate outright -- the published honesty exhibit tallies nulls (351) outnumbering confirms
(168) by 2.1x across the five ledger sources. The point of the exhibit is that ratio: the system
logs and keeps its honest rejects instead of hiding them.

![Verdict mix across each sport's validation ledger: nulls outnumber confirms 2.1x](../img/honesty_exhibit.png)

*Figure: verdict mix per sport plus the interaction-factory bar. Data:
[`honesty_exhibit.json`](../../scripts/platformkit/analytics_showcase/out/honesty_exhibit.json).*

---

## Receipts

| Stage / artifact | What it establishes | Committed path |
|---|---|---|
| Seed: literature-to-verdict loop | 21 cited hypotheses seeded + closed same session | commits `e500a0d6`, `1bc7d622` (+ closer chain); rows in the sport ledgers |
| Gate: leak-free ship gate | walk-forward + permutation z>=3 + ablation + FDR before any verdict | `src/loop/gate.py` |
| Gate at scale: interaction factory | 146 composed two-way candidates, all adjudicated | `data/cache/intel_claims/interaction_factory_ledger.jsonl` |
| Ledger: append-only verdicts, 4 sports | 197 rows (packet HEAD); 287 later recount | `domains/{basketball_nba,mlb,soccer,tennis}/knowledge/validation_ledger.jsonl` |
| Ledger integrity: dedupe audit + repair | 42% duplicate rows found, guard added at shared writer + squash w/ backups | commit `78d503ee` (writeup local-only under `docs/research/`) |
| Resolver receipt: anti-folklore client | reproduces verdict + n + p + source byte-for-byte, refuses unregistered questions | `scripts/platformkit/answers/contract_client.py`, `resolver_registry.py` |
| Effect graph | queryable what-affects-what, edges copied verbatim from ledgers | `scripts/platformkit/answers/effect_graph.py` |
| Honest-tally exhibit | nulls 351 vs confirms 168 (2.1x) | `scripts/platformkit/analytics_showcase/out/honesty_exhibit.json` |
| Survival rollup | 129 confirmed of 256 testable = 50.4% | `scripts/platformkit/analytics_showcase/out/mechanism_survival.json` |

---

## Reproduce (per-file only)

The four sport ledgers are committed, so these reproduce on a fresh clone:

```
# Reproduce one verdict deterministically from the committed ledger
python -m scripts.platformkit.answers.contract_client "does b2b_rest_penalty hold up" --sport nba

# Regenerate the honest tallies from the ledgers
python -m scripts.platformkit.analytics_showcase.honesty_exhibit
python -m scripts.platformkit.analytics_showcase.mechanism_survival

# Recount raw verdict splits directly
python -c "import json,collections,glob; c=collections.Counter(json.loads(l)['verdict'] for f in glob.glob('domains/*/knowledge/validation_ledger.jsonl') for l in open(f,encoding='utf-8') if l.strip()); print(sum(c.values()),'rows',dict(c))"
```

The interaction-factory ledger lives under gitignored `data/cache/`, so on a fresh clone the
exhibit's interaction bar degrades to the four committed sport ledgers rather than fabricating a
number.

---

## Why this matters

Anyone can assert that back-to-backs hurt shooting. The hire signal is a machine that turns each
assertion into a pre-registered, leak-free test, keeps the negative results as first-class output,
audits its own ledger for duplicate pollution, and answers only by reproducing a recorded verdict
-- never by improvising a plausible-sounding belief. Folklore goes in; a verdict with a sample
size, a p-value, and a source path comes out; the honest majority that does not survive is
published, not hidden. That discipline -- not any single confirmed effect -- is the product.

---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](../INDEX.md) - [Home](../../README.md) - [Glossary](../GLOSSARY.md)
