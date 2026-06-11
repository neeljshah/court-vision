"""The loop ORCHESTRATOR -- drives both arms forever over one shared substrate.

The never-stop LOOP DRIVER invoked repeatedly by the bot loop. Per iteration:
  ARM A: error_miner.mine() -> FDR-aware, ledger-deduped Hypothesis queue -> for
         each, discover/instantiate the concrete ``signals/<name>.py`` Signal ->
         gate.evaluate (ablation vs FULL, joint sim) -> SHIP: wiring.ship_signal
         (GPU retrain + regime gate + write learned values back as an atlas field);
         VARIANCE_ONLY: wiring.wire_variance_signal; DEFER: requeue (not ledgered);
         REJECT: ledger only.
  ARM B: each discovered ``intel/*.py`` AtlasSection -> build(as_of) ->
         intel_validator.validate -> profile_factory_bridge.register_section
         (extend the factory) -> memory_writer.write_finding -> ledger.record_atlas.

Multiple-comparisons BUDGET: Benjamini-Hochberg FDR is recomputed across the whole
ledger each iteration; the one-time held-out set is touched EXACTLY ONCE across the
loop lifetime (tracked in the checkpoint). Checkpoint+resume keeps the iteration
counter, held-out-spent flag, and per-name DEFER back-off so a restart never
re-spends the held-out budget. Never touches api/, the live server/tunnel,
data/live/, data/lines/; sets ``NBA_OFFLINE=1``; threads GPU device to gate/wiring.
"""
from __future__ import annotations

import datetime as _dt
import importlib
import inspect
import json
import os
import pkgutil
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Type

from .atlas import AtlasSection
from .signal import Hypothesis, Signal, Verdict
from .store import PointInTimeStore, entity_key, get_store

# Defer importing the heavy/skeleton modules to call time so the orchestrator
# imports cleanly even while sibling modules are still stubs.
from . import gate as _gate  # noqa: E402
from . import error_miner as _error_miner  # noqa: E402
from . import intel_validator as _intel_validator  # noqa: E402
from . import ledger as _ledger  # noqa: E402
from . import wiring as _wiring  # noqa: E402
from . import memory_writer as _memory_writer  # noqa: E402
from . import profile_factory_bridge as _bridge  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
_CHECKPOINT_PATH = ROOT / ".planning" / "loop" / "orchestrator_checkpoint.json"

# Stop requeuing a hypothesis whose signal keeps DEFERing after this many attempts.
_MAX_DEFER_ATTEMPTS = 3

# In dry-run / smoke mode, build each atlas section over at most this many
# entities so the end-to-end path is PROVEN quickly (full runs use the whole
# profile-index universe).
_DRY_RUN_ENTITY_CAP = 8
# In dry-run mode, build at most this many player + team sections (a
# representative slice) so a smoke run finishes fast.
_DRY_RUN_SECTION_CAP = 2


@dataclass
class IterationResult:
    """Summary of one loop iteration (printed by the CLI; appended to the ledger).

    Attributes:
        arm:          "signals" | "intel" | "both".
        hypotheses:   hypotheses considered this iteration.
        verdicts:     {name: Verdict} for every tested signal.
        atlas_built:  atlas section keys built + persisted.
        shipped:      names of signals that SHIPped (and were wired + written back).
        notes:        memory notes written.
        errors:       non-fatal errors captured (never raises out of the loop).
    """

    arm: str = "both"
    hypotheses: List[Hypothesis] = field(default_factory=list)
    verdicts: Dict[str, Verdict] = field(default_factory=dict)
    atlas_built: List[str] = field(default_factory=list)
    shipped: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


class Orchestrator:
    """Owns the shared store and sequences the two arms.

    Args:
        store:   the point-in-time substrate (defaults to ``get_store()``).
        device:  "auto" (cuda) | "cuda" | "cpu".
        dry_run: build + gate + validate but DO NOT persist/wire (smoke mode).
    """

    def __init__(self, store: Optional[PointInTimeStore] = None,
                 device: str = "auto", dry_run: bool = False) -> None:
        os.environ.setdefault("NBA_OFFLINE", "1")
        self.store = store or get_store()
        self.device = device
        self.dry_run = dry_run
        self._ckpt = self._load_checkpoint()

    # ---- public entry points -------------------------------------------------
    def run(self, *, arm: str = "both", max_iters: Optional[int] = None,
            forever: bool = False) -> List[IterationResult]:
        """Run the loop: ``max_iters`` iterations, or ``forever`` until stopped.

        Entry point called by ``scripts/loop/run_loop.py``. Respects ``dry_run``.
        Never raises; per-iteration failures are captured into the result.
        """
        import time as _time  # noqa: PLC0415
        results: List[IterationResult] = []
        i = 0
        backoff = 60.0
        _BACKOFF_MAX = 1800.0  # idle cap: 30 min when no productive work

        def _nondefer_count() -> int:
            """Count resolved (non-DEFER) ledger entries -- the productivity signal."""
            try:
                return sum(1 for e in _ledger.load_all()
                           if str(e.get("verdict")) not in ("DEFER", "Verdict.DEFER"))
            except Exception:
                return -1

        while True:
            if not forever and max_iters is not None and i >= max_iters:
                break
            before = _nondefer_count() if forever else -1
            res = self.run_iteration(arm=arm)
            results.append(res)
            i += 1
            if not forever and max_iters is None:
                break  # default: a single iteration ("--once")
            if forever:
                # Idle backoff: when a full cycle resolves nothing NEW (only the
                # same data-gapped DEFERs re-run), sleep progressively up to 30 min
                # instead of spinning every minute -- avoids ledger churn + wasted
                # compute. Any productive cycle (new SHIP/REJECT/VARIANCE_ONLY, e.g.
                # when fresh data lands) resets the cadence so the loop stays
                # responsive to genuinely new work.
                after = _nondefer_count()
                productive = before < 0 or after < 0 or after > before
                if productive:
                    backoff = 60.0
                    _time.sleep(backoff)
                else:
                    _time.sleep(backoff)
                    backoff = min(backoff * 2.0, _BACKOFF_MAX)
        return results

    def run_iteration(self, arm: str = "both") -> IterationResult:
        """Run ONE iteration of the requested arm(s); return the summary. Never raises."""
        result = IterationResult(arm=arm)
        try:
            if arm in ("signals", "both"):
                hyps = self._mine_hypotheses(result)
                result.hypotheses = hyps
                self._run_signals_arm(hyps, result)
                self._run_discovery_arm(result)   # ADDITIVE + flag-gated (CV_LOOP_DISCOVERY)
            if arm in ("intel", "both"):
                self._run_intel_arm(result)
            # Multiple-comparisons guard: recompute BH-FDR across the whole ledger.
            self._safe(lambda: _ledger.apply_fdr(), result, "apply_fdr")
        except Exception as exc:  # pragma: no cover - belt & suspenders
            result.errors.append(f"iteration: {exc!r}")
        finally:
            self._ckpt["iterations"] = int(self._ckpt.get("iterations", 0)) + 1
            self._ckpt["last_run"] = _dt.datetime.utcnow().isoformat() + "Z"
            self._save_checkpoint()
        return result

    # ---- ARM A: signals ------------------------------------------------------
    def _mine_hypotheses(self, result: IterationResult) -> List[Hypothesis]:
        """Refresh the hypothesis queue from the error-miner + intel-scanner +
        the SEED hypotheses self-declared by every built ``signals/*.py`` module,
        dropping anything already tested (non-DEFER) or DEFER-exhausted.

        The error-miner emits residual/atlas-derived hypotheses (empty when no
        logged residuals exist offline); the seed pass guarantees the 20 concrete
        signal modules are themselves enqueued (each carries its own
        ``hypothesis()`` whose ``name`` matches the signal-registry key), so the
        loop always has work even before residual logs accumulate.
        """
        try:
            hyps = list(_error_miner.mine(store=self.store, top_k=20) or [])
        except Exception as exc:
            result.errors.append(f"error_miner.mine: {exc!r}")
            hyps = []
        hyps.extend(self._seed_hypotheses(result))
        queue: List[Hypothesis] = []
        seen: set = set()
        for h in hyps:
            if h.name in seen:
                continue
            seen.add(h.name)
            try:
                if _ledger.already_tested(h.name, kind="signal"):
                    continue
            except Exception:
                pass  # ledger unavailable -> still attempt the hypothesis
            attempts = self._ckpt.get("defer_attempts", {}).get(h.name, 0)
            if attempts >= _MAX_DEFER_ATTEMPTS:
                continue
            queue.append(h)
        return queue

    def _seed_hypotheses(self, result: IterationResult) -> List[Hypothesis]:
        """Collect the self-declared ``hypothesis()`` from every built signal.

        Each ``signals/<name>.py`` module is a concrete :class:`Signal` whose
        ``hypothesis()`` returns a :class:`Hypothesis` with ``name == signal.name``.
        Enqueuing these guarantees the gate evaluates the built signals even with
        no residual logs (offline). Failures to instantiate/describe a signal are
        captured non-fatally so one broken module never stalls the queue.
        """
        out: List[Hypothesis] = []
        for name, cls in self._discover_signals(result).items():
            try:
                hyp = cls(store=self.store).hypothesis()
            except Exception as exc:
                result.errors.append(f"seed hypothesis {name}: {exc!r}")
                continue
            if isinstance(hyp, Hypothesis) and hyp.name:
                out.append(hyp)
        return out

    def _run_signals_arm(self, hypotheses: List[Hypothesis],
                         result: IterationResult) -> None:
        """ARM-A inner loop: gate each signal (ablation vs FULL + joint sim), wire SHIPs."""
        registry = self._discover_signals(result)
        for h in hypotheses:
            cls = registry.get(h.name)
            if cls is None:
                # No concrete signal module yet -> leave queued (do not waste a verdict).
                result.verdicts[h.name] = Verdict.DEFER
                continue
            try:
                signal = cls(store=self.store)
            except Exception as exc:
                result.errors.append(f"instantiate {h.name}: {exc!r}")
                result.verdicts[h.name] = Verdict.DEFER
                continue
            self._gate_one_signal(signal, h, result)

    def _gate_one_signal(self, signal: Signal, h: Hypothesis,
                          result: IterationResult) -> None:
        """Gate a single signal, dispatch on the verdict, and ledger it. Never raises."""
        held_out = self._claim_held_out_budget()
        try:
            gr = _gate.evaluate(signal, store=self.store, device=self.device,
                                held_out_once=held_out)
        except Exception as exc:
            result.errors.append(f"gate {signal.name}: {exc!r}")
            result.verdicts[signal.name] = Verdict.DEFER
            if held_out:
                self._release_held_out_budget()  # gate failed; refund the one-time touch
            return

        verdict = gr.verdict
        result.verdicts[signal.name] = verdict

        # Refund the one-time held-out touch when the gate returns DEFER
        # (coverage insufficient -- no evaluation happened, so the budget
        # was not actually used). The exception path above already handles
        # refunds for gate failures that raise.
        if held_out and verdict == Verdict.DEFER:
            self._release_held_out_budget()

        # Ledger every non-DEFER outcome (DEFER is requeued, not consumed).
        if verdict != Verdict.DEFER:
            self._safe(lambda: _ledger.record_signal(gr, target=signal.target),
                       result, f"ledger {signal.name}")

        if verdict == Verdict.SHIP:
            self._safe(lambda: self._ship(signal, gr, result),
                       result, f"ship {signal.name}")
        elif verdict == Verdict.VARIANCE_ONLY:
            self._safe(
                lambda: _wiring.wire_variance_signal(
                    signal, gr, store=self.store, dry_run=self.dry_run),
                result, f"wire_variance {signal.name}")
        elif verdict == Verdict.DEFER:
            self._bump_defer(signal.name)

    def _ship(self, signal: Signal, gr: Any, result: IterationResult) -> None:
        """Wire a SHIP signal: retrain + regime gate + write learned values back."""
        wr = _wiring.ship_signal(signal, gr, store=self.store,
                                 device=self.device, dry_run=self.dry_run)
        if getattr(wr, "ok", False):
            result.shipped.append(signal.name)

    # ---- ARM A+: deterministic LLM-FREE feature discovery (the inexhaustible proposer) ----
    def _run_discovery_arm(self, result: IterationResult) -> None:
        """Enumerate feature transforms -> cheap-screen -> the EXISTING honest gate -> ledger.

        This is the closed-loop proposer that lets the loop keep improving WITHOUT an LLM once the
        hand-written seed hypotheses are exhausted: ``src.loop.discovery`` deterministically enumerates
        transforms over the leak-safe pergame matrix and the honest gate (walk-forward + null-shuffle +
        ablation + FDR) decides. ADDITIVE + flag-gated (``CV_LOOP_DISCOVERY``); when the flag is unset this
        returns immediately and the loop behaves exactly as before. Discovered verdicts are recorded to the
        main ledger (FDR bookkeeping) + a discovered-signals ledger; a SHIP is recorded as validated-ready
        but NOT auto-grafted into the served model (the graft stays an explicit, reviewed step). Never raises.
        """
        if not os.environ.get("CV_LOOP_DISCOVERY"):
            return
        try:
            from . import discovery as _discovery
        except Exception as exc:  # pragma: no cover
            result.errors.append(f"discovery import: {exc!r}")
            return
        targets = [t.strip() for t in
                   os.environ.get("CV_LOOP_DISCOVERY_TARGETS", "pts").split(",") if t.strip()]
        top_k = int(os.environ.get("CV_LOOP_DISCOVERY_TOPK", "8") or "8")
        date = _dt.datetime.utcnow().date().isoformat()
        seen = self._safe(_discovery.load_discovered_families, result, "load_discovered") or set()
        for tgt in targets:
            try:
                results = _discovery.discover(tgt, top_k=top_k, device=self.device, seen_families=seen)
            except Exception as exc:
                result.errors.append(f"discover {tgt}: {exc!r}")
                continue
            for dr in results:
                seen.add(dr.spec.family_key())
                verdict = dr.gate.verdict
                result.verdicts[dr.spec.name] = verdict
                self._safe(lambda dr=dr: _discovery.record_discovered(dr, date=date),
                           result, f"record_discovered {dr.spec.name}")
                if verdict != Verdict.DEFER:
                    self._safe(lambda dr=dr: _ledger.record_signal(dr.gate, target=dr.target),
                               result, f"ledger {dr.spec.name}")
                if verdict == Verdict.SHIP:
                    result.shipped.append(dr.spec.name)

    # ---- ARM B: intelligence -------------------------------------------------
    def _run_intel_arm(self, result: IterationResult) -> None:
        """ARM-B inner loop: build -> validate -> bridge-persist -> memory note.

        A full run builds every discovered section over the whole universe. In
        dry-run (smoke) mode we build a small REPRESENTATIVE sample (a few player
        sections + a few team sections) so ``--once --dry-run`` proves the path
        for BOTH entity types quickly without a production-scale 28-section sweep.
        """
        as_of = _dt.datetime.utcnow()
        sections = self._discover_sections(result)
        if self.dry_run:
            sections = self._sample_sections(sections)
        for section in sections:
            try:
                self._run_one_section(section, as_of, result)
            except Exception as exc:
                result.errors.append(f"intel {getattr(section,'name','?')}: {exc!r}")

    @staticmethod
    def _sample_sections(sections: List[AtlasSection]) -> List[AtlasSection]:
        """Pick a small representative slice (>=1 player + >=1 team section)."""
        players = [s for s in sections if getattr(s, "entity", None) == "player"]
        teams = [s for s in sections if getattr(s, "entity", None) == "team"]
        return players[:_DRY_RUN_SECTION_CAP] + teams[:_DRY_RUN_SECTION_CAP]

    def _run_one_section(self, section: AtlasSection, as_of: _dt.datetime,
                         result: IterationResult) -> None:
        """Build + validate + persist a single atlas section over its entities."""
        if _ledger.already_tested(section.section_key(), kind="atlas"):
            return
        entities = self._section_entities(section)
        artifacts = []
        for eid in entities:
            try:
                art = section.build(eid, as_of)
            except Exception as exc:
                result.errors.append(f"build {section.name}:{eid}: {exc!r}")
                continue
            if art is None:
                continue
            vr = _intel_validator.validate(section, art)
            if not getattr(vr, "ok", False):
                continue
            if getattr(vr, "downgraded_confidence", None):
                art.confidence = vr.downgraded_confidence
            artifacts.append(art)

        if not artifacts:
            self._safe(lambda: _ledger.record_atlas(
                _dummy_atlas(section), verdict=Verdict.DEFER.value,
                reason="no validated entities"), result, f"ledger {section.name}")
            return

        # Persist by EXTENDING the factory (1 parquet + 1 sec_ fn + registry).
        self._safe(lambda: _bridge.register_section(
            section, artifacts, store=self.store, dry_run=self.dry_run),
            result, f"bridge {section.name}")

        # Durable memory note + index for the (validated) discovery.
        note = self._safe(lambda: self._write_section_memory(section, artifacts),
                          result, f"memory {section.name}")
        if note:
            result.notes.append(str(note))

        self._safe(lambda: _ledger.record_atlas(
            artifacts[0], verdict=Verdict.SHIP.value,
            reason=f"{len(artifacts)} entities validated"),
            result, f"ledger {section.name}")
        result.atlas_built.append(section.section_key())

    def _write_section_memory(self, section: AtlasSection, artifacts: List[Any]) -> Any:
        """Compose + write the durable memory note for a persisted atlas section."""
        slug = f"atlas_{section.entity}_{section.name}"
        title = f"{section.entity.title()} atlas: {section.name}"
        conf = artifacts[0].confidence if artifacts else "low"
        as_of = artifacts[0].as_of if artifacts else None
        body = (f"Atlas section `{section.name}` ({section.entity}) persisted for "
                f"{len(artifacts)} entities via the profile-factory bridge "
                f"(parquet `{section.parquet_name()}`, `{section.sec_fn_name()}`). "
                f"Source: {section.source_name}; confidence {conf}; as-of {as_of}. "
                f"Reserved CV slots: {sorted(section.cv_fields().keys())}.")
        index_line = (f"[{title}](project_{slug}.md) - {len(artifacts)} entities, "
                      f"conf {conf}, src {section.source_name}.")
        return _memory_writer.write_finding(
            slug=slug, title=title, body=body, note_type="project",
            index_line=index_line, dry_run=self.dry_run)

    # ---- discovery (resilient: empty package -> empty registry) --------------
    def _discover_signals(self, result: IterationResult) -> Dict[str, Type[Signal]]:
        """Import every ``signals/*.py`` and map ``Signal.name -> class``."""
        return self._discover("signals", Signal, result)

    def _discover_sections(self, result: IterationResult) -> List[AtlasSection]:
        """Import every ``intel/*.py`` and instantiate each AtlasSection subclass."""
        classes = self._discover("intel", AtlasSection, result)
        out: List[AtlasSection] = []
        for cls in classes.values():
            try:
                out.append(cls())
            except Exception as exc:
                result.errors.append(f"instantiate section {cls.__name__}: {exc!r}")
        return out

    def _discover(self, package: str, base: type,
                  result: IterationResult) -> Dict[str, type]:
        """Generic resilient discovery of concrete ``base`` subclasses in ``package``.

        Returns {class-attr ``name`` -> class}. An absent/empty package, an
        un-importable module, or an abstract subclass are all skipped silently
        (the loop must run before the 20 signals / 28 sections are built).
        """
        out: Dict[str, type] = {}
        pkg_dir = ROOT / package
        if not pkg_dir.is_dir():
            return out
        for mod_info in pkgutil.iter_modules([str(pkg_dir)]):
            mod_name = mod_info.name
            if mod_name.startswith("_"):
                continue
            try:
                module = importlib.import_module(f"{package}.{mod_name}")
            except Exception as exc:
                result.errors.append(f"import {package}.{mod_name}: {exc!r}")
                continue
            for _, obj in inspect.getmembers(module, inspect.isclass):
                if (issubclass(obj, base) and obj is not base
                        and not inspect.isabstract(obj)
                        and obj.__module__ == module.__name__):
                    name = getattr(obj, "name", None)
                    if isinstance(name, str) and name:
                        out[name] = obj
        return out

    def _section_entities(self, section: AtlasSection) -> List[Any]:
        """Resolve the entity ids a section should be built for.

        Resolution order:
          1. ``section.entities()`` (preferred — the section declares its universe).
          2. ``section.entity_ids`` class attribute.
          3. FALLBACK to the canonical profile-factory universe
             (``data/cache/profiles/PLAYER_INDEX.json`` /``TEAM_INDEX.json``),
             selecting the player-id or team-tricode list to match ``section.entity``.

        The fallback is what lets the orchestrator actually build the 28 sections
        end-to-end: none of them self-declare a universe, but the profile indices
        enumerate every player/team the factory already knows about (leak-safe —
        the ids are static identity, not future stats).
        """
        fn = getattr(section, "entities", None)
        if callable(fn):
            try:
                return list(fn())
            except Exception:
                return []
        ids = getattr(section, "entity_ids", None)
        if ids:
            return list(ids)
        # In dry-run (smoke) mode, sample a small slice so the path is PROVEN
        # end-to-end fast; full runs build the whole universe.
        limit = _DRY_RUN_ENTITY_CAP if self.dry_run else None
        return self._universe_from_index(section.entity, limit=limit)

    def _universe_from_index(self, entity_type: str,
                             *, limit: Optional[int] = None) -> List[Any]:
        """Read the player/team id universe from the cached profile indices.

        Returns player ids (ints) for ``entity_type == 'player'`` or team
        tricodes (str) for ``'team'``. Returns ``[]`` when the index is absent
        (fresh clone) so the arm degrades gracefully. Cached per process.
        """
        cache = getattr(self, "_universe_cache", None)
        if cache is None:
            cache = self._universe_cache = {}  # type: ignore[attr-defined]
        if entity_type not in cache:
            cache[entity_type] = self._load_universe(entity_type)
        ids = cache[entity_type]
        return ids[:limit] if limit else ids

    @staticmethod
    def _load_universe(entity_type: str) -> List[Any]:
        """Load and parse the relevant profile index file (best-effort)."""
        fname = ("PLAYER_INDEX.json" if entity_type == "player"
                 else "TEAM_INDEX.json")
        path = ROOT / "data" / "cache" / "profiles" / fname
        if not path.exists():
            return []
        try:
            idx = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        if entity_type == "player":
            return [p["player_id"] for p in idx.get("players", [])
                    if isinstance(p, dict) and p.get("player_id") is not None]
        return [t["team"] for t in idx.get("teams", [])
                if isinstance(t, dict) and t.get("team")]

    # ---- held-out / FDR budget bookkeeping -----------------------------------
    def _claim_held_out_budget(self) -> bool:
        """Claim the one-time held-out touch (returns True at most ONCE per loop life).

        The final held-out set must be touched exactly once across the whole loop
        lifetime; we record the spend in the checkpoint so a resumed loop never
        re-spends it. Disabled entirely in dry_run.
        """
        if self.dry_run:
            return False
        if self._ckpt.get("held_out_spent"):
            return False
        self._ckpt["held_out_spent"] = True
        self._save_checkpoint()
        return True

    def _release_held_out_budget(self) -> None:
        """Refund a held-out claim when the gate call failed before using it."""
        self._ckpt["held_out_spent"] = False
        self._save_checkpoint()

    def _bump_defer(self, name: str) -> None:
        """Increment the DEFER attempt counter for a hypothesis (back-off bookkeeping)."""
        d = self._ckpt.setdefault("defer_attempts", {})
        d[name] = int(d.get(name, 0)) + 1
        self._save_checkpoint()

    # ---- checkpoint persistence ----------------------------------------------
    def _load_checkpoint(self) -> Dict[str, Any]:
        """Load the resume checkpoint (iterations, held-out spend, defer counts)."""
        if _CHECKPOINT_PATH.exists():
            try:
                return json.loads(_CHECKPOINT_PATH.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        return {"iterations": 0, "held_out_spent": False, "defer_attempts": {}}

    def _save_checkpoint(self) -> None:
        """Persist the checkpoint atomically (best-effort; never raises)."""
        if self.dry_run:
            return
        try:
            _CHECKPOINT_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp = _CHECKPOINT_PATH.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(self._ckpt, indent=2), encoding="utf-8")
            tmp.replace(_CHECKPOINT_PATH)
        except OSError:
            pass

    # ---- utilities -----------------------------------------------------------
    def _safe(self, fn, result: IterationResult, label: str) -> Any:
        """Run ``fn`` capturing any exception into ``result.errors`` (never raises)."""
        try:
            return fn()
        except Exception as exc:
            result.errors.append(f"{label}: {exc!r}")
            return None


def _dummy_atlas(section: AtlasSection):
    """A minimal AtlasArtifact stand-in for ledgering a DEFER'd (empty) section."""
    from .atlas import AtlasArtifact
    return AtlasArtifact(section=section.section_key(), entity=section.entity,
                         entity_id=None, confidence="low")
