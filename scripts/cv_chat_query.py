"""
CV Chat Query Handler — CourtVision AI Chat Tool Integration
=============================================================
Example query handler for Claude API tool integration.
Bridges natural-language NBA questions to CV intelligence atlases.

Usage:
    python scripts/cv_chat_query.py "What's Jayson Tatum's CV profile?"
    python scripts/cv_chat_query.py "Who plays like Damian Lillard?"
    python scripts/cv_chat_query.py "How will Tatum play vs MEM?"
    python scripts/cv_chat_query.py "What's BOS's defensive scheme?"
    python scripts/cv_chat_query.py "Who's hot right now?"
    python scripts/cv_chat_query.py "How confident should I bet Damian Lillard pts?"

Integration with Claude API:
    from scripts.cv_chat_query import answer_query
    result = answer_query("What's Tatum's CV profile?")
    # Pass result dict as tool_result content to Claude API
"""

import json
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE = Path(r'C:\Users\neelj\nba-ai-system')
INTEL = BASE / 'data' / 'intelligence'
FACTS_PATH = INTEL / 'ai_chat_facts.json'
INDEX_PATH = INTEL / 'ai_chat_index.json'


# ---------------------------------------------------------------------------
# Lazy loaders
# ---------------------------------------------------------------------------
_facts: dict | None = None
_index: dict | None = None
_atlases: dict = {}

NBA_TEAMS = {
    'atlanta': 'ATL', 'hawks': 'ATL',
    'brooklyn': 'BKN', 'nets': 'BKN',
    'boston': 'BOS', 'celtics': 'BOS',
    'charlotte': 'CHA', 'hornets': 'CHA',
    'chicago': 'CHI', 'bulls': 'CHI',
    'cleveland': 'CLE', 'cavaliers': 'CLE', 'cavs': 'CLE',
    'dallas': 'DAL', 'mavericks': 'DAL', 'mavs': 'DAL',
    'denver': 'DEN', 'nuggets': 'DEN',
    'detroit': 'DET', 'pistons': 'DET',
    'golden state': 'GSW', 'warriors': 'GSW', 'gsw': 'GSW',
    'houston': 'HOU', 'rockets': 'HOU',
    'indiana': 'IND', 'pacers': 'IND',
    'la clippers': 'LAC', 'clippers': 'LAC', 'lac': 'LAC',
    'la lakers': 'LAL', 'lakers': 'LAL', 'lal': 'LAL', 'los angeles lakers': 'LAL',
    'memphis': 'MEM', 'grizzlies': 'MEM', 'mem': 'MEM',
    'miami': 'MIA', 'heat': 'MIA',
    'milwaukee': 'MIL', 'bucks': 'MIL',
    'minnesota': 'MIN', 'timberwolves': 'MIN', 'wolves': 'MIN',
    'new orleans': 'NOP', 'pelicans': 'NOP',
    'new york': 'NYK', 'knicks': 'NYK',
    'oklahoma city': 'OKC', 'thunder': 'OKC',
    'orlando': 'ORL', 'magic': 'ORL',
    'philadelphia': 'PHI', '76ers': 'PHI', 'sixers': 'PHI',
    'phoenix': 'PHX', 'suns': 'PHX',
    'portland': 'POR', 'trail blazers': 'POR', 'blazers': 'POR',
    'sacramento': 'SAC', 'kings': 'SAC',
    'san antonio': 'SAS', 'spurs': 'SAS',
    'toronto': 'TOR', 'raptors': 'TOR',
    'utah': 'UTA', 'jazz': 'UTA',
    'washington': 'WAS', 'wizards': 'WAS',
    # Short codes also work directly
    'atl': 'ATL', 'bkn': 'BKN', 'bos': 'BOS', 'cha': 'CHA', 'chi': 'CHI',
    'cle': 'CLE', 'dal': 'DAL', 'den': 'DEN', 'det': 'DET',
    'hou': 'HOU', 'ind': 'IND', 'mia': 'MIA', 'mil': 'MIL', 'min': 'MIN',
    'nop': 'NOP', 'nyk': 'NYK', 'okc': 'OKC', 'orl': 'ORL', 'phi': 'PHI',
    'phx': 'PHX', 'por': 'POR', 'sac': 'SAC', 'sas': 'SAS', 'tor': 'TOR',
    'uta': 'UTA', 'was': 'WAS',
}


def _load_facts() -> dict:
    global _facts
    if _facts is None:
        if not FACTS_PATH.exists():
            raise FileNotFoundError(
                f"ai_chat_facts.json not found. Run: python scripts/build_ai_chat_corpus.py"
            )
        with open(FACTS_PATH, encoding='utf-8') as f:
            _facts = json.load(f)
    return _facts


def _load_index() -> dict:
    global _index
    if _index is None:
        if not INDEX_PATH.exists():
            raise FileNotFoundError(
                f"ai_chat_index.json not found. Run: python scripts/build_ai_chat_corpus.py"
            )
        with open(INDEX_PATH, encoding='utf-8') as f:
            _index = json.load(f)
    return _index


def _pid_str(pid_val) -> str:
    """Normalize player_id to integer string (strips .0 from floats)."""
    try:
        return str(int(float(pid_val)))
    except (TypeError, ValueError):
        return str(pid_val)


def _load_atlas(name: str):
    """Lazy-load a parquet or json atlas."""
    if name in _atlases:
        return _atlases[name]
    p_pq = INTEL / f'{name}.parquet'
    p_js = INTEL / f'{name}.json'
    if p_pq.exists():
        _atlases[name] = pd.read_parquet(p_pq)
    elif p_js.exists():
        with open(p_js, encoding='utf-8') as f:
            _atlases[name] = json.load(f)
    else:
        _atlases[name] = None
    return _atlases[name]


# ---------------------------------------------------------------------------
# Name / team resolution
# ---------------------------------------------------------------------------

def _resolve_player(query: str) -> tuple[str | None, dict | None]:
    """
    Try to find a player in facts by partial name match.
    Returns (canonical_name, player_fact_dict) or (None, None).
    """
    facts = _load_facts()
    players = facts.get('players', {})
    q = query.lower().strip()

    # Exact match
    for name, fact in players.items():
        if q == name.lower():
            return name, fact

    # Partial match — prefer longer overlaps
    best_name, best_fact, best_len = None, None, 0
    for name, fact in players.items():
        nlow = name.lower()
        # Check if query fragment appears in name or vice versa
        for part in q.split():
            if len(part) >= 3 and part in nlow:
                if len(part) > best_len:
                    best_name, best_fact, best_len = name, fact, len(part)

    if best_name:
        return best_name, best_fact

    # Also try the full player_id name from fingerprints
    return None, None


def _extract_player_name(question: str) -> str | None:
    """
    Extract a likely player name from natural-language question.
    Heuristics: proper nouns, removes noise words.
    """
    q = question.strip()
    # Remove common prefixes
    for prefix in ["what's ", "what is ", "who is ", "how will ", "how has ",
                   "show me ", "tell me about ", "give me ", "find me "]:
        q = re.sub(r'^\s*' + re.escape(prefix), '', q, flags=re.IGNORECASE)

    # Try to extract "FirstName LastName" pattern
    # Remove suffixes like "vs MEM", "play tonight", etc.
    q_clean = re.sub(r'\s+(vs\.?\s+\w+|against\s+\w+|play\s+.*|tonight.*|this\s+month.*)', '', q, flags=re.IGNORECASE)
    q_clean = re.sub(r"\bCV\b|\bprofile\b|\barchetype\b|\btrend\b|\bform\b|\bconfidence\b|\bKelly\b|\bmultiplier\b|\b's\b", '', q_clean, flags=re.IGNORECASE)
    q_clean = q_clean.strip().rstrip("?.,")

    # Return cleaned name candidate
    return q_clean.strip() if q_clean.strip() else None


def _extract_team_abbrev(question: str) -> str | None:
    """Extract team abbreviation from a question string."""
    q = question.lower()
    # Try 3-letter uppercase codes in original
    for m in re.finditer(r'\b([A-Z]{3})\b', question):
        code = m.group(1)
        if code in NBA_TEAMS.values():
            return code
    # Try city/name phrases
    for phrase, abbrev in sorted(NBA_TEAMS.items(), key=lambda x: -len(x[0])):
        if phrase in q:
            return abbrev
    return None


# ---------------------------------------------------------------------------
# Query handlers
# ---------------------------------------------------------------------------

def handle_profile_query(question: str) -> dict:
    """Handler: player CV profile / fingerprint."""
    name_candidate = _extract_player_name(question)
    pname, fact = _resolve_player(name_candidate or '')

    if fact is None:
        return {
            'query_type': 'player_profile',
            'status': 'not_found',
            'message': f"Player not found in CV atlas for: '{name_candidate}'. CV coverage: 230 players.",
            'tip': "Try full name (e.g. 'Jayson Tatum' not 'Tatum').",
        }

    fp = fact.get('fingerprint') or {}
    conf = fact.get('confidence') or {}
    form = fact.get('current_form') or {}

    response_text = (
        f"{pname} is classified as '{fp.get('archetype', 'Unknown')}'. "
        f"CV games tracked: {fp.get('n_cv_games', 0)}. "
    )
    if fp.get('touches_per_game'):
        response_text += f"Touches/game: {fp['touches_per_game']:.1f}. "
    if fp.get('paint_dwell_pct') is not None:
        response_text += f"Paint dwell: {fp['paint_dwell_pct'] * 100:.1f}%. "
    if fp.get('avg_shot_distance'):
        response_text += f"Avg shot distance: {fp['avg_shot_distance']:.1f}ft. "
    if fp.get('contested_shot_rate') is not None:
        response_text += f"Contested shot rate: {fp['contested_shot_rate'] * 100:.1f}%. "
    if conf.get('cv_volatility'):
        response_text += f"CV volatility: {conf['cv_volatility']:.2f} "
        response_text += "(low — predictable). " if conf['cv_volatility'] < 2.0 else "(high — unpredictable). "
    if conf.get('overall_confidence_mult'):
        response_text += f"Overall Kelly multiplier: {conf['overall_confidence_mult']:.2f}x. "
    if form.get('trend_tag'):
        response_text += f"Current form: {form['trend_tag']}."

    return {
        'query_type': 'player_profile',
        'player': pname,
        'status': 'found',
        'response': response_text,
        'raw': {
            'fingerprint': fp,
            'confidence': conf,
            'current_form': form,
        },
    }


def handle_similarity_query(question: str) -> dict:
    """Handler: who plays like [player]?"""
    name_candidate = _extract_player_name(question)
    pname, fact = _resolve_player(name_candidate or '')

    if fact is None:
        return {
            'query_type': 'player_similarity',
            'status': 'not_found',
            'message': f"Player not found for: '{name_candidate}'.",
        }

    similar = fact.get('similar_players', [])
    fp = fact.get('fingerprint') or {}

    if not similar:
        return {
            'query_type': 'player_similarity',
            'player': pname,
            'status': 'no_neighbors',
            'message': f"{pname} has no computed neighbors yet (may need more CV games).",
        }

    neighbors_text = ', '.join(
        f"{n['name']} (dist={n['distance']:.2f})" for n in similar[:5]
    )
    response_text = (
        f"{pname} (archetype: {fp.get('archetype', 'Unknown')}) "
        f"plays most similarly to: {neighbors_text}."
    )

    return {
        'query_type': 'player_similarity',
        'player': pname,
        'status': 'found',
        'response': response_text,
        'raw': {'similar_players': similar[:5]},
    }


def handle_trend_query(question: str) -> dict:
    """Handler: is [player] hot or cold / what's their trend?"""
    name_candidate = _extract_player_name(question)
    pname, fact = _resolve_player(name_candidate or '')

    if fact is None:
        return {
            'query_type': 'player_trend',
            'status': 'not_found',
            'message': f"Player not found for: '{name_candidate}'.",
        }

    form = fact.get('current_form') or {}
    roll = fact.get('rolling_trend') or {}

    tag = form.get('trend_tag') or roll.get('trend_tag') or 'UNKNOWN'
    drivers = roll.get('top_3_drivers', [])
    driver_text = ', '.join(
        f"{d.get('feature','?')} ({'+' if (d.get('z') or 0) > 0 else ''}{d.get('z', 0):.2f}σ)"
        for d in drivers[:3]
        if d.get('z') is not None
    ) or 'no clear drivers'

    response_text = (
        f"{pname} is currently: {tag}. "
    )
    if roll.get('n_games_recent'):
        response_text += f"Based on last {roll['n_games_recent']} games vs prior {roll['n_games_prior']}. "
    if driver_text:
        response_text += f"Top CV drivers: {driver_text}. "
    if form.get('latest_game_date'):
        response_text += f"Latest CV game: {form['latest_game_date']}."

    return {
        'query_type': 'player_trend',
        'player': pname,
        'status': 'found',
        'response': response_text,
        'raw': {'current_form': form, 'rolling_trend': roll},
    }


def handle_matchup_query(question: str) -> dict:
    """Handler: how will [player] play vs [team]?"""
    team_abbrev = _extract_team_abbrev(question)
    name_candidate = _extract_player_name(question)
    pname, fact = _resolve_player(name_candidate or '')

    response_parts = []

    # Player side
    if pname and fact:
        fp = fact.get('fingerprint') or {}
        form = fact.get('current_form') or {}
        response_parts.append(f"{pname} (archetype: {fp.get('archetype', 'Unknown')}, form: {form.get('trend_tag', 'UNKNOWN')})")

        # Specific matchup history
        highlights = fact.get('matchup_highlights', [])
        if team_abbrev:
            specific = [h for h in highlights if h.get('opp') == team_abbrev]
            if specific:
                h = specific[0]
                response_parts.append(
                    f"vs {team_abbrev} specifically: max deviation {h['max_abs_z']:.2f}σ "
                    f"over {h['n_games']} games. Notable: {h['deviation_flags']}."
                )
            else:
                response_parts.append(f"No notable CV matchup history vs {team_abbrev} in atlas.")
    else:
        response_parts.append(f"Player '{name_candidate}' not found in CV atlas.")

    # Team side
    facts = _load_facts()
    if team_abbrev:
        team_fact = facts.get('teams', {}).get(team_abbrev)
        if team_fact:
            scheme = team_fact.get('defensive_scheme') or {}
            response_parts.append(
                f"{team_abbrev} defense: {scheme.get('primary_tag', 'Unknown scheme')} "
                f"({', '.join(scheme.get('all_tags', [])[:2])})."
            )
            imposed = team_fact.get('imposed_on_opponents') or {}
            top_devs = imposed.get('top_5_deviations', [])
            if top_devs:
                dev_text = ', '.join(
                    f"{d['feature']} {'+' if (d.get('z') or 0) > 0 else ''}{d.get('z', 0):.2f}σ"
                    for d in top_devs[:3]
                )
                response_parts.append(f"{team_abbrev} typically causes opponents: {dev_text}.")
        else:
            response_parts.append(f"Team {team_abbrev} not found in CV atlas.")

    # Archetype-scheme interaction
    if pname and fact and team_abbrev:
        archetype = (fact.get('fingerprint') or {}).get('archetype', '')
        team_fact = facts.get('teams', {}).get(team_abbrev, {})
        scheme_tag = (team_fact.get('defensive_scheme') or {}).get('primary_tag', '')

        asi = _load_atlas('archetype_scheme_interactions')
        if asi is not None and isinstance(asi, pd.DataFrame) and archetype and scheme_tag:
            mask = (
                (asi['archetype_name'] == archetype) &
                (asi['opp_scheme'] == scheme_tag) &
                (asi['significant'] == True)
            )
            interactions = asi[mask]
            if len(interactions) > 0:
                for _, irow in interactions.iterrows():
                    response_parts.append(
                        f"CV model: {archetype} vs {scheme_tag} — "
                        f"{irow['stat'].upper()} expected deviation: {irow['mean_dev']:.2f} "
                        f"(significant, p={irow['p_value']:.3f})."
                    )

    return {
        'query_type': 'player_matchup',
        'player': pname,
        'team': team_abbrev,
        'status': 'found' if pname else 'partial',
        'response': ' '.join(response_parts),
        'raw': {
            'matchup_highlights': (fact.get('matchup_highlights') or []) if fact else [],
        },
    }


def handle_scheme_query(question: str) -> dict:
    """Handler: what's [team]'s defensive scheme?"""
    team_abbrev = _extract_team_abbrev(question)
    if not team_abbrev:
        return {
            'query_type': 'team_scheme',
            'status': 'no_team_found',
            'message': "Could not identify a team. Try: 'What's BOS defensive scheme?'",
        }

    facts = _load_facts()
    team_fact = facts.get('teams', {}).get(team_abbrev)
    if not team_fact:
        return {
            'query_type': 'team_scheme',
            'status': 'not_found',
            'message': f"Team {team_abbrev} not found in CV atlas.",
        }

    scheme = team_fact.get('defensive_scheme') or {}
    imposed = team_fact.get('imposed_on_opponents') or {}
    affected = team_fact.get('most_affected_opponents', [])

    response_text = (
        f"{team_abbrev} plays {scheme.get('primary_tag', 'Unknown')} defense "
        f"({scheme.get('confidence', 'low')} confidence, "
        f"{scheme.get('n_opposing_player_games', 0)} player-games observed). "
        f"All schemes: {', '.join(scheme.get('all_tags', []))}. "
    )

    top_devs = imposed.get('top_5_deviations', [])
    if top_devs:
        dev_text = ', '.join(
            f"{d['feature']} {d['direction'].lower()}"
            for d in top_devs[:3]
        )
        response_text += f"Typically forces opponents to: {dev_text}. "

    if affected:
        top_aff = affected[0]
        response_text += f"Most disrupted opponent: {top_aff['player']} ({top_aff['max_abs_z']:.2f}σ)."

    return {
        'query_type': 'team_scheme',
        'team': team_abbrev,
        'status': 'found',
        'response': response_text,
        'raw': {
            'defensive_scheme': scheme,
            'imposed_on_opponents': imposed,
            'most_affected_opponents': affected[:5],
        },
    }


def handle_confidence_query(question: str) -> dict:
    """Handler: how confident should I bet [player] / Kelly multiplier."""
    name_candidate = _extract_player_name(question)
    pname, fact = _resolve_player(name_candidate or '')

    # Detect stat
    stat = None
    q = question.lower()
    for s in ['pts', 'reb', 'ast', 'fg3m', 'stl', 'blk', 'tov',
              'points', 'rebounds', 'assists', 'threes', 'steals', 'blocks', 'turnovers']:
        if s in q:
            stat_map = {'points': 'pts', 'rebounds': 'reb', 'assists': 'ast',
                        'threes': 'fg3m', 'steals': 'stl', 'blocks': 'blk', 'turnovers': 'tov'}
            stat = stat_map.get(s, s)
            break

    if fact is None:
        return {
            'query_type': 'player_confidence',
            'status': 'not_found',
            'message': f"Player not found for: '{name_candidate}'.",
        }

    conf = fact.get('confidence') or {}
    by_stat = conf.get('by_stat', {})

    if stat and stat in by_stat:
        sdata = by_stat[stat]
        response_text = (
            f"{pname} {stat.upper()}: CV={sdata.get('cv', 'N/A'):.3f}, "
            f"Kelly multiplier={sdata.get('kelly_mult', 1.0):.2f}x. "
        )
        if sdata.get('cv') and sdata['cv'] < 0.5:
            response_text += "Low variance — highly predictable."
        elif sdata.get('cv') and sdata['cv'] > 0.8:
            response_text += "High variance — bet smaller."
    else:
        overall = conf.get('overall_confidence_mult', 1.0)
        response_text = (
            f"{pname} overall Kelly multiplier: {overall:.2f}x. "
            f"CV volatility: {conf.get('cv_volatility', 'N/A')}. "
            f"Segment: {conf.get('segment', 'N/A')}. "
        )
        if by_stat:
            best_stat = min(by_stat.items(), key=lambda x: x[1].get('cv') or 99)
            response_text += f"Most predictable stat: {best_stat[0].upper()} (CV={best_stat[1].get('cv', 'N/A'):.3f})."

    return {
        'query_type': 'player_confidence',
        'player': pname,
        'stat': stat,
        'status': 'found',
        'response': response_text,
        'raw': conf,
    }


def handle_who_is_hot(question: str) -> dict:
    """Handler: who's hot / who's breaking out?"""
    facts = _load_facts()
    gt = facts.get('global_trends', {})

    hot = gt.get('active_hot', [])
    breakouts = gt.get('breakouts', [])
    generated = gt.get('generated', '')

    response_lines = [f"Active hot trends (as of {generated}):"]
    for h in hot[:5]:
        drivers = ', '.join(h.get('top_drivers', [])[:2])
        response_lines.append(
            f"  - {h['player']}: {h['tag']} (max_z={h.get('max_z', 0):.2f}, "
            f"based on {h.get('n_games_recent', 0)} recent games) — drivers: {drivers}"
        )

    if not hot and breakouts:
        response_lines = ["Season breakouts detected:"]
        for b in breakouts[:5]:
            ts = b.get('top_shift', {})
            response_lines.append(
                f"  - {b['player']}: score={b.get('score', 0):.1f}, "
                f"top shift: {ts.get('feature', '?')} ({ts.get('delta', 0):+.2f})"
            )

    if not hot and not breakouts:
        response_lines = ["No active hot-trend signals detected in current atlas."]

    return {
        'query_type': 'who_is_hot',
        'status': 'found',
        'response': '\n'.join(response_lines),
        'raw': {'active_hot': hot[:5], 'breakouts': breakouts[:5]},
    }


def handle_volatility_query(question: str) -> dict:
    """Handler: who's most volatile / riskiest bet."""
    facts = _load_facts()
    gt = facts.get('global_trends', {})
    vol = gt.get('most_volatile_players', [])

    response_lines = ["Most CV-volatile players (most anomalous games):"]
    for v in vol[:8]:
        response_lines.append(
            f"  - {v['player']}: {v['n_anomalous_games']} anomalous games, "
            f"avg_z={v.get('avg_z', 0):.2f}, max_z={v.get('max_z', 0):.2f}"
        )

    return {
        'query_type': 'who_is_volatile',
        'status': 'found',
        'response': '\n'.join(response_lines),
        'raw': {'most_volatile': vol[:8]},
    }


def handle_anomaly_query(question: str) -> dict:
    """Handler: [player]'s anomaly history."""
    name_candidate = _extract_player_name(question)
    pname, fact = _resolve_player(name_candidate or '')

    if fact is None:
        return {
            'query_type': 'player_anomaly',
            'status': 'not_found',
            'message': f"Player not found for: '{name_candidate}'.",
        }

    anom = fact.get('anomaly_history') or {}
    n = anom.get('n_anomalous_games', 0)

    if n == 0:
        response_text = f"{pname} has no anomalous CV games on record."
    else:
        response_text = (
            f"{pname} has had {n} anomalous CV games. "
            f"Max z-score: {anom.get('max_z_ever', 'N/A')}. "
            f"Most common anomalous feature: {anom.get('most_common_anomaly_feature', 'N/A')}. "
            f"Avg anomalous features/game: {anom.get('avg_anomalous_features_per_game', 'N/A')}."
        )

    return {
        'query_type': 'player_anomaly',
        'player': pname,
        'status': 'found',
        'response': response_text,
        'raw': anom,
    }


# ---------------------------------------------------------------------------
# Intent classifier + dispatcher
# ---------------------------------------------------------------------------

INTENT_PATTERNS = [
    # Global queries first (before player-specific trend patterns that share keywords)
    (["who's hot", "who is hot", "whos hot", 'hot right now', 'breaking out this',
      'season breakout', 'breakout players', r'who are.*break', r'which players.*break',
      r'who.*trending up', 'top trends', 'top cv trend'], handle_who_is_hot),
    (['most volatile', 'riskiest', 'inconsistent', 'unpredictable', 'most anomalies',
      r'who.*most volatile', r'who.*risky'], handle_volatility_query),
    # Player-specific patterns
    (['plays like', 'similar to', 'who else plays', 'comparable to', 'comp for'], handle_similarity_query),
    (['profile', 'fingerprint', 'archetype', 'cv profile', 'what type of player'], handle_profile_query),
    (['trending', 'hot or cold', 'in a streak', r"is.*breakout", 'heating up', 'cooling down',
      "what's.*form", "what is.*trend", r'is.*hot', r'is.*cold'], handle_trend_query),
    (['anomaly', 'anomalous', 'weird game', 'unusual', 'outlier', 'anomaly history'], handle_anomaly_query),
    (['confidence', 'kelly', 'reliable bet', 'how confident', 'risky bet', 'volatility', 'kelly multiplier'], handle_confidence_query),
    (['vs ', 'against ', 'matchup', 'face the', 'play.*tonight', 'how will.*play', 'how does.*do.*against'], handle_matchup_query),
    (['scheme', 'defensive', "how does.*defend", "what.*defense", "what does.*do to"], handle_scheme_query),
]


def answer_query(question: str) -> dict:
    """
    Main entry point. Parse intent from question and dispatch to handler.

    Returns a dict suitable for Claude API tool_result content.
    """
    q = question.lower().strip()

    for patterns, handler in INTENT_PATTERNS:
        for p in patterns:
            if re.search(p, q):
                return handler(question)

    # Fallback: try profile if it looks like a player name question
    words = question.split()
    if len(words) <= 4 and any(w[0].isupper() for w in words):
        return handle_profile_query(question)

    index = _load_index()
    return {
        'query_type': 'unknown',
        'status': 'unrecognized',
        'message': f"Query not recognized: '{question}'",
        'available_query_types': list(index.keys()),
        'tip': (
            "Try: 'What is [Player]'s CV profile?', "
            "'Who plays like [Player]?', "
            "'How will [Player] play vs [TEAM]?', "
            "'What's [TEAM]'s defensive scheme?', "
            "'Who's hot right now?'"
        ),
    }


# ---------------------------------------------------------------------------
# CLI demo
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    import io
    # Force UTF-8 output on Windows console
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

    DEMO_QUERIES = [
        "What's Jayson Tatum's CV profile?",
        "Who plays like Damian Lillard?",
        "Is Damian Lillard trending hot or cold?",
        "How will Tatum play vs MEM?",
        "What's BOS's defensive scheme?",
        "Who's hot right now?",
        "How confident should I bet Damian Lillard pts?",
        "What's Tatum's anomaly history?",
        "Who has the most volatile CV signal?",
    ]

    if len(sys.argv) > 1:
        queries = [' '.join(sys.argv[1:])]
    else:
        queries = DEMO_QUERIES

    print("=" * 70)
    print("CV Chat Query Handler -- Demo")
    print("=" * 70)

    for q in queries:
        print(f"\nQ: {q}")
        print("-" * 50)
        result = answer_query(q)
        response = result.get('response', '')
        if response:
            # Replace sigma to be safe
            response = response.replace('σ', 'sigma')
            print(f"A: {response}")
        else:
            print(f"Status: {result.get('status')}")
            print(f"Message: {result.get('message', str(result)[:200])}")
        print()
