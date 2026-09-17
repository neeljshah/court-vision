# The Analytics Site -- a Reviewer's Map

**Live site:** https://neeljshah.github.io/court-vision/analytics/

CourtVision Analytics is a static, dated snapshot that publishes descriptive
measurements of forecast calibration against real outcomes and devigged
closing markets across basketball, baseball, soccer, and tennis. It is a
Next.js app (`webapp/`) exported to static HTML and deployed to GitHub Pages
by [`.github/workflows/deploy-demo.yml`](../.github/workflows/deploy-demo.yml).
Every number on the site is a citation, not a claim: it links to the
committed JSON artifact that produced it and the date it was measured.
**This is a calibration reader. It makes no edge, ROI, or profit claim** --
see [`docs/JOB_EVIDENCE_PACKET.md`](../docs/JOB_EVIDENCE_PACKET.md), the
single truth source for what may and may not be claimed.

This document is the map: for every pillar page, what it shows, where the
number comes from, and what CI gate stops a wrong number from shipping.

---

## 1. Site map

All URLs verified `200` on 2026-09-17 with
`curl -s -o /dev/null -w "%{http_code}" -L <url>`. None were dropped.

| Page | What it shows | Source artifact(s) | Generator module |
|---|---|---|---|
| [Overview](https://neeljshah.github.io/court-vision/analytics/) | Landing dashboard: module counts, headline calibration example, paper index | [`webapp/public/data/showcase/`](../webapp/public/data/showcase) (all modules) + [`calibration_stability.json`](../webapp/public/data/showcase/calibration_stability.json) | `scripts/platformkit/analytics_showcase/*.py` (all showcase modules) |
| [Papers](https://neeljshah.github.io/court-vision/analytics/papers/) | Index of published research papers, one per calibration/measurement question | [`webapp/public/data/papers/`](../webapp/public/data/papers) (29 files) | authored papers, evidence-checked against `out/*.json` by `check-paper-evidence.mjs` |
| [Papers / one paper](https://neeljshah.github.io/court-vision/analytics/papers/how-to-read-a-courtvision-paper/) | A single paper's sections with inline evidence citations | [`how-to-read-a-courtvision-paper.json`](../webapp/public/data/papers/how-to-read-a-courtvision-paper.json) | n/a (authored; evidence resolved at build time) |
| [Calibration](https://neeljshah.github.io/court-vision/analytics/calibration/) | Reliability bins (mean predicted vs. observed) with bootstrap CIs, model vs. market | [`calibration_stability.json`](../webapp/public/data/showcase/calibration_stability.json) | `scripts/platformkit/analytics_showcase/calibration_stability.py` |
| [State reliability](https://neeljshah.github.io/court-vision/analytics/state-reliability/) | Calibration error by probability band x game-state time bucket, model vs. closing reference | [`state_conditioned_calibration.json`](../webapp/public/data/showcase/state_conditioned_calibration.json) | `scripts/platformkit/analytics_showcase/state_conditioned_calibration.py` |
| [Forecaster](https://neeljshah.github.io/court-vision/analytics/forecaster/) | Published pregame + in-game calibration checks (walk-forward proof + aggregate receipts) | [`results/winprob_walk_forward_results.json`](../results/winprob_walk_forward_results.json), [`state_conditioned_calibration.json`](../webapp/public/data/showcase/state_conditioned_calibration.json), [`murphy_decomposition.json`](../webapp/public/data/showcase/murphy_decomposition.json), [`calibration_stability.json`](../webapp/public/data/showcase/calibration_stability.json), [`brier_skill_scores.json`](../webapp/public/data/showcase/brier_skill_scores.json), [`cross_sport_scoreboard.json`](../webapp/public/data/showcase/cross_sport_scoreboard.json) | `stage_webapp_assets.py` copies these five aggregates into `forecaster/`; each has its own generator module |
| [Experimental metrics](https://neeljshah.github.io/court-vision/analytics/novel/) | Candidate novel-stat cards (market foresight, schedule fatigue, load-bearing index, etc.), each with a SHIP/REJECT-style verdict | [`novel_stats_index.json`](../webapp/public/data/showcase/novel_stats_index.json) | `scripts/platformkit/analytics_showcase/novel_stats_index.py` |
| [Measurement lab](https://neeljshah.github.io/court-vision/analytics/lab/) | Interactive scatter/distribution explorer over established + candidate measurements | `webapp/public/data/showcase/*.json` (module-selectable) | varies by selected module |
| [Compare](https://neeljshah.github.io/court-vision/analytics/compare/) | Side-by-side comparison of two Atlas profiles within one published pack (client-side fetch of static JSON) | `webapp/public/data/showcase/atlas_*.json` | `scripts/platformkit/analytics_showcase/atlas_factory.py` family |
| [Library](https://neeljshah.github.io/court-vision/analytics/browse/) | Searchable index of every published measurement, finding, and explainer | [`explainers.json`](../webapp/public/data/explainers/explainers.json) + showcase/insights/papers/findings indexes | `libraryData.ts` composes from the same showcase/insights/papers artifacts |
| [Ask Scout](https://neeljshah.github.io/court-vision/analytics/ask/) | Q&A search over the published corpus; answers cite source artifacts | [`webapp/public/data/ask/corpus.json`](../webapp/public/data/ask) + every showcase/paper/explainer artifact | `scripts/platformkit/analytics_showcase/build_ask_corpus.py` |
| [Findings](https://neeljshah.github.io/court-vision/analytics/findings/) | Index of individually-titled research findings (momentum, parity, shrinkage, verdict flips, etc.) | [`findingsIndex.ts`](../webapp/lib/analytics/findingsIndex.ts) composed from each finding's own artifact | one generator per finding, e.g. `nba_momentum_tested.py`, `league_parity_index.py` |
| [Findings / Retraction](https://neeljshah.github.io/court-vision/analytics/findings/retraction/) | Six withdrawn headline figures with defect, withdrawal date, editorial date, and replacement | [`RETRACTIONS`](<../webapp/app/(analytics)/analytics/findings/retraction/retractions.ts>) sourced from `docs/JOB_EVIDENCE_PACKET.md` | authored; not a generated artifact |
| [Findings / Data integrity](https://neeljshah.github.io/court-vision/analytics/findings/ingame-join-integrity/) | The in-game join-integrity incident: fail-closed audit, revision-2 re-segmentation, before/after receipts | [`mlb-ingame-integrity.json`](../webapp/public/data/audits/mlb-ingame-integrity.json), [`mlb-ingame-regeneration.json`](../webapp/public/data/audits/mlb-ingame-regeneration.json), [`mlb-ingame-timing-regeneration.json`](../webapp/public/data/audits/mlb-ingame-timing-regeneration.json) | `scripts/platformkit/check_ingame_join_integrity.py`, `scripts/platformkit/segment_ingame_join.py` |
| [About](https://neeljshah.github.io/court-vision/analytics/about/) | Scope statement, what is/isn't claimed, and how to read the site | authored copy | n/a |
| [Evidence & Platform](https://neeljshah.github.io/court-vision/analytics/evidence/) | Chart gallery + pipeline ledger + links to `JOB_EVIDENCE_PACKET.md` / `PLATFORM.md` / `KNOWN_LIMITATIONS.md` | `webapp/public/img/showcase/*.png` + [`site_manifest.json`](../webapp/public/data/showcase/site_manifest.json) | `scripts/platformkit/analytics_showcase/build_site_manifest.py` |
| [Explainers](https://neeljshah.github.io/court-vision/analytics/explainers/) | Plain-language essays explaining methodology (Brier, ECE, walk-forward, etc.) | [`explainers.json`](../webapp/public/data/explainers/explainers.json) | authored |
| [Research loop / claim history](https://neeljshah.github.io/court-vision/analytics/the-loop/) | The full ledger of every forward claim made, with verdict and date | [`fwd_claim_scoreboard.json`](../webapp/public/data/showcase/fwd_claim_scoreboard.json) | `scripts/platformkit/analytics_showcase/fwd_claim_scoreboard.py` |
| Inspector: module detail (dynamic, e.g. [`/analytics/m/agent_fleet_history/`](https://neeljshah.github.io/court-vision/analytics/m/agent_fleet_history/)) | Raw output + human-written insight for one showcase module (one static page per module) | `webapp/public/data/showcase/<id>.json` + `webapp/public/data/insights/<id>.json` | the module's own generator; enumerated from `site_manifest.json` |

Additional footer-only inspectors not repeated above (same showcase/insights
pattern): `pitch-sequencing`, `count-context`, `score-decomposition`,
`residual-anatomy`, `observation-dependence`, `blowout-timing`,
`state-contrasts`, `cross-sport-comparability`, `players` (all-entities
browser). Each reads its own named artifact under `showcase/` or `insights/`
following the same loader pattern documented in Section 3.

---

## 2. What "showcase" vs. "insights" vs. other data folders mean

| Folder | File count | Contents |
|---|---|---|
| [`webapp/public/data/showcase/`](../webapp/public/data/showcase) | 102 | Raw module output JSON -- one file per analytics module, machine-generated |
| [`webapp/public/data/insights/`](../webapp/public/data/insights) | 241 | Human-written headline/verdict/caveat text paired 1:1 with a showcase module id |
| [`webapp/public/data/papers/`](../webapp/public/data/papers) | 29 | Authored long-form papers with an `evidence[]` array citing showcase/insights artifacts |
| [`webapp/public/data/ask/`](../webapp/public/data/ask) | 9 | Ask Scout's search corpus and answer index |
| [`webapp/public/data/audits/`](../webapp/public/data/audits) | 3 | Incident receipts (the in-game join-integrity finding) |
| [`webapp/public/data/explainers/`](../webapp/public/data/explainers) | 1 | Methodology essays, one JSON file holding all essays |
| [`webapp/public/data/forecaster/`](../webapp/public/data/forecaster) | 1 | Staged walk-forward proof receipt for the Forecaster page |

---

## 3. How a number gets onto the site

1. A generator module in [`scripts/platformkit/analytics_showcase/`](../scripts/platformkit/analytics_showcase) (e.g. `calibration_stability.py`) reads a real corpus (e.g. `data/cache/ingame_grade_joined/`) and writes one JSON file to `scripts/platformkit/analytics_showcase/out/<module>.json`, tagged with `as_of` / `generated_on` and an `edge_claimed=False` field.
2. [`check_all.py`](../scripts/platformkit/analytics_showcase/check_all.py) runs every module's own `--check` mode sequentially and writes `out/check_all_report.json` -- a pass/fail scoreboard, not a build step.
3. [`build_site_manifest.py`](../scripts/platformkit/analytics_showcase/build_site_manifest.py) scans `out/*.json` + `out/atlas_*_manifest.json` + `docs/img/*.png` and writes `out/site_manifest.json`: one honest row per module (title, one-liner, `as_of`, evidence-page link) plus top-level counts. Paths are always repo-relative, never a box-local absolute path.
4. [`validate_webapp_artifacts.py`](../scripts/platformkit/analytics_showcase/validate_webapp_artifacts.py) shape-validates every artifact the webapp will blindly `as T`-cast in TypeScript, so a shape drift fails loudly here instead of silently rendering wrong.
5. [`stage_webapp_assets.py`](../scripts/platformkit/analytics_showcase/stage_webapp_assets.py) copies `out/*.json` into `webapp/public/data/showcase/` (and chart PNGs into `webapp/public/img/showcase/`, and the five forecaster aggregates into `webapp/public/data/showcase/forecaster/`), repairing mojibake and rewriting any leaked absolute path to repo-relative. Authors do not run this by hand; the gate phase does, and it is committed to git.
6. A page's server loader (e.g. [`webapp/lib/analytics/stateReliability.server.ts`](../webapp/lib/analytics/stateReliability.server.ts)) reads the committed file straight off disk at Next.js build time with `readFileSync(join(process.cwd(), "public", "data", "showcase", "<file>.json"))` -- some pages (Compare, parts of the Lab) instead `fetch()` the same static JSON client-side from `/data/showcase/`, since the file is already public.
7. The page component renders the parsed JSON directly; nothing is recomputed or summarized differently between the JSON file and the page.
8. `next build` with `NEXT_PUBLIC_DATA_MODE=snapshot` statically exports every route (module pages included, via `generateStaticParams()` off `site_manifest.json`) to `webapp/out/`, which GitHub Pages serves as-is -- there is no live backend and no runtime fetch to anything outside the committed JSON.

---

## 4. What stops a wrong number from shipping

| Gate | File | What it blocks | Runs |
|---|---|---|---|
| Artifact shape validation | [`scripts/platformkit/analytics_showcase/validate_webapp_artifacts.py`](../scripts/platformkit/analytics_showcase/validate_webapp_artifacts.py) | A JSON shape drift that a blind TypeScript `as T` cast would silently mis-render | before staging, part of the showcase build |
| Module self-check | [`scripts/platformkit/analytics_showcase/check_all.py`](../scripts/platformkit/analytics_showcase/check_all.py) | A module whose `--check` mode fails (e.g. artifact was never rebuilt) | on demand, and by any lane touching `analytics_showcase/` |
| Analytics unit tests | [`.github/workflows/deploy-demo.yml`](../.github/workflows/deploy-demo.yml) (`Analytics unit tests` step, ~90 named `vitest` files) | Component/loader logic regressions across calibration, lab, compare, library, ask, findings | on every push to `webapp/**` on `master` |
| Verify published JSON | [`webapp/scripts/verify-public-json.mjs`](../webapp/scripts/verify-public-json.mjs) | Non-finite numbers (`NaN`/`Infinity`) or malformed JSON reaching the public data tree | `deploy-demo.yml`, pre- and post-export |
| Verify paper evidence | [`webapp/scripts/check-paper-evidence.mjs`](../webapp/scripts/check-paper-evidence.mjs) | A published paper citing an evidence artifact that doesn't exist, or using forbidden betting/wagering language | `deploy-demo.yml` |
| Client-import boundary | [`webapp/scripts/check-client-imports.mjs`](../webapp/scripts/check-client-imports.mjs) | A `"use client"` component reaching a module that imports `node:fs`/`node:path` (passes locally, fails only in static `next build`) | `deploy-demo.yml`, post-export |
| Analytics copy scan | [`webapp/scripts/check-analytics-copy.mjs`](../webapp/scripts/check-analytics-copy.mjs) | Prohibited betting-adjacent words (wager, bankroll, payout, and similar -- see the script's own token list) appearing anywhere in analytics source or published data | `deploy-demo.yml`, post-export (`--data` flag also scans `public/data/*`) |
| Export shape verification | [`webapp/scripts/verify-analytics-export.mjs`](../webapp/scripts/verify-analytics-export.mjs) | Required routes missing from the static export, or the export otherwise malformed | `deploy-demo.yml`, post-export |
| Typecheck (hard gate) | [`.github/workflows/webapp-qa.yml`](../.github/workflows/webapp-qa.yml) (`npm run typecheck`) | Type contract violations across the webapp | on every push/PR touching `webapp/**` |
| Honesty gate (hard gate) | [`webapp-qa.yml`](../.github/workflows/webapp-qa.yml) (`Honesty gate` step) | Any of the six retracted headline figures (see `docs/JOB_EVIDENCE_PACKET.md`'s do-not-claim list) appearing in shipped HTML outside pages that explicitly frame it as a retraction | `webapp-qa.yml`, post-export |
| Page-count tripwire (hard gate) | [`webapp-qa.yml`](../.github/workflows/webapp-qa.yml) (`Page-count tripwire` step) | A template refactor silently dropping thousands of exported routes (fails if fewer than 3200 HTML pages exist) | `webapp-qa.yml`, post-export |
| Lint / unit tests (report-only) | `webapp-qa.yml` | Reported as warnings, not blocking -- repo carries known pre-existing lint warnings and unrelated terminal-app test failures | `webapp-qa.yml` |

Two workflows run independently on the same push: `deploy-demo.yml` builds
and ships the site; `webapp-qa.yml` is the honesty/regression signal and does
not gate the deploy itself -- a human treats a red `webapp-qa` run as the
signal that a hard invariant broke.

---

## 5. Revisions and withdrawals

The site keeps two separate mechanisms for "this number changed" and "this
number was wrong":

**Regeneration receipts (in-game join-integrity incident).** In 2026-09,
[`mlb-ingame-integrity.json`](../webapp/public/data/audits/mlb-ingame-integrity.json)
recorded a fail-closed audit finding that some stored MLB/soccer in-game tick
files mixed more than one real game. The corpus was re-segmented
(`scripts/platformkit/segment_ingame_join.py`) and re-checked
(`scripts/platformkit/check_ingame_join_integrity.py`), and 13 exposed
artifacts were rebuilt from the segmented corpus. The resulting
[`mlb-ingame-regeneration.json`](../webapp/public/data/audits/mlb-ingame-regeneration.json)
and
[`mlb-ingame-timing-regeneration.json`](../webapp/public/data/audits/mlb-ingame-timing-regeneration.json)
are **revision 2** receipts: each carries `revision_published: 2`, a
`supersedes` block naming the withdrawn revision 1 and why, a
`segmentation.per_sport` before/after file and tick count, and a per-artifact
`n_before` / `n_after` / `headline_before` / `headline_after` table. This is
rendered live on
[Findings / Data integrity](https://neeljshah.github.io/court-vision/analytics/findings/ingame-join-integrity/).
The loader for all three receipts is
[`ingameJoinIntegrity.server.ts`](<../webapp/app/(analytics)/analytics/findings/ingame-join-integrity/ingameJoinIntegrity.server.ts>).

**Retractions (measurement failures, not corpus fixes).** Six headline
figures published earlier in the project's history were withdrawn because
their measurement method itself was wrong (leakage, wrong-scale grid, a
market-follow artifact mistaken for a model result). These stay visible,
struck through, on
[Findings / Retraction](https://neeljshah.github.io/court-vision/analytics/findings/retraction/) --
each entry names the withdrawn figure, the measurement failure, the
withdrawal date (or says "date not recorded" if the source doesn't state
one), the editorial date of the record, and a replacement only when one with
a dated calibration measure exists. The withdrawal source is
[`docs/JOB_EVIDENCE_PACKET.md`](../docs/JOB_EVIDENCE_PACKET.md).

**Claim history (the full ledger).** Every forward claim the project has
made -- verified, null, or retracted -- is scored in
[`fwd_claim_scoreboard.json`](../webapp/public/data/showcase/fwd_claim_scoreboard.json)
and rendered on
[Research loop](https://neeljshah.github.io/court-vision/analytics/the-loop/)
via [`claimHistory.server.ts`](../webapp/lib/analytics/claimHistory.server.ts).
An honest null result is recorded as a success, not omitted.

---

## 6. How to verify locally

Everything below runs from a bare clone; nothing reads `data/` or `vault/`
(both are local-only and gitignored, absent from a fresh clone).

| Command | What it checks | Needs `node_modules`? |
|---|---|---|
| `cd scripts/platformkit/analytics_showcase && python check_all.py` | Every showcase module's own `--check` self-test | No (Python only) |
| `python -m scripts.platformkit.analytics_showcase.build_site_manifest --check` | The manifest builder reproduces the committed manifest | No |
| `python -m scripts.platformkit.analytics_showcase.validate_webapp_artifacts` | Shape-validates every committed showcase artifact | No |
| `cd webapp && npm ci` | Installs deps -- required before any command below | -- |
| `npm run typecheck` | TypeScript contract (hard gate in CI) | Yes |
| `npm run build` (with `NEXT_PUBLIC_DATA_MODE=snapshot NEXT_PUBLIC_BASE_PATH=/court-vision`) | Full static export to `webapp/out/` | Yes |
| `node scripts/verify-public-json.mjs` | Malformed/non-finite JSON in `public/data` | Yes (Node built-ins only, but run from `webapp/`) |
| `node scripts/check-paper-evidence.mjs` | Every paper's evidence citations resolve | Yes |
| `node scripts/check-client-imports.mjs` | No client component reaches `node:fs`/`node:path` | Yes |
| `node scripts/check-analytics-copy.mjs --data` | No prohibited betting language in source or data | Yes |
| `node scripts/verify-analytics-export.mjs` | Required routes exist in `webapp/out/` after build | Yes |
| `npm run test` | Vitest unit suite (report-only in CI; known pre-existing failures unrelated to analytics) | Yes |

The honesty-gate grep and page-count tripwire in
[`webapp-qa.yml`](../.github/workflows/webapp-qa.yml) are shell one-liners,
reproducible directly against `webapp/out/**/*.html` after `npm run build`
without any additional tooling.

---

## 7. Known limits (honest)

- **Static snapshot, not live.** The site has no backend and no runtime
  fetch outside its own committed JSON. Every page carries an `as_of` /
  `measured_on` date; nothing updates until the next deploy.
- **Private corpora are not in the clone.** Generator modules read from
  `data/cache/ingame_grade_joined/` and similar paths under `data/`, which
  is local-only and gitignored -- a fresh clone has the committed JSON
  outputs but not the raw corpora that produced them.
- **One retracted figure is not grepped by the honesty gate.** One of the six
  do-not-claim values (see `docs/JOB_EVIDENCE_PACKET.md`) collides with
  legitimate descriptive tennis rate statistics, so the CI honesty check
  deliberately excludes it from its numeric grep; a human reviewer, not a
  regex, is the control for that one retracted value.
- **Lint and unit-test steps in `webapp-qa.yml` are report-only,** not hard
  gates -- the repo carries known pre-existing lint warnings and terminal-app
  test failures unrelated to the analytics site.
- **The in-game timing artifacts** listed under `timing_artifacts_regenerated`
  in the audit receipts were rebuilt in revision 2; any artifact still
  flagged `derived_artifacts_under_review` in
  [`mlb-ingame-integrity.json`](../webapp/public/data/audits/mlb-ingame-integrity.json)
  has stale inputs and is marked as such on the Data integrity finding page,
  not silently trusted.

---

**Navigate:** [README](../README.md) - [Evidence index](../EVIDENCE.md) - [Doc map](INDEX.md)
