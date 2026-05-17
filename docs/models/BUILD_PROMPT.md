# BUILD_PROMPT — Model Universe Build Loop

Paste the block below into Claude Code to build out the next batch of models from `docs/models/MODEL_UNIVERSE.md`.

It picks unbuilt models in priority order, implements + trains + evaluates them, registers artifacts, updates docs + vault, and commits to git — one atomic commit per model. Re-run it as many times as you want; it always resumes at the next 🔲 model.

**Nothing is built yet — this is a plan.** Run the prompt only when you want to start.

Mirror of the Obsidian note `vault/Models/BUILD_PROMPT.md` (vault is gitignored; this is the git-tracked copy).

---

## The Prompt

```
Build the next batch of models from docs/models/MODEL_UNIVERSE.md.

SCOPE
- Read docs/models/MODEL_UNIVERSE.md. Find every model with status 🔲 (planned)
  or ⚙️ (partial) whose `Data` requirement is already satisfiable
  (API / Shots / PBP / Sched / BBRef if scraper exists — skip CVn / Mkt / News /
  Live unless that data source is confirmed present in the repo).
- Process them in the Build Phasing order (P1 first). Build BATCH_SIZE = 5 models
  this run. If fewer than 5 are buildable, build all that are.

FOR EACH MODEL
1. Implement it in src/prediction/<model_name>.py (≤300 LOC, type hints,
   docstrings on public API only). Reuse feature_engineering.py features — do not
   re-derive features that already exist. Match the conventions of the nearest
   existing sibling module (e.g. game_models.py for game-level, player_props.py
   for props).
2. Wire it into the layer it belongs to:
   - L1 atomic    -> expose a predict() the possession chain / aggregator can call
   - L3 aggregation -> consume L2 simulator output
   - L4 meta      -> wrap an existing model's output
   - L5 betting   -> feed betting_edge.py / betting_portfolio.py
   Respect the dependency rule: a model may only consume layers below it.
3. Train on available data. Use walk-forward / out-of-sample CV (no leakage).
   Save the artifact to data/models/ and add an entry to
   data/models/model_registry.json (id from MODEL_UNIVERSE, e.g. M037, plus
   algorithm, target, features, metric, value, trained date).
4. Evaluate: report the appropriate metric (R² / Brier / AUC / MAE / logloss).
   If a model underperforms a trivial baseline, keep it but mark it ⚙️ with a
   note — do not delete; small edges compound.
5. Run `python -m pytest tests/ -q` and confirm nothing broke. Add a minimal
   smoke test for the new model if a tests/ sibling pattern exists.

DOC + VAULT UPDATES (after each model)
- docs/models/MODEL_UNIVERSE.md  -> flip that model's status 🔲/⚙️ -> ✅
  (or ⚙️ if data-starved); update the Count Summary table.
- docs/ML_MODELS.md + docs/models/model-registry.md -> add the model + metric.
- vault/Models/Model Universe.md -> mirror the same status flip (vault is
  gitignored — edit it but it won't be committed).
- vault/Models/Model Performance.md -> add the model + metric.
- If it's a CV fix or new signal, also touch the notes named in CLAUDE.md's
  "Vault Auto-Maintenance" section.
Keep edits minimal — change the value/status line, don't rewrite notes.

GIT
- One atomic commit per model: `feat(models): add <Mxxx> <model name> (<metric>=<value>)`
  Stage only the git-tracked files that model touched (src module, registry json,
  docs notes, test). Never `git add -A`. vault/ is gitignored so it won't commit.
- Do not push.

OUTPUT
- Terse. Per model: one line — `Mxxx <name>: <metric>=<value> ✅`.
- End with: models built this run, models remaining (🔲 count), and the next
  3 model IDs the next run will pick up.

RULES
- Autonomous — no permission prompts, no confirmation questions.
- Never run run.py or loop_processor.py. Video stays headless.
- _VRAM_FLUSH_INTERVAL stays 3000.
- If a model needs data the repo doesn't have, skip it, log why, move on.
```

---

## Usage Notes

- **First runs** burn through Phase P1 (~70 API-only models) — quarter totals,
  derivative props, combo props, milestone props. No new data needed.
- Once a scraper or feed lands (BBRef / market / news / CV games), the prompt
  automatically starts picking up that tier's models on the next run.
- To target a specific domain instead of phase order, append to the prompt:
  `Restrict to Domain K (betting market).`
- To build everything in one long session, append:
  `Set BATCH_SIZE = 999 and loop until no buildable 🔲 models remain.`
- Pair with `/loop` for unattended batches:
  `/loop 30m <paste the prompt>` — builds 5 models every 30 min.

## Related
- `docs/models/MODEL_UNIVERSE.md` — the 350-model master index this prompt consumes
- `docs/ML_MODELS.md` — current trained-artifact reference
