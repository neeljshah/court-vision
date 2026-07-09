"""A deterministic stand-in for "any LLM following docs/AI_CONSUMER_CONTRACT.md".
No model call -- this IS the contract, executable, so the consistency battery
can assert an LLM client that actually follows the rules reproduces the
resolver's own numbers byte-for-byte. A real LLM client should do exactly
this: classify -> resolve -> format verbatim -> cite artifact + as-of.

Run: python -m scripts.platformkit.answers.contract_client "Trae Young gravity" --sport nba
"""
from __future__ import annotations

import argparse

from scripts.platformkit.answers import contracts as _contracts
from scripts.platformkit.answers import resolver_registry as R


def answer(query: str, sport: str = "nba", **kwargs) -> str:
    """Format one resolver envelope per AI_CONSUMER_CONTRACT.md rule 2 (quote
    verbatim) + rule 3 (cite artifact + as-of). Refusal/NOT_SUPPORTED are
    rendered plainly, never papered over with an invented number."""
    env = R.resolve(query, sport, **kwargs)
    status = env["status"]
    if status == "refused":
        return f"REFUSED -- {env['note']} (see {env['source_artifact']})"
    if status == "not_supported":
        return f"NOT_SUPPORTED -- {env['note']}"
    if status == "no_data":
        return f"NO_DATA -- {env.get('note') or env.get('detail') or 'zero rows matched'}"
    cat = env["category"]
    if cat in ("player_stat", "rating_attribute"):
        if cat == "player_stat":
            body = f"{env['entity_name']} {env['attribute']} = {env['raw_value']} (n={env['n']}, {env['status_label']})"
        else:
            body = (f"{env['entity_name']} {env['attribute']} percentile={env['percentile']} "
                     f"rating_2k={env['rating_2k']} (n={env['n']}, {env['status_label']})")
        return f"{body} | source: {env['source_artifact']} | as-of: {env['as_of']}"
    if cat == "concept_rating":
        if env.get("question_type") == "superlative" and env.get("top"):
            names = ", ".join(f"{e['entity_name']} ({e['composite']})" for e in env["top"])
            body = f"best {env['concept']}: {names}"
        elif env.get("question_type") == "comparison":
            body = f"{env['entity_a']['name']} vs {env['entity_b']['name']} on {env['concept']}: favored={env['favored']}"
        elif env.get("question_type") == "explanation":
            body = f"{env['entity_name']} {env['concept']} composite={env['composite']} (confidence={env['confidence']})"
        else:
            body = f"{cat} result for {env.get('concept')}"
        return f"{body} | source: {env['source_artifact']} | as-of: {env['as_of']}"
    if cat == "calibration_number":
        return (f"{env['sport'].upper()} calibration: baseline_brier={env['baseline_brier']} "
                f"improved_brier={env['improved_brier']} (n={env['n']}, method={env['method']}) "
                f"| source: {env['source_artifact']} | as-of: {env['as_of']}")
    if cat == "historical_result":
        return (f"{env['away_team']} {env['away_score']} @ {env['home_team']} {env['home_score']} "
                f"-- winner {env['winner']} | source: {env['source_artifact']} | as-of: {env['as_of']}")
    return f"UNHANDLED category {cat}"


def _render(query: str, sport: str = "nba", **kwargs) -> str:
    """ASCII-stdout-safe wrapper (cp1252 console; entity names may carry
    diacritics) -- use this for anything printed, `answer()` for anything
    compared/asserted on the real value."""
    return _contracts._ascii(answer(query, sport, **kwargs))


def main(argv=None):
    p = argparse.ArgumentParser(description="Contract-following client over resolver_registry.")
    p.add_argument("query")
    p.add_argument("--sport", default="nba")
    p.add_argument("--team")
    p.add_argument("--opponent")
    a = p.parse_args(argv)
    kwargs = {k: v for k, v in (("team", a.team), ("opponent", a.opponent)) if v}
    print(_render(a.query, a.sport, **kwargs))


if __name__ == "__main__":
    main()
