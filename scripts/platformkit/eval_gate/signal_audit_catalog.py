"""Catalog arm of the signal audit: declared evaluability + the AsOfContext adapter.
S396 AMENDMENT 1(b)/2(b). The interface is `build(self, ctx: AsOfContext)`, NOT `compute`. A
member is EVALUABLE when its DECLARED target is the home-win outcome, its DECLARED scope
includes pregame, it declares no `reads_atlas` section AND its build body names no
point-in-time read (`self.store`, `self.read`, `ctx.extra`) -- all by AST, so the census
never imports the human-gated catalog code; `recheck` re-derives a SEALED member the same way
and the import happens only when a member is actually built.
ONE AsOfContext per state comes from the strict test view and nothing else
(CONTEXT_DECLARATION enumerates every field; `extra` stays empty). `context_from_state`
re-redacts in strict mode and refuses any key outside TEST_VIEW_KEYS; a LeakError is
fail-closed and ENDS the run (AMENDMENT 2(c)). The census walks CANONICAL order (parsed
decision time, then game_id), never the loader's. `AsOfContext` is READ-ONLY from
`src.loop.signal`; `src/` is never edited. Calibration language only.
"""
from __future__ import annotations
import ast
import importlib
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Sequence, Tuple

from src.loop.signal import AsOfContext

from scripts.platformkit.eval_gate.signal_audit_family import EVALUABLE, make_member
from scripts.platformkit.eval_gate.signal_audit_verdicts import COVERAGE
from scripts.platformkit.eval_gate.walkforward import (
    LeakError, TEST_VIEW_KEYS, redact_test_view,
)
from scripts.platformkit.execution.venue_time import parse_venue_time, venue_time_reason

SOURCE = "catalog"
NS = "catalog:"
HOME_WIN_TARGET = "winprob"
PREGAME = "pregame"
PREGAME_SCOPES = (PREGAME, "both")
SEASON_START_MONTH = 8
CATALOG_GLOB = "domains/*/signal_catalog*.py"
DOMAIN_SPORT = {"basketball_nba": "nba", "mlb": "mlb", "soccer": "soccer", "tennis": "tennis"}
BUILD_FAILED = "NOT_EVALUABLE:build_failed"
NE_NO_BUILD = "NOT_EVALUABLE:catalog class %s exposes no build method"
NE_TARGET = "NOT_EVALUABLE:catalog target %r is not the home-win outcome (%r)"
NE_SCOPE = "NOT_EVALUABLE:catalog scope %r does not include pregame"
NE_SPORT = "NOT_EVALUABLE:catalog domain %s is not the family sport %s"
BODY_READS = ("self.store", "self.read", "ctx.extra")
NE_INPUT_DECLARED = "NOT_EVALUABLE:input missing on this machine: atlas section(s) %s; this runner binds no point-in-time store (Signal(store=None))"
NE_INPUT_BODY = "NOT_EVALUABLE:input missing on this machine: build body reads %s; this runner binds no point-in-time store (Signal(store=None))"
CONTEXT_DECLARATION = {
    "fields": ("decision_time = state_ts through parse_venue_time; team = home; opp = away; is_home = True; "
               "game_id; game_date; season from game_date; scope = pregame; player_id = None; live = None; extra = {}"),
    "source_keys": "the strict test view only (walkforward.TEST_VIEW_KEYS)",
    "unzoned_state_ts": "runner and standalone context refuse unzoned timestamps",
    "store": "Signal(store=None): no point-in-time store is bound",
    "census_order": "CANONICAL: parsed decision time, then game_id -- never the loader's order",
    "per_state_failure": "a None, an exception or a non-finite value is COUNTED, never zeroed",
}

class BuildFailed(ValueError):
    """One state's feature could not be built. Counted under `reason`, never imputed."""
    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = "%s:%s" % (BUILD_FAILED, reason)
        super().__init__(self.reason if not detail else "%s (%s)" % (self.reason, detail))


@dataclass(frozen=True)
class Declaration:
    """What one catalog class declares on disk, read without importing it."""

    domain: str
    cls_name: str
    module: str
    name: str
    target: str
    scope: str
    reads_atlas: Tuple[str, ...]
    emits: Tuple[str, ...]
    has_build: bool
    body_reads: Tuple[str, ...] = ()

    @property
    def signal_id(self) -> str:
        return "%s:%s" % (self.domain, self.cls_name)


def _value(node: ast.AST) -> object:
    if isinstance(node, (ast.List, ast.Tuple)):
        return [item.value for item in node.elts if isinstance(item, ast.Constant)]
    return node.value if isinstance(node, ast.Constant) else None


def _class_attrs(node: ast.ClassDef) -> Dict[str, object]:
    attrs: Dict[str, object] = {}
    for stmt in node.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and stmt.value:
            attrs[stmt.target.id] = _value(stmt.value)
        elif isinstance(stmt, ast.Assign):
            attrs.update({t.id: _value(stmt.value) for t in stmt.targets if isinstance(t, ast.Name)})
    return attrs


def _body_reads(fn: ast.FunctionDef | None) -> Tuple[str, ...]:
    """AMENDMENT 2(b): the point-in-time reads a `build` body NAMES, by AST, never by import."""
    named = {"%s.%s" % (node.value.id, node.attr) for node in ast.walk(fn)
             if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)} if fn else set()
    return tuple(name for name in BODY_READS if name in named)


def declarations(root: Path | None = None) -> List[Declaration]:
    """Every on-disk catalog class with its DECLARED target / scope / atlas reads (AST)."""
    base = Path(root) if root else Path(__file__).resolve().parents[3]
    out: List[Declaration] = []
    for path in sorted(base.glob(CATALOG_GLOB)):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if not isinstance(node, ast.ClassDef) or not node.name.endswith("Signal"):
                continue
            attrs = _class_attrs(node)
            reads = attrs.get("reads_atlas") or []
            emits = attrs.get("emits") or []
            build_def = next((s for s in node.body
                              if isinstance(s, ast.FunctionDef) and s.name == "build"), None)
            out.append(Declaration(
                domain=path.parent.name, cls_name=node.name,
                module="domains.%s.%s" % (path.parent.name, path.stem),
                name=str(attrs.get("name") or node.name), target=str(attrs.get("target")),
                scope=str(attrs.get("scope")),
                reads_atlas=tuple(str(item) for item in reads),
                emits=tuple(str(item) for item in emits),
                has_build=build_def is not None, body_reads=_body_reads(build_def)))
    return out


def evaluability(decl: Declaration, sport: str | None = None) -> str:
    """EVALUABLE or the exact NOT_EVALUABLE reason from the declaration alone. `sport` None
    gives the sport-blind census; a family passes its own, so another domain is not counted."""
    if not decl.has_build:
        return NE_NO_BUILD % decl.cls_name
    if decl.target != HOME_WIN_TARGET:
        return NE_TARGET % (decl.target, HOME_WIN_TARGET)
    if decl.scope not in PREGAME_SCOPES:
        return NE_SCOPE % (decl.scope,)
    if sport is not None and DOMAIN_SPORT.get(decl.domain) != str(sport):
        return NE_SPORT % (decl.domain, sport)
    if decl.reads_atlas:
        return NE_INPUT_DECLARED % (",".join(decl.reads_atlas),)
    if decl.body_reads:
        return NE_INPUT_BODY % (",".join(decl.body_reads),)
    return EVALUABLE


def declares(decl: Declaration) -> dict:
    """The store / atlas paths and the interface a class declares, recorded on the member."""
    return {"signal_name": decl.name, "target": decl.target, "scope": decl.scope, "module": decl.module,
            "reads_atlas": list(decl.reads_atlas), "body_reads": list(decl.body_reads),
            "emits": list(decl.emits), "has_build": decl.has_build, "interface": "build(ctx: AsOfContext)"}


def members(sport: str, start: str, end: str, *, domains: Sequence[str] = (),
            decls: Sequence[Declaration] | None = None) -> List[dict]:
    """One manifest member per catalog class, with its declared evaluability. A sealed family
    names ONE sport: the sport-blind mode is `census` only and can no longer build members."""
    chosen = list(decls if decls is not None else declarations())
    if domains:
        chosen = [d for d in chosen if d.domain in set(domains)]
    return [make_member(d.signal_id, SOURCE, evaluability(d, sport), sport, start, end,
                        declares=declares(d), builder=NS + d.signal_id) for d in chosen]


def season_from_date(game_date: str) -> str:
    """The declared season rule: a season is named by the calendar year it opens in."""
    year, month = int(str(game_date)[:4]), int(str(game_date)[5:7])
    opened = year if month >= SEASON_START_MONTH else year - 1
    return "%d-%02d" % (opened, (opened + 1) % 100)


def context_from_state(state: dict) -> AsOfContext:
    """ONE AsOfContext from the strict test view and nothing else: `redact_test_view` in
    strict mode drops the settled keys and raises LeakError on any undeclared key, and the
    explicit check below is the assertion the amendment asks for."""
    view = redact_test_view(state, strict=True)
    stray = sorted(key for key in view if key not in TEST_VIEW_KEYS)
    if stray:
        raise LeakError("context key(s) %s lie outside TEST_VIEW_KEYS" % stray)
    stamp = view.get("state_ts")
    epoch = parse_venue_time(stamp)
    if epoch is None:
        raise BuildFailed("decision_time_refused", str(venue_time_reason(stamp)))
    when = datetime.fromtimestamp(float(epoch), timezone.utc)
    game_date = str(view.get("game_date") or when.date().isoformat())
    return AsOfContext(decision_time=when, player_id=None, team=view.get("home"), is_home=True,
                       opp=view.get("away"), game_id=view.get("game_id"), game_date=game_date,
                       season=str(view.get("season") or season_from_date(game_date)), scope=PREGAME, snapshot=None, live=None)


def _order_key(state: dict) -> Tuple[float, str]:
    return (context_from_state(state).decision_time.timestamp(), str(state.get("game_id")))


def load_signal(decl: Declaration):
    """Import and instantiate the class with NO store bound (a READ-ONLY import)."""
    return getattr(importlib.import_module(decl.module), decl.cls_name)()

def make_builder(decl: Declaration) -> Callable[[dict], float]:
    """Per-state adapter: ordinary build failures are counted; LeakError terminates."""
    signal = load_signal(decl)
    key = decl.emits[0] if decl.emits else decl.name
    def build(state: dict) -> float:
        ctx = context_from_state(state)
        try:
            value = signal.build(ctx)
        except LeakError:
            raise
        except Exception as exc:                       # the class's own failure, counted
            raise BuildFailed("build_raised_%s" % type(exc).__name__, str(exc)) from exc
        if isinstance(value, dict):
            value = value.get(key)
        if value is None:
            raise BuildFailed("no_value_for_declared_key", key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise BuildFailed("not_a_real_number", repr(value))
        if not math.isfinite(number := float(value)):
            raise BuildFailed("not_finite", key)
        return number
    return build
def sealed_declaration(member: dict) -> Declaration:
    """The Declaration the manifest SEALED, never disk (Q1); NO import runs here."""
    name = str(member["feature_builder"])
    if not name.startswith(NS) or not name[len(NS):]:
        raise ValueError("unknown catalog builder %r; only %s<domain>:<class>" % (name, NS))
    domain, _, cls_name = name[len(NS):].partition(":")
    sealed = dict(member["declares"])
    if not cls_name or not sealed.get("module"):
        raise ValueError("member %r seals no catalog module to build from" % member["member_key"])
    return Declaration(domain=domain, cls_name=cls_name, module=str(sealed["module"]),
                       name=str(sealed.get("signal_name") or cls_name),
                       target=str(sealed.get("target")), scope=str(sealed.get("scope")),
                       reads_atlas=tuple(sealed.get("reads_atlas") or ()),
                       emits=tuple(sealed.get("emits") or ()), has_build=bool(sealed.get("has_build", True)),
                       body_reads=tuple(sealed.get("body_reads") or ()))
def recheck(member: dict, sport: str) -> Tuple[str, dict, str]:
    """A SEALED member's own evaluability, declares and signal_id, for validate_manifest."""
    return evaluability(decl := sealed_declaration(member), sport), declares(decl), decl.signal_id
def builder_for(member: dict) -> Tuple[Callable[[dict], float], Declaration]:
    """The sealed builder and its declaration; the catalog import happens HERE, not earlier."""
    return make_builder(decl := sealed_declaration(member)), decl
def coverage(build: Callable[[dict], float], states: Sequence[dict]) -> Tuple[List[dict], Dict[str, object]]:
    """Build every state once in CANONICAL order (never the loader's, so a class that keeps
    state cannot make eligibility follow arrival): keep the finite ones, COUNT the failures."""
    kept, reasons = [], {}
    for state in sorted(states, key=_order_key):
        try:
            build(state)
        except BuildFailed as exc:
            reasons[exc.reason] = int(reasons.get(exc.reason, 0)) + 1
            continue
        kept.append(state)
    games = {str(s["game_id"]) for s in kept}
    return kept, {"n_states": int(len(states)), "n_states_finite": int(len(kept)),
                  "n_games_finite": int(len(games)), "n_build_failed": int(len(states) - len(kept)),
                  "build_failed_reasons": dict(sorted(reasons.items()))}
def arm(member: dict, states: Sequence[dict]) -> Tuple[Callable[[], Callable[[dict], float]], List[dict], Dict[str, object]]:
    """The states this member covers, plus a FACTORY of FRESH builders: the census builder is
    NEVER the scored one and the scorer takes a new one per fold (a class may keep state)."""
    kept, info = coverage(builder_for(member)[0], states)
    return (lambda: builder_for(member)[0]), kept, info
def coverage_note(info: Dict[str, object], n_min: int) -> str:
    return "%s: %s of %s game(s) carry a finite feature, landed n_min %d; build_failed %s %s" % (
        COVERAGE, info["n_games_finite"], info["n_states"], n_min, info["n_build_failed"], info["build_failed_reasons"])
def canonical_time(value: object, reason: str = "decision_time_refused") -> str:
    """Canonical fixed-width UTC text, so the landed string ordering is chronological."""
    if (epoch := parse_venue_time(value)) is None:
        raise ValueError(reason)
    fraction = re.search(r"\.(\d+)", str(value))
    if fraction and any(d != "0" for d in fraction[1][6:]):
        raise ValueError(reason + ":submicrosecond_precision")
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="microseconds")
def prepare_states(raw_states: Sequence[dict]) -> Tuple[List[dict], dict]:
    """Validate timing evidence; settlement metadata never enters the builder's view."""
    states, settled = [], {}
    for raw in raw_states:
        try:
            state = dict(raw)
            state["state_ts"] = canonical_time(state["state_ts"])
            available = canonical_time(state.pop("reference_available_at", None), "reference_availability_unknown")
            if available > state["state_ts"]:
                raise LeakError("reference_unavailable_at_decision")
            settled[state["game_id"]] = canonical_time(state.pop("settled_at", None), "settlement_unknown")
            state["feature_avail"] = {k: canonical_time(v, "feature_time_refused")
                                      for k, v in state.get("feature_avail", {}).items()}
            states.append(state)
        except (KeyError, TypeError, ValueError, LeakError) as exc:
            raise type(exc)("%s; game_id=%r; value=%r" % (exc, raw.get("game_id"), raw)) from exc
    return states, settled
def census(sport: str | None = None, decls: Sequence[Declaration] | None = None) -> Dict[str, int]:
    """Counts by EVALUABLE / exact NOT_EVALUABLE reason. ne_input_declared (reads_atlas) and
    ne_input_body (the build body) are DISTINCT reasons, so the two paths are counted apart."""
    marks = [evaluability(d, sport) for d in (decls if decls is not None else declarations())]
    return {mark: marks.count(mark) for mark in sorted(set(marks))}
