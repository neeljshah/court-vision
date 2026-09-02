"""S27 -- the answer-layer envelope contract, over 50 fixed probes.

Drives `docs/evidence/answer_probe_50.json` through the SAME
`tools.handler_for(name)` the live MCP server uses and checks the envelope
contract from PLAN_EXECUTION_ANSWER_LAYER_2026-09-03.md section 3:

  status is EXACTLY one of {ok, no_data, not_supported, refused};
  ok            -> source_artifact and as_of non-empty, plus staleness_days
                   whenever source_artifact names a file that exists on disk;
  not ok        -> a note, and no numeric answer payload;
  edge language -> refused (.claude/rules/no-edge-claims.md);
  unknown category / unknown kind -> not_supported, never ok.

Plus the plan's staleness policy, asserted only where the plan pins a bound:
injuries 7 d and analytics receipts / execution_status 48 h refuse past the
bound; pinned corpora (win_probability, profiles) report staleness and never
refuse, but their `as_of` must describe the DATA -- an `as_of` stamped within
15 minutes of the call is the wall clock, not the corpus.

RED IS THE HONEST DELIVERABLE. These probes read the real artifacts on this
box; a red here is a finding about the surface, not a broken test. Do NOT
weaken an assert to make it green (VERIFIER_CONTRACT Q3) -- fix the handler in
its own gated diff, or record the row as CLOSED AT LIMIT.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import pytest

from scripts.platformkit.mcp_server import tools as mcp_tools

_ROOT = Path(__file__).resolve().parents[3]
_PROBE_FILE = _ROOT / "docs/evidence/answer_probe_50.json"
_PROBES: List[Dict[str, Any]] = json.loads(_PROBE_FILE.read_text(encoding="utf-8"))

# The 13 query tools the contract covers. run_burst is excluded on purpose: it
# is an ACTION whose documented statuses are ok|aborted, not the four above.
_TOOLS_UNDER_TEST = {
    "ask", "scouting_report", "comparables", "matchup_preview", "win_probability",
    "injury_report", "analytics_receipts", "system_health", "strength_atlas",
    "mechanism_exposure", "tracking_program_status", "harness_health", "execution_status",
}
_STATUSES = ("ok", "no_data", "not_supported", "refused")
# Numbers that are metadata about the answer, not the answer -- a fail-closed
# envelope may carry these while still returning no number.
_META_NUMERIC = {"staleness_days", "k", "top_n", "corpus_staleness_days"}
_WALL_CLOCK_WINDOW_S = 900


def _parse(stamp: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _existing_sources(source_artifact: Any) -> List[str]:
    values = source_artifact if isinstance(source_artifact, list) else [source_artifact]
    return [v for v in values
            if isinstance(v, str) and (_ROOT / v.replace("\\", "/")).is_file()]


def _violations(env: Dict[str, Any], probe: Dict[str, Any]) -> List[str]:
    """Every contract breach in one envelope -- all of them, not just the first."""
    out: List[str] = []
    if not isinstance(env, dict):
        return ["NOT_AN_ENVELOPE:%s" % type(env).__name__]
    status = env.get("status")
    if status not in _STATUSES:
        out.append("BAD_STATUS:%r" % (status,))
    expect = probe["expect"]
    if expect != "any_valid" and status != expect:
        out.append("EXPECT_%s_GOT_%s" % (expect, status))
    if status == "ok":
        out.extend(_ok_violations(env, probe))
    else:
        if not env.get("note"):
            out.append("NOTOK_NO_NOTE")
        numeric = sorted(k for k, v in env.items()
                         if isinstance(v, (int, float)) and not isinstance(v, bool)
                         and k not in _META_NUMERIC)
        if numeric:
            out.append("NOTOK_NUMERIC_PAYLOAD:%s" % numeric)
    return out


def _ok_violations(env: Dict[str, Any], probe: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    if not env.get("source_artifact"):
        out.append("OK_NO_SOURCE_ARTIFACT")
    if not env.get("as_of"):
        out.append("OK_NO_AS_OF")
    if _existing_sources(env.get("source_artifact")) and env.get("staleness_days") is None:
        out.append("OK_NO_STALENESS_DAYS")
    stamp = _parse(env.get("as_of"))
    bound = probe.get("max_ok_staleness_days")
    if bound is not None:
        # A bound that cannot be evaluated is a bound that does not bind.
        if stamp is None:
            out.append("OK_ASOF_UNPARSEABLE:%r" % (env.get("as_of"),))
        else:
            age_d = (datetime.now(timezone.utc) - stamp).total_seconds() / 86400.0
            if age_d > bound:
                out.append("OK_OVER_STALENESS_BOUND:%.1fd>%sd" % (age_d, bound))
    if probe.get("asof_must_describe_data") and stamp is not None:
        age_s = abs((datetime.now(timezone.utc) - stamp).total_seconds())
        if age_s < _WALL_CLOCK_WINDOW_S:
            out.append("OK_ASOF_IS_WALL_CLOCK")
    return out


def test_probe_file_is_the_fixed_50_over_13_tools():
    assert len(_PROBES) == 50
    assert len({p["id"] for p in _PROBES}) == 50
    assert {p["tool"] for p in _PROBES} == _TOOLS_UNDER_TEST
    assert "run_burst" not in {p["tool"] for p in _PROBES}
    for probe in _PROBES:
        assert probe["expect"] in ("any_valid",) + _STATUSES
        assert mcp_tools.handler_for(probe["tool"]) is not None, probe["tool"]


@pytest.mark.parametrize("probe", _PROBES, ids=[p["id"] for p in _PROBES])
def test_envelope_contract(probe):
    env = mcp_tools.handler_for(probe["tool"])(probe["arguments"])
    breaches = _violations(env, probe)
    assert not breaches, "%s %s(%s) status=%r -> %s" % (
        probe["id"], probe["tool"], json.dumps(probe["arguments"])[:90],
        env.get("status") if isinstance(env, dict) else env, "; ".join(breaches))
