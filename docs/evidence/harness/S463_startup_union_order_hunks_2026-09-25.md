# S463 FIX 1f -- full `git diff master` hunks (sibling to the memo, per AMENDMENT 2(e)/3(c))

Row: S463 | worktree: nba-harness-h113 | date: 2026-09-25 | referenced from
`S463_startup_union_order_2026-09-25.md` section 5, which exceeds 300 lines with
these included verbatim. HEAD = `2b20cbd4fce5a7d9beb97b558e56d35ea5977662` = `master`
at this FIX 1f session's own fast-forward point (see the memo header). **EQUAL**.
Reproduce: `git diff master -- <path>`. Regenerated this round (FIX 1f); byte-
identical to the prior round's content since no product file changed this round
(verified). BEFORE the memo's own A9 identities (regenerated last, AMENDMENT 3c/4d).

## scripts/platformkit/ingame/schedule_pointer.py
```diff
diff --git a/scripts/platformkit/ingame/schedule_pointer.py b/scripts/platformkit/ingame/schedule_pointer.py
index 4561dc8de..b3ddef63a 100644
--- a/scripts/platformkit/ingame/schedule_pointer.py
+++ b/scripts/platformkit/ingame/schedule_pointer.py
@@ -19,6 +19,23 @@ class _Object(dict):
         self.duplicates = len(pairs) != len(self)
 
 
+def sources_delta(before: list, after: list, reselected_rows: int = 0) -> dict:
+    """S463 telemetry: split a post-union forward_schedule against its pre-call rows.
+
+    Public (AMENDMENT 1d): shared by both runners so identical inputs give identical
+    cli_rows/pointer_rows/carried_rows instead of each runner computing its own drift.
+    AMENDMENT 3(a): reselected_rows is supplied by the caller (union_open_rows' own
+    telemetry, via read_schedule_pointer) rather than inferred from a before/after
+    diff -- a before/after diff cannot see a re-selection whose adopted selected_at
+    equals the carried row's own (the prior row wins), so it always undercounts that
+    direction. Always present in the result, a strict int, 0 when none.
+    """
+    before_index = {(r["game_id"], r["ticker"]) for r in before}
+    carried = sum(1 for r in after if (r["game_id"], r["ticker"]) in before_index)
+    return {"pointer_rows": len(after) - carried, "carried_rows": carried,
+            "reselected_rows": reselected_rows}
+
+
 def instant(value: object) -> Decimal:
     """Use the landed venue grammar and retain nanoseconds at strict boundaries."""
     if not isinstance(value, (str, datetime)):
@@ -79,8 +96,15 @@ def _admit_capacity(carry: list, candidates: list, at, errors: Counter) -> list:
     return scheduler.schedule_rows(accepted, at, errors)
 
 
-def union_open_rows(rows: list, prior: list, now: object, errors: Counter) -> list:
-    """Union a new selection with prior rows still inside their focus window."""
+def union_open_rows(rows: list, prior: list, now: object, errors: Counter,
+                     telemetry: dict | None = None) -> list:
+    """Union a new selection with prior rows still inside their focus window.
+
+    AMENDMENT 3(a): optional out-param -- when given, telemetry["reselected_rows"]
+    is set to the count of full-identity matches whose incoming selected_at
+    differed from the kept row's, whichever row was kept. Additive-only: the
+    return type stays a plain list (frozen by a pre-existing direct caller).
+    """
     at = instant(now)
     # AMENDMENT 1(a): no lower bound -- a not-yet-open row is carried no matter how far
     # ahead its start is; only a row whose window has exclusively closed is dropped.
@@ -94,15 +118,79 @@ def union_open_rows(rows: list, prior: list, now: object, errors: Counter) -> li
     # against carried game ids, a ticker only against carried tickers.
     carried_game_ids = {r["game_id"] for r in carry}
     carried_tickers = {r["ticker"] for r in carry}
+    reselected = {}
     for row in carry:
         overlaps = [r for r in incoming if r["game_id"] == row["game_id"] or r["ticker"] == row["ticker"]]
-        if overlaps and (len(overlaps) != 1 or overlaps[0] != row):
+        if not overlaps:
+            continue
+        other = overlaps[0]
+        # AMENDMENT 2(d): a PARTIAL identity match (only game_id or only ticker agrees) is
+        # a genuine conflict -- a different ticker for the same game_id, or a different
+        # game_id for the same ticker -- and still refuses. A FULL identity match (both
+        # agree) that differs ONLY in selected_at is the same game re-selected, not a
+        # conflict: keep the row, adopt the later selected_at.
+        same_identity = other["game_id"] == row["game_id"] and other["ticker"] == row["ticker"]
+        if len(overlaps) != 1 or not same_identity:
             raise ValueError("conflicting_schedule_rows")
+        if other == row:
+            continue
+        rest_equal = ({k: v for k, v in row.items() if k != "selected_at"}
+                     == {k: v for k, v in other.items() if k != "selected_at"})
+        if not rest_equal:
+            raise ValueError("conflicting_schedule_rows")
+        later = row if instant(row["selected_at"]) >= instant(other["selected_at"]) else other
+        reselected[row["game_id"], row["ticker"]] = dict(row, selected_at=later["selected_at"])
+    if telemetry is not None:
+        telemetry["reselected_rows"] = len(reselected)
+    if reselected:
+        carry = [reselected.get((r["game_id"], r["ticker"]), r) for r in carry]
     candidates = [r for r in incoming
                   if r["game_id"] not in carried_game_ids and r["ticker"] not in carried_tickers]
     return _admit_capacity(carry, candidates, at, errors)
 
 
+def seed_cli_schedule(state: dict, now: object, errors: Counter) -> None:
+    """S463: seed forward_schedule from --schedule before the first pointer read.
+
+    Bootstrap-only and additive: fires at most once per state, and is a
+    silent no-op unless both the pointer flag (schedule_pointer_path) and a
+    CLI schedule path (schedule_path) are already present in state. The
+    one-shot flag means a later legitimate empty forward_schedule is never
+    clobbered by a stale re-seed.
+    """
+    if not state.get("schedule_pointer_path") or "schedule_path" not in state:
+        return
+    if state.get("cli_schedule_seed_done"):
+        return
+    state["cli_schedule_seed_done"] = True
+    if state.get("forward_schedule") or state.get("schedule_pointer_ever_resolved"):
+        return
+    # AMENDMENT 1(d): the key is created here, the moment the seed actually attempts a
+    # read, not only on success -- so a failed/invalid CLI file still counts as "ran".
+    # AMENDMENT 4(a): reselected_rows is present from this first tick too, a strict int,
+    # so a malformed pointer or a failed refresh before any success never leaves it absent.
+    state["schedule_sources"] = {"cli_rows": 0, "pointer_rows": 0, "carried_rows": 0,
+                                  "reselected_rows": 0}
+    try:
+        raw = Path(state["schedule_path"]).read_bytes()
+    except (OSError, TypeError):
+        errors["cli_schedule_unavailable"] += 1
+        return
+    try:
+        rows = _decode(raw)
+        if isinstance(rows, list) and any(isinstance(r, dict) and r.duplicates for r in rows):
+            raise ValueError("duplicate_schedule_keys")
+        parsed = scheduler.schedule_rows(rows, instant(now), errors)
+    except (ValueError, TypeError, ArithmeticError, KeyError):
+        errors["cli_schedule_invalid"] += 1
+        return
+    if not parsed:
+        errors["cli_schedule_unavailable"] += 1
+        return
+    state["forward_schedule"] = parsed
+    state["schedule_sources"]["cli_rows"] = len(parsed)
+
+
 def read_schedule_pointer(state: dict, now: object, errors: Counter) -> bytes | None:
     """Commit a fully checked target, or count a named refusal and retain state."""
     total = scheduler.count(state.get("schedule_pointer_refusals_total", 0))
@@ -151,7 +239,8 @@ def read_schedule_pointer(state: dict, now: object, errors: Counter) -> bytes |
         except ValueError as exc:
             reason = "pointer_day_mismatch" if str(exc) == "pointer_day_mismatch" else reason
             raise
-        rows = union_open_rows(parsed, state.get("forward_schedule", []), now, errors)
+        telemetry: dict = {}
+        rows = union_open_rows(parsed, state.get("forward_schedule", []), now, errors, telemetry)
         resolved = attempted_at
         heartbeat = dict(schedule_pointer_day=pointer["day"], schedule_pointer_file=relative,
                          schedule_pointer_sha256=digest, schedule_pointer_resolved_at=resolved,
@@ -171,26 +260,38 @@ def read_schedule_pointer(state: dict, now: object, errors: Counter) -> bytes |
         return None
     state.update(schedule_path=target, forward_schedule=rows,
                  schedule_pointer_heartbeat=heartbeat, schedule_pointer_status={"ok": True},
-                 schedule_pointer_refusals_total=total, schedule_pointer_ever_resolved=True)
+                 schedule_pointer_refusals_total=total, schedule_pointer_ever_resolved=True,
+                 # AMENDMENT 3(a): transient, read once by the caller's sources_delta call
+                 # and never itself persisted (the heartbeat/archive writers whitelist fields).
+                 schedule_pointer_reselected_rows=telemetry.get("reselected_rows", 0))
     state["schedule_pointer_health"] = {**state.get("schedule_pointer_health", {}),
                                         "schedule_pointer_refusals_total": total,
                                         "pointer_read_at": attempted_at, "pointer_ok_at": attempted_at}
     return raw
 
 
-def refresh_polymarket_pointer(state: dict, now: object, clock_value: float, errors: Counter) -> None:
-    """Refresh the prospective selection on the same sixty-second cadence."""
+def refresh_polymarket_pointer(state: dict, now: object, clock_value: float, errors: Counter) -> bool:
+    """Refresh the prospective selection on the same sixty-second cadence.
+
+    Returns whether a pointer resolution actually succeeded this call (AMENDMENT 1c):
+    the caller uses this, not a before/after content diff, to gate telemetry.
+    """
     if clock_value - state.get("schedule_read_at", -float("inf")) < 60:
-        return
+        return False
     state["schedule_read_at"] = clock_value
     if read_schedule_pointer(state, now, errors) is None:
-        return
+        return False
     prospective = set()
     for row in state["forward_schedule"]:
         at = instant(row["scheduled_start"])
         stamp = datetime.fromtimestamp(int(at), timezone.utc).replace(microsecond=int((at % 1) * 1000000))
         prospective.add((row["sport"], iso(stamp)))
+    # AMENDMENT 1(d) / NEW GAP: a loose {sport, scheduled_start}-only --schedule carries no
+    # game_id/ticker, so it can never enter forward_schedule via seed_cli_schedule; without
+    # this union its load_prospective identities would be dropped on the first resolution.
+    prospective |= state.get("prospective_cli", frozenset())
     changed = prospective != state.get("prospective")
     state["prospective"] = frozenset(prospective)
     if changed and state.get("discovery") is not None:
         state["discovery"]["ts"] = clock_value - 300
+    return True
```

## scripts/platformkit/ingame/capture_schedule_loader.py
```diff
diff --git a/scripts/platformkit/ingame/capture_schedule_loader.py b/scripts/platformkit/ingame/capture_schedule_loader.py
index bed5b9f50..041b1df61 100644
--- a/scripts/platformkit/ingame/capture_schedule_loader.py
+++ b/scripts/platformkit/ingame/capture_schedule_loader.py
@@ -22,6 +22,11 @@ def _forward_config(state: dict, now, clock_value, writer, metrics) -> None:
     if not has_source or clock_value - state.get("schedule_read_at", -float("inf")) < 60: return
     state["schedule_read_at"] = clock_value
     state.setdefault("forward_schedule", [])
+    # S463: seed the CLI --schedule rows into forward_schedule BEFORE the pointer is ever
+    # read, so the union below (inside read_schedule_pointer) sees them as prior state.
+    # Gated on pointer enablement: never called when the pointer flag is off.
+    if state.get("schedule_pointer_path"):
+        schedule_pointer.seed_cli_schedule(state, now, metrics.errors)
     # Opt-in pointer hand-off (S438 AMENDMENT 1b/c): on success the helper already sets
     # schedule_path and the unioned forward_schedule, so the plain re-read below must not
     # clobber it; once a pointer has EVER resolved, a later refusal must not fall back to
@@ -30,7 +35,16 @@ def _forward_config(state: dict, now, clock_value, writer, metrics) -> None:
     # is a bootstrap: schedule_path is seeded here, on the first successful pointer read.
     pointer_hit = False
     if state.get("schedule_pointer_path"):
+        before = list(state["forward_schedule"])
         pointer_hit = schedule_pointer.read_schedule_pointer(state, now, metrics.errors) is not None
+        # AMENDMENT 1(b)/(c): never CREATE the key (pointer-alone stays byte-identical);
+        # once the seed created it, every successful resolution REPLACES it (AMENDMENT
+        # 3a), changed or not -- dict.update let a stale reselected_rows from an earlier
+        # resolution survive every later one.
+        if pointer_hit and "schedule_sources" in state:
+            reselected = state.pop("schedule_pointer_reselected_rows", 0)
+            state["schedule_sources"] = {"cli_rows": state["schedule_sources"]["cli_rows"],
+                                          **schedule_pointer.sources_delta(before, state["forward_schedule"], reselected)}
         pointer_hit = pointer_hit or state.get("schedule_pointer_ever_resolved", False)
     if not pointer_hit and "schedule_path" not in state:
         return  # bootstrap pending: pointer never resolved yet and no --schedule fallback
```

## scripts/platformkit/ingame/polymarket_live_capture.py
```diff
diff --git a/scripts/platformkit/ingame/polymarket_live_capture.py b/scripts/platformkit/ingame/polymarket_live_capture.py
index 01a98b1d0..cca273d33 100644
--- a/scripts/platformkit/ingame/polymarket_live_capture.py
+++ b/scripts/platformkit/ingame/polymarket_live_capture.py
@@ -143,7 +143,16 @@ def capture_once(*, client, sports: list, now, state: dict, output_root: Path,
                  writer, clock: Callable = time.monotonic, state_root=None) -> dict:
     """One tick: scheduled linked games first, both outcomes of a market together."""
     if state.get("schedule_pointer_path"):  # S438 opt-in hand-off; flag off is byte-identical.
-        pointer_hub.refresh_polymarket_pointer(state, now, clock(), client.metrics.errors)
+        before = list(state.get("forward_schedule", []))
+        resolved = pointer_hub.refresh_polymarket_pointer(state, now, clock(), client.metrics.errors)
+        # AMENDMENT 1(b)/(c): never CREATE the key (pointer-alone stays byte-identical);
+        # once the seed created it, every successful resolution REPLACES it (AMENDMENT
+        # 3a), changed or not -- dict.update let a stale reselected_rows from an earlier
+        # resolution survive every later one.
+        if resolved and "schedule_sources" in state:
+            reselected = state.pop("schedule_pointer_reselected_rows", 0)
+            state["schedule_sources"] = {"cli_rows": state["schedule_sources"]["cli_rows"],
+                                          **pointer_hub.sources_delta(before, state.get("forward_schedule", []), reselected)}
     tick_start = iso(now)
     counts = state.setdefault("counters", Counter())
     before = dict(writer.counts)
@@ -212,6 +221,8 @@ def _publish(client, writer, state: dict, sports: list, units: list, before: dic
                  "error_counters": dict(client.metrics.errors),
                  "sources": client.metrics.snapshot(client.aimd.rate, client.aimd.clock())}
         value.update({**state.get("schedule_pointer_heartbeat", {}), **state.get("schedule_pointer_health", {})})
+        if state.get("schedule_sources"):
+            value["schedule_sources"] = state["schedule_sources"]
         state["hb"][sport] = value
         path = lrow.heartbeat_path(VENUE, sport, output_root)
         writer.atomic(path, value, "heartbeat")
@@ -231,6 +242,15 @@ def run_capture(*, sports=None, output_root=None, schedule=None, schedule_pointe
     state = {"prospective": load_prospective(schedule, client.metrics.errors)}
     if schedule_pointer is not None:
         state["schedule_pointer_path"] = Path(schedule_pointer)
+        # prospective_cli (AMENDMENT 1d/NEW GAP): the loose-shape CLI identities are never
+        # in forward_schedule, so refresh_polymarket_pointer must union them back in on
+        # every pointer resolution or they are silently dropped from prospective. Gated on
+        # the pointer flag: pointer-alone/flag-off stays byte-identical (no extra key).
+        state["prospective_cli"] = state["prospective"]
+    if schedule is not None:  # S463: seed forward_schedule's CLI path before the first tick.
+        state["schedule_path"] = Path(schedule)
+    if state.get("schedule_pointer_path"):  # gated on pointer enablement: never called when off.
+        pointer_hub.seed_cli_schedule(state, client.utc_clock(), client.metrics.errors)
     result, ticks = {}, 0
     with PolymarketWriter(output_root, client.metrics) as writer:
         while not stop_file.exists() and not (stop is not None and stop()):
```

## scripts/platformkit/ingame/local_capture_runner.py
```diff
diff --git a/scripts/platformkit/ingame/local_capture_runner.py b/scripts/platformkit/ingame/local_capture_runner.py
index 81263f215..ac96f85d5 100644
--- a/scripts/platformkit/ingame/local_capture_runner.py
+++ b/scripts/platformkit/ingame/local_capture_runner.py
@@ -229,7 +229,7 @@ def _scheduled_tick(client, writer, sports, now, state, clock):
         summary = heartbeat(client, writer, state, sports, list(plan.markets), before)
         for sport in sports:
             state["hb"][sport].update(scheduler.heartbeat_fields(plan, state, sport))
-            state["hb"][sport].update({**state.get("schedule_pointer_heartbeat", {}), **state.get("schedule_pointer_health", {})})
+            state["hb"][sport].update({**state.get("schedule_pointer_heartbeat", {}), **state.get("schedule_pointer_health", {}), **({"schedule_sources": state["schedule_sources"]} if state.get("schedule_sources") else {})})
             writer.atomic(lrow.heartbeat_path("kalshi", sport, writer.root), state["hb"][sport], "heartbeat")
     return {"by_sport": summary, "n_due_books": len(plan.focus_tickers), "budget": plan.budget}
 def capture_once(*, client=None, sports=None, now=None, state=None, clock: Callable = time.monotonic, output_root=None, _writer=None, scheduler_enabled=False, schedule=None, schedule_pointer=None) -> dict:
```
