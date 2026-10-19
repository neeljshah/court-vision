# PROPOSED S558 -- connect the execution receipts to the unattended paper desk (FOR paper-desk-improve)

Author: EXEC-LIVE lead (Opus), 2026-09-30 ~00:3xZ. Plan: FIVE_HOUR_PLAN_2026-09-30_B.md package B4.
STATUS: PROPOSED ONLY. The target files belong to S500/S501/S510/S511 (paper-desk-improve). Nothing below is applied;
no paper_desk_* or paper_night* file was edited. Tracked twin of the research-side copy
docs/research/organization-sprint/PROPOSED-S558_exec_receipts_unattended_2026-09-30.md.
PAPER ONLY. Execution-quality and calibration wording only.

## Problem (measured on master 13d304aa7)
- Nothing runs the S516 fill receipt (live_shadow_fills), the S551 scored replay (exec_policy_report --mode scored)
  or the S550 rolling receipt (exec_quality_audit_io) on any schedule. paper_night._steps
  (scripts/platformkit/execution/paper_night.py:61-110) builds only qualification, fill_realism, week, scoreboard,
  history and e; KNOWN_STEP_NAMES (paper_night_steps.py:22) names only those six.
- Nothing watches the live shadow recorder: the issue scanner registers capture, obligations and tick_silent only
  (paper_desk_issues.py:57). A dead or RAM-starved recorder during a served game is invisible.
- S551's one confirmatory look (PREREG_S551.json) is reached only if every served game from 2026-09-30 is replayed;
  a missed night cannot be re-run with the same receipt instant later without an operator.

## Proposed change (four parts; each is additive and budget-gated like the existing optional steps)

### 1. paper_night_budget.json (budget_version 3 -> 4)
ceiling_bytes gains (per-step ceilings; the runner's free-RAM gate = ceiling + free_ram_margin_bytes still applies):
- "live_shadow_fills": 157286400    (150 MiB; S516 real-row probe peak 27.1 MiB; full-night RSS NOT measured yet)
- "exec_cancel_policy": 536870912   (512 MiB; S551 measured replay peak 336 MiB -> runs only above the night RAM gate)
- "exec_quality_week": 157286400    (150 MiB; S550 measured 52.5 MB over 09-22..26)
producer_args gains:
- "shadow_root": "data/cache/live_shadow"
- "books_root_local": "data/cache/ingame_books_local"
- "live_shadow_out": "docs/evidence/forward/live_shadow/{date}.json"
- "exec_policy_prereg": "docs/evidence/forward/exec_policy/PREREG_S551.json"
- "exec_quality_out_dir": "docs/evidence/forward/exec_quality"

### 2. paper_night_steps.py:22
KNOWN_STEP_NAMES = (..., "e", "live_shadow_fills", "exec_cancel_policy", "exec_quality_week")

### 3. paper_night.py _steps, appended after the "e" block (paper_night.py:107-109)
```python
    if "live_shadow_fills" in budget["ceiling_bytes"]:
        ls = make("live_shadow_fills", "execution.live_shadow_fills",
                  dict(date=day, sport="mlb", shadow_root=p["shadow_root"], books_root=p["books_root_local"]),
                  p["live_shadow_out"])
        # PROVISIONAL is expected (the live tape lags ~2 h, S516); the receipt labels itself.
        ls["skip"] = plan["reason"] or (None if (root / p["shadow_root"] / "mlb" / f"{day}.jsonl").exists()
                                        else "no_live_shadow_rows")
        result.append(ls)
    if "exec_cancel_policy" in budget["ceiling_bytes"]:
        argv = [sys.executable, "-m", "scripts.platformkit.execution.exec_policy_report", "--date", day,
                "--mode", "scored", "--prereg", p["exec_policy_prereg"]]
        out = f"docs/evidence/forward/exec_policy/{day}.json"   # verify the child's receipt name at build
        result.append(dict(name="exec_cancel_policy", argv=argv, out=out, skip=plan["reason"]))
    if "exec_quality_week" in budget["ceiling_bytes"] and date.fromisoformat(day).weekday() == 6:
        first = (date.fromisoformat(day) - timedelta(days=6)).isoformat()
        days = [(date.fromisoformat(first) + timedelta(days=i)).isoformat() for i in range(7)]
        argv = [sys.executable, "-m", "scripts.platformkit.execution.exec_quality_audit_io", *days,
                "--out-dir", p["exec_quality_out_dir"]]
        out = f'{p["exec_quality_out_dir"]}/{first}_{day}.json'   # S550 receipt naming <first>_<last>.json
        result.append(dict(name="exec_quality_week", argv=argv, out=out, skip=plan["reason"]))
```
Notes for the builder:
- make() appends `--out`; exec_policy_report treats --out as a DIRECTORY and exec_quality_audit_io takes positional
  days plus --out-dir, so those two steps build argv by hand (above). Re-read both CLIs at build time.
- The S551 scored run refuses games dated on or before the seal UTC date (2026-09-29) by itself; do not filter here.
- GUARD (S557 AMENDMENT 1 (2)): the landed scored path pools EVERY sport on a scored date permanently (no sport
  filter; exec_policy_report.py:100-127, :186-206). Until the S557 wiring lands, the exec_cancel_policy step must
  SKIP (reason non_mlb_served) any night whose <day>_maker_forward.json holds a non-MLB entry (first: TNF 2026-10-02).
- A night where the S551 child exits 3 (prereg refusal) must be journaled as a refusal, not child_failed (S520 pattern).
- None of these steps may touch the scoreboard identity files or arm E; they are report-only children.

### 4. Issue kind live_shadow_silent (new module scripts/platformkit/ops/paper_desk_issue_live_shadow.py, registered
next to tick_silent at paper_desk_issues.py:57), modelled on paper_desk_issue_tick.py:
- Read data/cache/live_shadow/_heartbeat.json (one small file; never the rows).
- If a served MLB game in docs/evidence/forward/schedules/<D>_maker_forward.json has scheduled_start within
  [now - 4 h, now + 10 min] (a served game plausibly live) and the heartbeat is missing or its `ts` is older than
  90 s (6 x the 15 s cadence): FAIL, P1 inside 16:00Z-06:00Z, else P2.
- If the heartbeat's `low_ram_skip` is > 0 on the latest record: FAIL live_shadow_low_ram, P2 (the recorder is up
  but every tick is skipped below 1,500 MB free).
- No served game plausibly live: PASS (the recorder is expected to be idle or stopped).
- Never P0; never acts; evidence strings carry the heartbeat path, ts and age in whole seconds.

## Cases the builder should pin (construct)
1. budget without the new names -> _steps output unchanged byte for byte (regression).
2. live_shadow_fills skip = no_live_shadow_rows when the day file is absent; runs when present.
3. exec_quality_week appears only when the night's day is a Sunday; days = the 7 days ending on it.
4. exec_cancel_policy argv carries --mode scored and the sealed prereg path; ceiling 512 MiB forces the RAM gate.
5. live_shadow_silent: heartbeat age 89 s PASS, 91 s FAIL (P1 at 23:00Z, P2 at 12:00Z); missing heartbeat with a
   served game in window FAIL; no served game PASS; low_ram_skip > 0 FAIL live_shadow_low_ram.

## Risk
- RAM: the three steps run serially after the existing children, each under its own ceiling; the S551 child is
  the only large one (336 MiB measured) and the night runner's free-RAM gate defers it rather than risking the night.
- Night duration: S551 replay wall time on one night of MLB is minutes (S551 memo); verify before enabling.
