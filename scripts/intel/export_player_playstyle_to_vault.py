"""
Export per-player playstyle / scheme dossiers from the synthesized profile factory
(data/cache/profiles/PLAYER_REPORTS.json) into browsable Obsidian markdown notes at
vault/Intelligence/Players/<player_id>_<slug>.md, plus a Players_Index.md MOC grouped
by team and by archetype.

Deterministic. No LLM. ~$0 per player. Idempotent / safe to re-run.

Per-player report schema (player_report/1.0): each section has a ``data`` dict (with
possibly deeply-nested sub-dicts) and a ``provenance`` dict. Thin players have mostly
nulls. We flatten ``data`` generically (so new atlas fields appear automatically) and
emit a bullet only for non-null leaves.

Existing CV cards (vault/Intelligence/Players/<id>_<slug>.md, ~135 players) are folded
in under "## CV Behavioral". Because the playstyle note is written to the same path,
we read the prior file first and recover its CV body so re-runs don't nest, and we strip
the legacy card's YAML front-matter + duplicate H1 title.

Player->team is resolved from the league game logs (most-recent game's
TEAM_ABBREVIATION per PLAYER_ID), since the profile factory carries no team field.

Run:
  set NBA_OFFLINE=1
  python scripts/intel/export_player_playstyle_to_vault.py
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, ".")

ROOT = Path(__file__).resolve().parent.parent.parent
PROFILES = ROOT / "data" / "cache" / "profiles"
PLAYERS_DIR = ROOT / "vault" / "Intelligence" / "Players"
TEAMS_DIR = ROOT / "vault" / "Intelligence" / "Teams"
INDEX_MD = ROOT / "vault" / "Intelligence" / "Players_Index.md"

REPORTS_JSON = PROFILES / "PLAYER_REPORTS.json"
PLAYER_INDEX_JSON = PROFILES / "PLAYER_INDEX.json"

GAMELOG_PARQUETS = [
    ROOT / "data" / "cache" / "cv_fix" / "leaguegamelog_regular_season.parquet",
    ROOT / "data" / "cache" / "cv_fix" / "leaguegamelog_playoffs.parquet",
    # fallbacks if a future build relocates them
    ROOT / "data" / "nba" / "leaguegamelog_regular_season.parquet",
    ROOT / "data" / "nba" / "leaguegamelog_playoffs.parquet",
]

PLAYSTYLE_MARKER = "<!-- PLAYSTYLE-EXPORT v1 -->"

# scheme-usage keys lifted into "## Scheme & Role" (and excluded from "## Scoring")
SCHEME_KEYS = (
    "pick_and_roll", "isolation", "post_up", "catch_shoot_vs_pullup",
    "spot_up", "transition", "handoff", "off_screen", "playtype",
)


# --------------------------------------------------------------------------- helpers

def slugify(name, pid) -> str:
    """Match the existing CV-card slug convention: every run of punctuation/space
    (incl. '.' and "'") becomes a single underscore, so "De'Aaron Fox" -> de_aaron_fox,
    "P.J. Washington" -> p_j_washington."""
    if not name or str(name).startswith("Player "):
        return f"player_{pid}"
    s = str(name).lower().strip()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or f"player_{pid}"


def fnum(v, nd=2):
    if isinstance(v, bool):
        return None
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        if v != v:  # NaN
            return None
        return f"{v:.{nd}f}".rstrip("0").rstrip(".")
    return None


def pretty_key(k: str) -> str:
    repl = {
        "pct": "%", "rtg": "Rtg", "pg": "per game", "reb": "reb", "oreb": "OREB",
        "dreb": "DREB", "ast": "AST", "ft": "FT", "fg": "FG", "fg3": "3PT",
        "fg3m": "3PM", "fg3a": "3PA", "pnr": "PnR", "ts": "TS", "efg": "eFG",
        "usg": "usage", "cv": "CV", "ppp": "PPP", "tov": "TOV", "stl": "STL",
        "blk": "BLK", "pf": "PF", "b2b": "B2B", "q4": "Q4", "min": "minutes",
        "2pm": "2PM", "3pm": "3PM", "and1": "and-1", "drtg": "DRtg", "gp": "games",
    }
    parts = [repl.get(p, p) for p in str(k).split("_")]
    label = " ".join(parts)
    return (label[:1].upper() + label[1:]) if label else str(k)


def fmt_val(k: str, v):
    if v is None:
        return None
    if isinstance(v, bool):
        return "yes" if v else "no"
    if isinstance(v, (int, float)):
        n = fnum(v)
        if n is None:
            return None
        fv = float(v)
        if k.endswith("_rank") and 0.0 <= fv <= 1.0:
            return f"{round(fv * 100)}th pct"
        pct_like = (
            "pct" in k or k.endswith("_pct") or "share" in k or "rate" in k
            or k in ("usage_rate", "ast_pct", "pie_mean", "oreb_rate", "dreb_rate",
                     "total_reb_rate", "freq_pct", "freq", "handler_freq",
                     "roll_man_freq", "catch_shoot_efg", "efg_pct", "fg_pct",
                     "fg3_pct", "ft_pct", "scheme_ts_spread")
        )
        if pct_like and 0.0 <= fv <= 1.0:
            return f"{fv * 100:.1f}%"
        return n
    if isinstance(v, str):
        s = v.strip()
        if not s:
            return None
        # drop atlas-builder placeholder / deferred-feature sentinels
        if s.startswith("{") and ("_note" in s or "DEFER" in s):
            return None
        if s.startswith("DEFER"):
            return None
        if s.lower() in ("(suppressed)", "suppressed", "n/a", "na", "none", "null", "nan"):
            return None
        return s
    if isinstance(v, list):
        items = [fmt_val(k, x) for x in v]
        items = [str(x) for x in items if x is not None and str(x).strip()]
        return ", ".join(items) if items else None
    return None


def walk_leaves(data, prefix=""):
    """Yield (dotted_key, leaf_value) for every non-null, non-dict leaf."""
    if isinstance(data, dict):
        for k, v in data.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, dict):
                yield from walk_leaves(v, key)
            elif isinstance(v, list):
                if v:
                    yield key, v
            elif v is not None:
                yield key, v


def bullets_from_data(data, skip_top_keys=()):
    lines = []
    for dotted, v in walk_leaves(data):
        parts = dotted.split(".")
        if parts[0] in skip_top_keys:
            continue
        leaf = parts[-1]
        if leaf.startswith("_"):  # _source / _note / _season internal keys
            continue
        rendered = fmt_val(leaf, v)
        if rendered is None or rendered == "":
            continue
        label = pretty_key(leaf)
        if len(parts) > 1:
            ctx = pretty_key(parts[-2])
            if ctx.lower() not in label.lower():
                label = f"{ctx} — {label}"
        lines.append(f"- **{label}:** {rendered}")
    return lines


# --------------------------------------------------------------------------- CV folding

def _strip_frontmatter_and_h1(text: str) -> str:
    """Remove a leading YAML front-matter block and a single leading H1 title."""
    if text.lstrip().startswith("---"):
        m = re.match(r"\s*---\s*\n.*?\n---\s*\n", text, re.S)
        if m:
            text = text[m.end():]
    lines = text.splitlines()
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and lines[0].lstrip().startswith("# "):
        lines = lines[1:]
    return "\n".join(lines).strip()


def extract_cv_body(path: Path):
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8")
    except Exception:
        return None
    if not raw.strip():
        return None
    if PLAYSTYLE_MARKER in raw:
        # our own prior export: recover just the CV Behavioral section, and still
        # strip any YAML/H1 that an earlier (pre-fix) run may have folded in.
        m = re.search(r"\n## CV Behavioral\s*\n(.*?)(?:\n## |\Z)", raw, re.S)
        if m:
            body = _strip_frontmatter_and_h1(m.group(1).strip())
            if body and "CV pending" not in body:
                return body
        return None
    # legacy CV-only card: strip YAML front-matter + leading H1, keep the rest
    body = _strip_frontmatter_and_h1(raw)
    return body or None


# --------------------------------------------------------------------------- team map

def valid_team_tris():
    tris = set()
    if TEAMS_DIR.exists():
        for f in TEAMS_DIR.glob("*.md"):
            tris.add(f.stem.upper())
    return tris


def build_gamelog_team_map(valid_tris):
    """player_id(str) -> tri-code, from the most-recent game in the league game logs."""
    try:
        import pandas as pd
    except Exception:
        return {}, {}
    frames = []
    for p in GAMELOG_PARQUETS:
        if p.exists():
            try:
                frames.append(pd.read_parquet(
                    p, columns=["PLAYER_ID", "TEAM_ABBREVIATION", "TEAM_NAME", "GAME_DATE"]))
            except Exception:
                pass
    if not frames:
        return {}, {}
    df = pd.concat(frames, ignore_index=True)
    df = df.dropna(subset=["PLAYER_ID", "TEAM_ABBREVIATION"])
    df["GAME_DATE"] = df["GAME_DATE"].astype(str)
    df = df.sort_values("GAME_DATE").drop_duplicates("PLAYER_ID", keep="last")
    tri_map, name_map = {}, {}
    for _, r in df.iterrows():
        pid = str(int(r["PLAYER_ID"]))
        tri = str(r["TEAM_ABBREVIATION"]).upper().strip()
        tri_map[pid] = tri if (not valid_tris or tri in valid_tris) else None
        name_map[pid] = str(r.get("TEAM_NAME") or "").strip() or None
    return tri_map, name_map


# --------------------------------------------------------------------------- accessors

def get_name(report, idx_name):
    return (report.get("player_name") or "").strip() or idx_name or f"Player {report.get('player_id')}"


def get_archetype(report):
    ar = (report.get("archetype_role", {}) or {}).get("data", {}) or {}
    arch = ar.get("archetype") or {}
    if isinstance(arch, dict):
        return arch.get("label") or "Role Player", arch.get("secondary"), arch.get("tags") or []
    if isinstance(arch, str):
        return arch, None, []
    return "Role Player", None, []


# --------------------------------------------------------------------------- note builder

def build_note(report, team_info, valid_tris, idx_name, cv_body):
    pid = report.get("player_id")
    name = get_name(report, idx_name)
    arch_label, arch_secondary, arch_tags = get_archetype(report)
    tri = (team_info or {}).get("tri")
    team_name = (team_info or {}).get("team_name")

    L = [PLAYSTYLE_MARKER, f"# {name}"]
    head = []
    if tri and tri in valid_tris:
        head.append(f"**Team:** [[{tri}]]")
    elif team_name:
        head.append(f"**Team:** {team_name}")
    head.append(f"**Archetype:** {arch_label}")
    if arch_secondary:
        head.append(f"*(secondary: {arch_secondary})*")
    L.append(" · ".join(head))
    if arch_tags:
        L += ["", "Tags: " + ", ".join(f"`{t}`" for t in arch_tags)]
    dc = report.get("data_completeness", {}) or {}
    if dc:
        L += ["", (f"> Data completeness: {dc.get('sections_present', '?')}/"
                   f"{dc.get('sections_total', '?')} sections (score {dc.get('score', '?')}). "
                   f"Generated {report.get('generated_at') or report.get('as_of')}.")]
    L.append("")

    scoring = (report.get("scoring", {}) or {}).get("data", {}) or {}

    # ---- Scheme & Role
    L.append("## Scheme & Role")
    role_b = bullets_from_data((report.get("archetype_role", {}) or {}).get("data", {}) or {},
                               skip_top_keys=("archetype",))
    scheme_b = []
    for k in SCHEME_KEYS:
        if k in scoring:
            scheme_b += bullets_from_data({k: scoring[k]})
    L += role_b
    if scheme_b:
        L += ["", "**Scheme usage:**"] + scheme_b
    if not role_b and not scheme_b:
        L.append("_No role/scheme usage data on file._")
    L.append("")

    # ---- Scoring (everything except the scheme keys already shown)
    L.append("## Scoring")
    scoring_b = bullets_from_data(scoring, skip_top_keys=SCHEME_KEYS)
    L += scoring_b if scoring_b else ["_No scoring/shot-zone data on file._"]
    L.append("")

    # ---- Playmaking
    L.append("## Playmaking")
    pmb = bullets_from_data((report.get("playmaking", {}) or {}).get("data", {}) or {})
    L += pmb if pmb else ["_No playmaking data on file._"]
    L.append("")

    # ---- Rebounding
    L.append("## Rebounding")
    rbb = bullets_from_data((report.get("rebounding", {}) or {}).get("data", {}) or {})
    L += rbb if rbb else ["_No rebounding data on file._"]
    L.append("")

    # ---- Defense (incl. how they're guarded if a matchup section exists)
    L.append("## Defense")
    dfb = bullets_from_data((report.get("defense", {}) or {}).get("data", {}) or {})
    L += dfb if dfb else ["_No defensive data on file._"]
    matchup = (report.get("matchup", {}) or {}).get("data", {}) if isinstance(report.get("matchup"), dict) else {}
    mb = bullets_from_data(matchup) if matchup else []
    if mb:
        L += ["", "**How they're guarded / matchups:**"] + mb
    L.append("")

    # ---- Situational
    L.append("## Situational")
    sitb = (bullets_from_data((report.get("situational", {}) or {}).get("data", {}) or {})
            + bullets_from_data((report.get("consistency_durability", {}) or {}).get("data", {}) or {}))
    L += sitb if sitb else ["_No clutch / fatigue / rest / vs-scheme / form data on file._"]
    L.append("")

    # ---- Strengths & Weaknesses (percentile table)
    L.append("## Strengths & Weaknesses")
    sw = report.get("strengths_weaknesses", {}) or {}
    ranked = sw.get("ranked") or []
    if ranked:
        L += ["| Metric | Percentile | Value |", "|---|---|---|"]
        for r in ranked[:25]:
            if not isinstance(r, dict):
                continue
            metric = r.get("label") or pretty_key(str(r.get("metric") or "?"))
            pctl = r.get("percentile", r.get("rank"))
            if isinstance(pctl, (int, float)):
                pctl = f"{round(pctl)}th" if pctl > 1 else f"{round(pctl * 100)}th"
            val = r.get("value")
            val = fnum(val) if isinstance(val, (int, float)) else (val if val is not None else "")
            L.append(f"| {metric} | {pctl if pctl is not None else '—'} | {val} |")
    else:
        L.append("_No ranked strengths/weaknesses on file._")
    L.append("")

    # ---- How <player> plays
    short = name.split()[0] if name and not name.startswith("Player ") else name
    L.append(f"## How {short} plays")
    nar = (report.get("narrative") or "").strip()
    L.append(nar if nar else "_Summary pending more data._")
    L.append("")

    # ---- CV Behavioral
    L.append("## CV Behavioral")
    L.append(cv_body if cv_body else
             "_CV pending — no broadcast-tracking card for this player yet._")
    L.append("")

    return name, slugify(name, pid), arch_label, tri, "\n".join(L).rstrip() + "\n"


# --------------------------------------------------------------------------- index MOC

def make_headline(report, arch_label):
    """One-line headline: archetype + the player's top strength (human label)."""
    sw = report.get("strengths_weaknesses", {}) or {}
    tendency = None
    strengths = sw.get("strengths") or []
    if strengths and isinstance(strengths[0], dict):
        tendency = strengths[0].get("label") or pretty_key(str(strengths[0].get("metric") or ""))
    elif strengths and isinstance(strengths[0], str):
        tendency = pretty_key(strengths[0]) if "_" in strengths[0] else strengths[0]
    if not tendency:
        ranked = sw.get("ranked") or []
        if ranked and isinstance(ranked[0], dict):
            tendency = ranked[0].get("label") or pretty_key(str(ranked[0].get("metric") or ""))
    return arch_label + (f"; {tendency}" if tendency else "")


def write_index(rows, valid_tris):
    cv_n = sum(1 for r in rows if r.get("has_cv"))
    L = ["<!-- PLAYSTYLE-INDEX v2 -->", "# Players Index (Playstyle / Scheme MOC)", ""]
    L.append(f"The single index of all **{len(rows)}** current-season player dossiers "
             f"({cv_n} with folded-in broadcast CV data — marked `[CV]`), grouped by team and "
             "by archetype. Each note covers scheme & role, scoring, playmaking, rebounding, "
             "defense, situational splits, strengths/weaknesses, a deterministic how-they-play "
             "summary, and folded-in CV behavioral data.")
    L.append("")

    def _line(r):
        cv = " `[CV]`" if r.get("has_cv") else ""
        return f"- [[{r['slug_full']}|{r['name']}]]{cv} — {r['headline']}"

    L += ["## By Team", ""]
    by_team, no_team = {}, []
    for r in rows:
        if r["tri"] and r["tri"] in valid_tris:
            by_team.setdefault(r["tri"], []).append(r)
        else:
            no_team.append(r)
    for tri in sorted(by_team):
        L.append(f"### [[{tri}]]")
        for r in sorted(by_team[tri], key=lambda x: (-x["completeness"], x["name"])):
            L.append(_line(r))
        L.append("")
    if no_team:
        L.append("### (Team unmapped — free agents / inactive)")
        for r in sorted(no_team, key=lambda x: x["name"]):
            L.append(_line(r))
        L.append("")

    L += ["## By Archetype", ""]
    by_arch = {}
    for r in rows:
        by_arch.setdefault(r["archetype"] or "Role Player", []).append(r)
    for arch in sorted(by_arch):
        L.append(f"### {arch}")
        for r in sorted(by_arch[arch], key=lambda x: (-x["completeness"], x["name"])):
            tri = f" ({r['tri']})" if r["tri"] else ""
            cv = " `[CV]`" if r.get("has_cv") else ""
            L.append(f"- [[{r['slug_full']}|{r['name']}]]{tri}{cv} — {r['headline']}")
        L.append("")

    INDEX_MD.write_text("\n".join(L).rstrip() + "\n", encoding="utf-8")


ROSTER_START = "<!-- ROSTER-AUTO START -->"
ROSTER_END = "<!-- ROSTER-AUTO END -->"


def write_rosters(rows, valid_tris):
    """Refresh the auto roster block in each Teams/<TRI>.md from the current-season
    dossiers, so team notes list exactly their active players (graph nests players
    under teams via these links)."""
    by_team = {}
    for r in rows:
        if r["tri"] and r["tri"] in valid_tris:
            by_team.setdefault(r["tri"], []).append(r)
    updated = 0
    for tri, players in by_team.items():
        tf = TEAMS_DIR / f"{tri}.md"
        if not tf.exists():
            continue
        players = sorted(players, key=lambda x: x["name"])
        block = [ROSTER_START, "", f"## Roster ({len(players)} players)", ""]
        block += [f"- [[{p['slug_full']}|{p['name']}]] — _{p['archetype']}_" for p in players]
        block += ["", ROSTER_END]
        block_txt = "\n".join(block)
        txt = tf.read_text(encoding="utf-8")
        if ROSTER_START in txt and ROSTER_END in txt:
            txt = re.sub(re.escape(ROSTER_START) + r".*?" + re.escape(ROSTER_END),
                         block_txt, txt, flags=re.S)
        else:
            txt = txt.rstrip() + "\n\n" + block_txt + "\n"
        tf.write_text(txt, encoding="utf-8")
        updated += 1
    return updated


# --------------------------------------------------------------------------- main

def main():
    os.environ.setdefault("NBA_OFFLINE", "1")
    reports = json.loads(REPORTS_JSON.read_text(encoding="utf-8"))
    player_index = json.loads(PLAYER_INDEX_JSON.read_text(encoding="utf-8")) if PLAYER_INDEX_JSON.exists() else {}

    valid_tris = valid_team_tris()
    gl_tri, gl_name = build_gamelog_team_map(valid_tris)

    idx_name = {}
    pl = (player_index or {}).get("players") or []
    if isinstance(pl, list):
        for rec in pl:
            if isinstance(rec, dict):
                idx_name[str(rec.get("player_id"))] = rec.get("name")
    elif isinstance(pl, dict):
        for k, rec in pl.items():
            idx_name[str(k)] = (rec or {}).get("name")

    PLAYERS_DIR.mkdir(parents=True, exist_ok=True)

    written = cv_folded = thin = skipped_no_game = 0
    rows = []
    written_paths = set()

    # Current-season player set: only players with at least one game in the league
    # game logs get a dossier. Players absent from the logs (retired / out-of-league
    # historical pool) are skipped so the index/rosters reflect the active season.
    current_player_ids = set(gl_tri.keys()) | set(gl_name.keys())

    for pid, report in reports.items():
        if not isinstance(report, dict):
            continue
        spid = str(pid)
        if current_player_ids and spid not in current_player_ids:
            skipped_no_game += 1
            continue
        team_info = {"tri": gl_tri.get(spid), "team_name": gl_name.get(spid)}

        name0 = get_name(report, idx_name.get(spid))
        note_path = PLAYERS_DIR / f"{pid}_{slugify(name0, pid)}.md"
        cv_body = extract_cv_body(note_path)
        if cv_body:
            cv_folded += 1

        name, slug, arch_label, tri, content = build_note(
            report, team_info, valid_tris, idx_name.get(spid), cv_body)
        out_path = PLAYERS_DIR / f"{pid}_{slug}.md"
        out_path.write_text(content, encoding="utf-8")
        written_paths.add(out_path.name)
        written += 1

        dc = report.get("data_completeness", {}) or {}
        if (dc.get("sections_present") or 0) <= 3:
            thin += 1
        comp = dc.get("score") or 0
        rows.append({
            "pid": pid, "name": name, "slug_full": f"{pid}_{slug}",
            "archetype": arch_label, "tri": tri,
            "completeness": comp if isinstance(comp, (int, float)) else 0,
            "headline": make_headline(report, arch_label),
            "has_cv": bool(cv_body),
        })

    # Prune stale dossiers: any note we didn't write this run (player no longer in the
    # current-season pool) is removed so Players/ stays current-season-only.
    pruned = 0
    for f in PLAYERS_DIR.glob("*.md"):
        if f.name not in written_paths:
            try:
                f.unlink()
                pruned += 1
            except Exception:
                pass

    write_index(rows, valid_tris)
    rosters_updated = write_rosters(rows, valid_tris)

    summary = {
        "players_written": written,
        "stale_dossiers_pruned": pruned,
        "skipped_no_current_season_game": skipped_no_game,
        "cv_cards_folded_in": cv_folded,
        "thin_players_3_or_fewer_sections": thin,
        "team_rosters_updated": rosters_updated,
        "teams_mapped": len({r["tri"] for r in rows if r["tri"]}),
        "index_path": str(INDEX_MD),
        "players_dir": str(PLAYERS_DIR),
    }
    (Path(__file__).resolve().parent / "EXPORT_SUMMARY.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return summary, written_paths


if __name__ == "__main__":
    main()
