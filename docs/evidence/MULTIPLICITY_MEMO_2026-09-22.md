# The Multiplicity Memo -- 0 of 60 candidate signal classes survived

Job-evidence artifact 7. Calibration and sharpness language only. Headline: **zero survivors, and that is the completed
result.**

**Read this before the table.** These artifacts record **verdicts, not statistics**. Every per-candidate studentized
statistic on disk is `NA` and every SPA verdict is `NOT_EVALUABLE` (`scripts/platformkit/eval_gate/spa_catalog_report.txt:9-68`),
because the historical per-signal loss differentials were never archived (`:3-5`). No ranking by distance to threshold
can be produced from them. The path to per-candidate statistics is the next test, S396, in section 9.

**Where these files live.** Most citations below resolve in a bare public clone. Three do not, and are named once here
rather than implied to be checkable: `scripts/platformkit/combo/fwer_budget.py` and `domains/*/signal_catalog*.py` are
private-repository paths, and `data/cache/eval_gate/backtest_fwer.jsonl` is a local-only cache, gitignored in both
repositories. Claims resting on those three are labelled where they appear.

## 1. The question
Does any declared candidate signal lower walk-forward loss against the devigged close by enough to survive the cost of
having looked at many candidates at once? The benchmark is the devigged close (`spa_catalog_report.txt:2`), never raw
accuracy.

## 2. The family: what counted as one hypothesis

One hypothesis = **one catalog signal class**, enumerated mechanically by walking the AST of
`domains/*/signal_catalog*.py` and taking every `ClassDef` whose name ends in `Signal`
(`scripts/platformkit/eval_gate/retro_correction.py:15-23`) -- no human picks membership. **60 classes: NBA 16, MLB 14,
soccer 15, tennis 15**, re-measured this session by AST, matching
`docs/evidence/harness/SIGNAL_INVENTORY_REDTEAM_2026-09-03.md:39-42` and
`scripts/platformkit/eval_gate/retro_correction_report.txt:69` (`catalog_signals_on_disk=60`).

**Declared where -- and the date is not on record.** The sweep width is fixed in source as a constant,
`RETRO_SWEEP_TRIALS = 85`, commented "do not shrink to archive survivors" (`retro_correction.py:12`), with a
**fail-closed guard**: if the catalog ever grows past 85 the renderer raises rather than pricing its Bonferroni epsilon
too loosely (`retro_correction.py:34-39` -- a `raise`, not an `assert`, so `python -O` cannot delete it). The width is
wider than the family it prices (85 > 60) and can only be conservative. **No artifact dates that registration**; the only
support is the source comment, and `docs/JOB_EVIDENCE_PACKET.md:276` calls 85 "the per-row `n_trials` multiplicity
constant" without calling it pre-registered. The general rule the module obeys: membership frozen and pinned by content
before any p-value is seen, and **no past verdict is ever re-scored under a looser bar** (`fwer_budget.py:31-33`).

## 3. The K accounting

**Charge rule.** A charged trial appends its ledger row *before* computing anything and reports the K it read **at
launch**; K read after scoring is an automatic reject (`docs/evidence/tracking/VERIFIER_CONTRACT.md:35`, Q2 -- written
after nine unrelated trials moved K from 3 to 12 between prereg and launch and flipped a verdict); an unmeetable bar is
CLOSED AT LIMIT, never lowered (`:36`, Q3). **K for this sweep = 85** (`retro_correction_report.txt:8-67`, the `n_trials`
column on every one of the 60 rows; summary at `:69`).

**eps_eff.** Bonferroni-on-eps, `eps_eff(eps, K) = eps / max(1, K)`, monotone decreasing in K (`fwer_budget.py:64-74`),
with `DEFAULT_EPS = 0.05` sitting as the middle line of `fwer_budget.py:53-55` (its rationale comment, the constant, then
the corpora-cap note). The same `eps_eff = alpha / k` relation is restated in the public tree at
`scripts/platformkit/eval_gate/deflated_metrics.py:67`. Stated motivation: gating K candidates at a fixed eps gives
`P(>=1 false SHIP) ~= 1 - (1-eps)^K`, so a wider search must get **stricter, not looser** (`fwer_budget.py:3-9`).
**FWER budget at K = 85: eps_eff = 0.05 / 85 = 0.00058824** (`retro_correction_report.txt:69`, 8 decimals).

**Replication floor.** `min_corpora_eff = min(n_corpora, 2 + floor(log2 K))` capped at 4 (`fwer_budget.py:77-88`). At
K = 85 the raw floor is 2 + 6 = 8, capped to **4 corpora** -- a fixed cap that exists so a genuine two-corpus signal
stays reachable (`fwer_budget.py:55-56`).

**Cumulativity.** K never resets by splitting a search into small cycles; the ledger carries a running total
(`fwer_budget.py:104-111`, the phrase at `:106`). The live charged ledger holds **19 rows, `k_cumulative` 1..19**
(`data/cache/eval_gate/backtest_fwer.jsonl`, local-only, read this session) -- a **different quantity** from the 85 sweep
width; the two must not be mixed.

## 4. The null

**What the machinery is.** Hansen's consistent SPA over a **stationary bootstrap of whole-game clusters** -- each game
contributes one mean loss differential, so repeated in-game states cannot manufacture evidence
(`scripts/platformkit/eval_gate/spa_test.py:1-6, 32-55`). Defaults: `n_bootstrap = 2000`, `seed = 2718`,
`mean_block_length = 5.0`, `alpha = 0.05` (`spa_test.py:83-85`); geometric restart draw (`:68-80`); consistent recentering
at `sqrt(2 log log n_games)` so clearly inferior candidates stay uncentered (`:96-100`); family p = `(1 + exceed) /
(B + 1)` (`:112`).

**What the artifact did: it did not draw.** `family_spa_p = NA (historical per-signal loss differentials are not
archived)`, "no SPA survivor can be inferred" (`spa_catalog_report.txt:3-4`, written unconditionally by
`spa_test.py:119-124`). **No bootstrap was run over these 60 candidates.** The draw count and seed above are module
defaults, not parameters of an executed catalog run.

**The one null that did execute** is the planted-null calibration lane: 200 synthetic candidates, **0 ships**, nominal
alpha 0.050000, observed null ship rate 0.000000 against a 0.100000 ceiling, 279.444 s, PASS; LABEL-ECHO and MARKET-ECHO
exploit lanes both BLOCKED at 0 ships (`scripts/platformkit/eval_gate/post_hardening_revalidation_report.txt:1-6`). That
shows a different instrument -- the scoring gate -- does not manufacture false positives. It is **not** a null for the
60, and section 7 does not borrow it back.

## 5. The deflated threshold each candidate faced, and why

Every candidate was priced at **eps_eff = 0.00058824** (0.05 / 85), not 0.05 (`retro_correction_report.txt:69`).
Bonferroni-on-eps rather than Benjamini-Hochberg within the family, for two reasons stated in the module: it is
**assumption-light and FWER-correct without any independence assumption** (`fwer_budget.py:64-74`), and a within-family BH
bar at q = 0.05 is **strictly looser**, admissible only for a family frozen before the first family-relative trial and
never for re-scoring recorded verdicts (`fwer_budget.py:26-33`). This catalog is heavily dependent by construction -- 46
of the 60 class names carry Elo or Rest, and most members are interactions or transforms of those two primitives
(`EloXRestDiffSignal` at `spa_catalog_report.txt:17`, `AbsRestDiffXEloMismatchSign` at `:22`; the 14 carrying neither are
back-to-back, rolling-win, lambda and surface terms). Under that dependence the looser bar would need a proof nobody has;
the stricter bar holds regardless.

## 6. The result table

Both artifacts enumerate all 60 rows; nothing is omitted.

| Column | What is on disk | Source |
|---|---|---|
| raw verdict | `REJECT` x 60 | `retro_correction_report.txt:8-67` |
| corrected verdict | `REJECT` x 60 | same |
| per-test bar | `0.00058824` | `retro_correction_report.txt:69` |
| survivors | `0` | `retro_correction_report.txt:70` |
| studentized_stat | `NA` x 60 | `spa_catalog_report.txt:9-68` |
| spa_verdict | `NOT_EVALUABLE` x 60 | same |
| family_spa_p | `NA` | `spa_catalog_report.txt:3` |

**Stability re-run** after the gate was hardened: `before_survivors=0 after_survivors=0`, `before_documented_rejects=60
after_documented_rejects=60`, `report_content=IDENTICAL`, PASS (`post_hardening_revalidation_report.txt:8-12`).

**The closest ten candidates cannot be named.** No per-candidate statistic, loss differential or distance to the bar
exists on disk for any of the 60. The rule that closes this hole was written later and is not retroactive: **Q9 ARCHIVE
THE DIFFERENTIAL** -- a scored artifact stores its per-unit paired-loss series (both losses, cluster id, timestamp) and an
archived as-of state beside the summary, because "a CI that cannot be recomputed from the artifact alone is not a result"
(`VERIFIER_CONTRACT.md:63-70`, added 2026-09-03 after an NBA halftime claim could not be re-scored). Ranking arrives with
the next test, not this one.

## 7. The honest reading

**What zero survivors says.** At a sweep width of 85 and the resulting per-test bar of 0.00058824, **none of these 60
declared candidates was recorded as separating from the devigged-close benchmark**, and the correction preserved every
documented REJECT without inferring a single survivor (`retro_correction.py:26-27, 42-44`). The correction is stable
across a gate hardening. It is not underwritten by the planted-null lane: **the renderer that produced this report writes
the literals `REJECT`, `REJECT` for every pair and computes no statistic** (`retro_correction.py:51`). The planted-null
PASS in section 4 is evidence about a different lane.

**What it does not say.**
1. **Not that no signal exists.** These 60 did not clear this bar on these corpora at this power.
2. **Not that the 60 faced the SPA null.** They did not: the loss vectors were never archived, so the family test is
   `NOT_EVALUABLE` -- which the artifact states in its own header rather than papering over (`spa_catalog_report.txt:3-5`).
3. **The result is partly an evidence boundary, not purely a statistical one.** The published catalog outcome was
   REJECT-first and the differentials are gone, so the correction could only ever *preserve* rejects -- it had no
   mechanical path to producing a survivor (`retro_correction.py:27, 42-44, 51`). That asymmetry is a known failure mode:
   a gate applied to the **sampling** prunes precisely the evidence that could falsify the claim. The claim here is "zero
   survivors" and no adversarial check on it can be run from disk. Honest status: **0 of 60 REJECT with the falsification
   branch unavailable**, not "0 of 60 tested and refuted".
4. **The family is shallow.** Sixty transforms of Elo, rest, back-to-back, rolling win, lambda and surface primitives is
   a narrow search; zero survivors there says little about a deeper family.

**Four counts that are not the same population.** The **60** are the catalog classes corrected here. The **85** is the
sweep width that prices their bar. The **19** are charged rows in the live FWER ledger. The **513** recorded REJECT/DEFER
verdicts quoted by `EVIDENCE.md:60` and `README.md:29` are different again -- all NBA and MLB signal candidates in the
reject ledger, `scripts/platformkit/reject_ledger.py`, counted by `python -m scripts.platformkit.reject_ledger show`
(`docs/JOB_EVIDENCE_PACKET.md:139`, inside section G at `:123-146`). `EVIDENCE.md:60` points the 0-of-60 row at that
section G, and for the 513 the pointer resolves exactly. It is **incomplete rather than wrong**: the multiplicity
correction itself is recorded in the packet's do-not-claim material at `:276`, not in section G.

## 8. What it would take to detect a candidate of the size that matters

Power arithmetic: `docs/evidence/POWER_PAGE_2026-09-22.md`. `MDE = 1.429 * half-width` at 80 percent power (`:19-24`);
the smallest interesting Brier effect is the venue cost scale **0.004375** (`:43`); a 30-game floor precedes any interval
(`:120`). The power page's requirement spans **all five** of its rows -- 8,823 / 9,940 / 4,852 / 8,318 / 8,448 games, so
**4,852 to 9,940 games** end to end (`:111-117`) -- to resolve a cost-scale Brier effect at the ordinary 95 percent level.
A per-test bar of 0.00058824 instead of 0.05 widens the required interval further, so **treat that band as a lower bound
for a multiplicity-corrected family test**; the exact inflation is NOT COMPUTED here.
Practical reading: a cost-scale effect is not detectable inside one sport-season per candidate under this bar. Either the
corpus grows by an order of magnitude, or the family shrinks to a handful of pre-registered candidates so K stops eating
the bar, or the effect hunted is larger than cost scale.

## 9. The next test: S396, the family audit under sealed manifests

Spec: `docs/evidence/tracking/specs/S396_spec.md` (161 lines, four binding amendments). What it changes:

- **One charge per family, not per member.** Exactly one `_charge_ledger` call for the whole family; `k_at_launch` is the
  charged row's own `k_cumulative`; `family_allowance = eps_eff(0.05, k_at_launch)`; `member_allowance =
  family_allowance / n_declared_evaluable`, a Bonferroni allocation written as Decimal strings (`S396_spec.md:40-44`).
- **Sealed manifest first.** One JSON per family listing each member's signal_id, source, one-line hypothesis, builder
  name and evaluability; `seal()` writes a sibling `.sha256`; the digest is the family's `hypothesis_hash`; committed
  before any run; any extra look is a NEW manifest and a NEW charge (`:29-39`). The charge is idempotent per digest -- an
  identical retry after a crash is REFUSED with K unchanged (AMENDMENT 3(c), `:114-117`).
- **Evaluability declared before scoring.** Measured this session by AST over `domains/*/signal_catalog*.py`: **27 of 60
  classes reference a `.store`, `.read` or `.extra` attribute anywhere in the class body (NOT_EVALUABLE by input); 33 do
  not.** Per sport: NBA 16 (6 NE), MLB 14 (3 NE), soccer 15 (**15 NE -- the entire soccer catalog**), tennis 15 (3 NE).
  This reproduces the count asserted in AMENDMENT 2(b) (`:98-103`), which also records why gating on the declared
  `reads_atlas = []` alone would have sealed all 60 as evaluable, inflating the allowance divisor.
- **Q9 satisfied.** Per-game paired Brier and log-loss differences archived beside the summary, reconstructing the point
  to 1e-9 (`:47-48, 66`), so "which candidate was closest" becomes answerable. The Romano-Wolf step-down is a secondary
  column and never decides, NOT_EVALUABLE members consume nothing, and the full matrix is published (`:52-53`).

**The blocker, measured and unresolved.** Rows returned by the landed `load_states` carry an unzoned `state_ts` and
**neither `reference_available_at` nor `settled_at`**, so the runner refuses them twice over; availability and settlement
timestamps come from the real corpus contract and are **never synthesized, defaulted or back-filled**, and until that
contract carries them the affected rows are **NOT VALIDATED** (AMENDMENT 4(a), `:127-133`). S396 cannot yet produce
numbers on the real corpus.

## 10. Reproduction

The first two **regenerate** their report in place (`write_report`, `write_catalog_report`), so "reproduce" here means
regenerate, not read-only verify: compare the regenerated bytes against the committed file.

```
cd /c/Users/neelj/nba-ai-system && python -m scripts.platformkit.eval_gate.retro_correction
cd /c/Users/neelj/nba-ai-system && python -m scripts.platformkit.eval_gate.spa_test
cd /c/Users/neelj/nba-ai-system && python -m scripts.platformkit.reject_ledger show
cd /c/Users/neelj/nba-ai-system && python -c "import ast,glob;C=[n for p in sorted(glob.glob('domains/*/signal_catalog*.py')) for n in ast.parse(open(p,encoding='utf-8').read()).body if isinstance(n,ast.ClassDef) and n.name.endswith('Signal')];H=[n for n in C if any(isinstance(a,ast.Attribute) and a.attr in ('store','read','extra') for a in ast.walk(n))];print(len(C),len(H),len(C)-len(H))"
```

The AST census prints `60 27 33`. Its predicate matches a `.store`, `.read` or `.extra` attribute on **any** receiver
anywhere in the class body, not only `self.` or `ctx.` inside a build body; it needs the private
`domains/*/signal_catalog*.py` tree. Per-file tests, NOT RUN this session (per-file only, never the suite):
`python -m pytest scripts/platformkit/eval_gate/test_retro_correction.py -q`, same for `test_spa_test.py`.

## 11. NOT VERIFIED

- **Every per-candidate statistic.** All 60 studentized stats are `NA`; `family_spa_p` is `NA`. No candidate can be named
  as closest to its threshold, and no calibration curve can be drawn for this result: neither a per-candidate statistic
  nor a per-game loss differential is on disk for any of the 60.
- **The bootstrap never drew for these 60.** `n_bootstrap = 2000`, `seed = 2718`, `mean_block_length = 5.0` are module
  defaults (`spa_test.py:83-85`), not parameters of an executed catalog run.
- **The 85 trials, their registration date, and the exploit lanes.** The width is fixed in source
  (`retro_correction.py:12`) but no artifact enumerates the 85 trials, their dates or their seals, and no artifact dates
  the registration; `post_hardening_revalidation_report.txt:5-6` prints `outcome=REDACTED` for LABEL-ECHO and MARKET-ECHO,
  which was not read.
- **Q1 (PREREG SEALED BEFORE SCORING) is not checkable from the live ledger.** It carries no seal column at all:
  `data/cache/eval_gate/backtest_fwer.jsonl` rows hold only `at`, `end`, `k_cumulative`, `predictor`, `sport` and
  `start`. The 513 REJECT/DEFER count was not re-counted this session.
- **The S396 runner does not exist in the working tree.** No `scripts/platformkit/eval_gate/signal_audit_*.py`, no
  `tests/platformkit/eval_gate/test_signal_audit_*.py`, no `docs/evidence/harness/S396_signal_audit_2026-09-22.md` (only
  the archived critique `docs/evidence/harness/S396_astra_r4_critique_2026-09-22.md`, which was not read). The line
  references named by AMENDMENTS 4(a), 4(b), 4(c) and 4(e) -- into `signal_audit_catalog.py`, `signal_audit_family.py`,
  `signal_audit_verdicts.py` and that missing memo -- are therefore uncheckable here. AMENDMENT 2(b) names no line
  reference.
- **`data/registry/signal_registry.parquet` was not opened**, so the packet's registry figures at `:276` are unchecked.
- **Nothing was executed beyond the AST census.** Neither regeneration command above nor any pytest was run this session.

Last verified: 2026-09-22.

NOT VERIFIED
