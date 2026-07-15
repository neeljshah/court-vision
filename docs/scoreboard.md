# CourtVision Weekly Scoreboard

Use this file as the single weekly execution snapshot. Update once per week (same weekday/time).

## Current Week

- Week of: `2026-07-15`
- Program status: `yellow` (active build, no release-blocking incident; core KPI instrumentation below still unwired)
- Primary blocker: frontend rooms (`webapp/`) pending user go-ahead; replay model-tick join v2 (venue-slug <-> ESPN id map) open per `.planning/NOW.md`
- Next review date: `2026-07-22`

## Core KPIs

| KPI | Target | Current | Trend | Status | Notes |
|---|---|---|---|---|---|
| CV drift SLA pass rate | >=95% | TBD | TBD | TBD | |
| ID switch benchmark pass rate | >=95% | TBD | TBD | TBD | |
| Leakage violations per release | 0 | TBD | TBD | TBD | |
| Official reports using proxy/synthetic lines | 0 | TBD | TBD | TBD | |
| 90% PI coverage (major markets) | 88-92% | TBD | TBD | TBD | |
| CLV positive rate (30d) | >=55% | TBD | TBD | TBD | |
| Contract compatibility failures | 0 | TBD | TBD | TBD | |
| Unrecoverable pipeline runs | 0 | TBD | TBD | TBD | |

## 14-Day Sprint Progress

| Sprint Outcome | Owner | ETA | Status | Evidence |
|---|---|---|---|---|
| Leakage gate wiring | Research Platform | Day 5 | Not started | `data/model_reports/leakage/leakage_audit.json` |
| CV drift benchmark v1 | CV Lead | Day 7 | Not started | `data/model_reports/cv_drift/<game_id>.json` |
| Quality-filtered train manifest | Data Platform | Day 9 | Not started | `data/model_reports/data_quality/train_manifest.json` |
| Execution quality baseline | Trading Infra | Day 11 | Not started | `data/model_reports/execution/clv_30d.json` |
| Release-gate dry run | MLOps | Day 14 | Not started | release checklist link |

## Risks and Decisions

- Top risk this week:
- Decision needed:
- Escalation owner:

## Change Log

- `YYYY-MM-DD`: initialized scoreboard template
- `2026-07-15`: filled in Current Week header from `.planning/NOW.md`; Core KPIs and
  14-Day Sprint Progress below are still unpopulated -- no `cv_drift`/`id_switch`
  benchmark artifacts or the named sprint-evidence files (`data/model_reports/leakage/`,
  `.../cv_drift/`, `.../data_quality/`, `.../execution/`) exist on disk yet, so those
  rows remain honest TBD / Not started rather than invented numbers


---
<!-- nav-footer -->
**Navigate:** [Up: full doc map](INDEX.md) - [Home](../README.md) - [Glossary](GLOSSARY.md)
