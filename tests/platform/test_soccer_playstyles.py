"""tests.platform.test_soccer_playstyles — Acceptance tests for domains.soccer.atlas_playstyles.

Synthetic corpus fixture covers all seven scheme branches deterministically.
No real parquet I/O required.

Tests
-----
- build returns non-empty list
- index note exists with frontmatter, wikilinks, and tags
- index links up to [[_Index]] (soccer atlas root)
- at least one scheme note emitted
- each scheme note has YAML frontmatter, [[Teams/]] wikilinks, and #tags
- hand-checked classification: clear High-Scoring Attacking team goes to that scheme
- hand-checked classification: clear Defensive Low-Block team goes to that scheme
- index lists all 7 scheme keys / labels
- idempotent second run returns same count
- missing corpus raises FileNotFoundError
- scheme notes contain stat-signature text
- team_count frontmatter value matches actual team list length
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import List

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from domains.soccer.atlas_playstyles import build_playstyles, _SCHEMES  # noqa: E402


# ---------------------------------------------------------------------------
# Synthetic corpus builder
# ---------------------------------------------------------------------------

def _make_corpus(tmp_path: Path) -> Path:
    """Build a minimal matches.parquet covering all scheme branches."""
    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()

    rows: List[dict] = []
    eid = 1

    def _add(home: str, away: str, hg: int, ag: int, n_rep: int = 10) -> None:
        nonlocal eid
        total = hg + ag
        ftr = "H" if hg > ag else ("A" if ag > hg else "D")
        for i in range(n_rep):
            rows.append({
                "event_id": f"ev{eid}",
                "date": f"2023-08-{(i % 28) + 1:02d}",
                "season": 2023,
                "div": "E0",
                "home_team": home,
                "away_team": away,
                "fthg": hg,
                "ftag": ag,
                "total_goals": total,
                "target_over25": 1 if total >= 3 else 0,
                "ftr": ftr,
            })
            eid += 1

    # --- High-Scoring Attacking (GF/game ≥ 1.60, Over ≥ 58%) ---
    # "Super FC" scores 3-1 at home and away in every match => GF/game=3.0, over=100%
    _add("Super FC", "Foe1", 3, 1, n_rep=18)  # home: gf=3, ga=1
    _add("Foe1", "Super FC", 1, 3, n_rep=18)  # away: gf=3, ga=1

    # --- Defensive Low-Block (GA ≤ 1.15, CS ≥ 31%, Over ≤ 49%) ---
    # "Iron Wall" concedes 0-1 goals; nearly all clean sheets
    _add("Iron Wall", "Foe2", 1, 0, n_rep=20)  # 1-0 home wins => cs=100%, over=0%
    _add("Foe2", "Iron Wall", 0, 1, n_rep=16)  # away 0-1 => cs=100%

    # --- High-Variance Entertainers (BTTS ≥ 60%, Over ≥ 58%) ---
    # "Chaos United": 2-2 in most games => BTTS=100%, over=100%, but GF/game=2 (<1.6 avg)
    # Actually 2-2 => GF=2, let's ensure GF < 1.6 to avoid High-Scoring branch first
    # We need GF < 1.60 but over >= 0.58 and btts >= 0.60
    # 1-2 scores: GF=1, GA=2 home; away 2-1 => total 3 goals, over, btts
    _add("Chaos United", "Foe3", 2, 2, n_rep=20)  # 2-2: btts, over; gf=2 → will hit HiSco first
    # Let's craft this carefully: average GF needs to be < 1.60 with btts+over
    # Use mix: 20× 1-2 (btts, over, GF=1) + 16× 2-1 (btts, over, GF=2)
    # That gives avg GF = (20*1 + 16*2)/(36+36) = 52/72 home... let's just pick a team
    # that ends up in HiVariance slot: BTTS>=60 and Over>=58 but GF<1.60
    # "Thrill FC": home 2-2 (10×) + away loss 1-2 (10×) + away 1-2 (16×)
    # GF = (20+10+16)/... let's compute after. Use simpler: all 1-2 results:
    # GF home=1, GF away=2, GA home=2, GA away=1 → GF/game=1.5, over=100%, btts=100%
    _add("Thrill FC", "Foe4", 1, 2, n_rep=20)  # home 1-2 (loss): gf=1,ga=2, btts, over
    _add("Foe4", "Thrill FC", 1, 2, n_rep=16)  # away 2-1 (win): gf=2,ga=1, btts, over
    # GF = (20*1 + 16*2) / 36 = 52/36 = 1.44 => < 1.60, over=100%, btts=100% ✓

    # --- Draw-Prone Grinder (draw_pct ≥ 30%) ---
    # "Draw FC": 22/36 draws => 61% draw rate
    _add("Draw FC", "Foe5", 1, 1, n_rep=22)   # all 1-1 draws
    _add("Foe5", "Draw FC", 1, 1, n_rep=14)

    # --- Leaky / High-Risk (GA ≥ 1.80, CS ≤ 18%) ---
    # "Porous City": concedes 3+ every game
    _add("Porous City", "Foe6", 1, 3, n_rep=18)  # home: ga=3, cs=0
    _add("Foe6", "Porous City", 3, 1, n_rep=18)  # away: ga=3, cs=0

    # --- Strong at Home (home_adv ≥ 0.50) ---
    # "Fortress Town": scores 3 at home, 0 away
    _add("Fortress Town", "Foe7", 3, 1, n_rep=20)  # home gf=3
    _add("Foe7", "Fortress Town", 2, 0, n_rep=16)  # away gf=0
    # home_adv = 3 - 0 = 3.0 ✓; GF/game = (60+0)/36 = 1.67 → would hit High-Scoring first
    # Lower home scoring: 2-1 home, 0-2 away => home_gf=2, away_gf=0, GF/game=40/36=1.11
    # → over 3/36 = 8% → won't be High-Scoring or HiVariance or Defensive or Draw-Prone or Leaky
    # Let's use: 2-1 home x20, 0-2 away x16 => GF/g = (40+0)/36=1.11, GA/g=(20+32)/36=1.44
    # over: (0+16)/36=44%, cs: (0+0)/36=0 ... 0 CS from home 2-1 but away gets 0-2 (cs if 0 scored?)
    # Actually cs = home ftag==0 (away score==0) + away fthg==0 (home score when away)
    # home 2-1: ftag=1 => no cs; away 0-2: fthg=0 => THEY score 0 → cs for Fortress
    # So cs_pct = 16/36=44%, over_pct = 44%... could hit Defensive if GA low enough
    # GA/g = (20+32)/36=1.44 > 1.15 → won't hit Defensive ✓
    # draw_pct = 0 → won't hit Draw-Prone ✓; leaky: GA=1.44 < 1.80 → no ✓
    # So it falls to Strong-at-Home: home_adv = 2-0 = 2.0 ≥ 0.50 ✓
    # Re-create Fortress Town with corrected fixture:
    rows_fortress = [r for r in rows if r["home_team"] not in ("Fortress Town", "Foe7")
                     and r["away_team"] not in ("Fortress Town", "Foe7")]
    rows = rows_fortress
    for i in range(20):
        rows.append({
            "event_id": f"ft_h_{i}", "date": "2023-09-01", "season": 2023,
            "div": "E0", "home_team": "Fortress Town", "away_team": "Foe7",
            "fthg": 2, "ftag": 1, "total_goals": 3, "target_over25": 1, "ftr": "H",
        })
    for i in range(16):
        rows.append({
            "event_id": f"ft_a_{i}", "date": "2023-10-01", "season": 2023,
            "div": "E0", "home_team": "Foe7", "away_team": "Fortress Town",
            "fthg": 2, "ftag": 0, "total_goals": 2, "target_over25": 0, "ftr": "H",
        })

    # --- Balanced (falls through all other rules) ---
    # "Mid Table SC": GF=1.2, GA=1.4, over=50%, btts=50%, draw=25% — all median
    _add("Mid Table SC", "FoeB1", 1, 1, n_rep=9)   # draw
    _add("FoeB1", "Mid Table SC", 1, 1, n_rep=9)
    _add("Mid Table SC", "FoeB2", 2, 1, n_rep=10)  # win
    _add("FoeB2", "Mid Table SC", 1, 2, n_rep=8)
    _add("Mid Table SC", "FoeB3", 0, 1, n_rep=5)   # loss

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df.to_parquet(corpus_dir / "matches.parquet", index=False)
    return corpus_dir


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _has_frontmatter(text: str) -> bool:
    lines = text.splitlines()
    return len(lines) >= 3 and lines[0].strip() == "---"


def _has_wikilink(text: str) -> bool:
    return bool(re.search(r"\[\[.*?\]\]", text))


def _has_tag(text: str) -> bool:
    return bool(re.search(r"#[\w/\-]+", text))


def _scheme_notes(paths: List[Path]) -> List[Path]:
    return [p for p in paths if p.name != "_Playstyles_Index.md"]


def _index_text(out: Path) -> str:
    return (out / "_Playstyles_Index.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_returns_nonempty(tmp_path: Path) -> None:
    paths = build_playstyles(tmp_path / "out", _make_corpus(tmp_path))
    assert len(paths) > 0


def test_index_exists_with_frontmatter(tmp_path: Path) -> None:
    out = tmp_path / "out"
    build_playstyles(out, _make_corpus(tmp_path))
    text = _index_text(out)
    assert _has_frontmatter(text), "Index missing YAML frontmatter"


def test_index_has_wikilinks(tmp_path: Path) -> None:
    out = tmp_path / "out"
    build_playstyles(out, _make_corpus(tmp_path))
    assert _has_wikilink(_index_text(out)), "Index missing [[wikilinks]]"


def test_index_has_tags(tmp_path: Path) -> None:
    out = tmp_path / "out"
    build_playstyles(out, _make_corpus(tmp_path))
    assert _has_tag(_index_text(out)), "Index missing #tags"


def test_index_links_up_to_soccer_index(tmp_path: Path) -> None:
    out = tmp_path / "out"
    build_playstyles(out, _make_corpus(tmp_path))
    assert "[[_Index" in _index_text(out), "Index missing up-link to [[_Index]]"


def test_at_least_one_scheme_note(tmp_path: Path) -> None:
    paths = build_playstyles(tmp_path / "out", _make_corpus(tmp_path))
    assert len(_scheme_notes(paths)) >= 1


def test_scheme_notes_have_frontmatter_and_tags(tmp_path: Path) -> None:
    paths = build_playstyles(tmp_path / "out", _make_corpus(tmp_path))
    for p in _scheme_notes(paths):
        text = p.read_text(encoding="utf-8")
        assert _has_frontmatter(text), f"{p.name} missing frontmatter"
        assert _has_tag(text), f"{p.name} missing #tags"


def test_scheme_notes_have_teams_wikilinks(tmp_path: Path) -> None:
    """Every scheme note with teams must contain [[Teams/...]] links."""
    paths = build_playstyles(tmp_path / "out", _make_corpus(tmp_path))
    for p in _scheme_notes(paths):
        text = p.read_text(encoding="utf-8")
        if "team_count: 0" not in text:
            assert "[[Teams/" in text, f"{p.name} missing [[Teams/]] wikilinks"


def test_high_scoring_classification(tmp_path: Path) -> None:
    """Super FC (GF≥3/game, Over=100%) must appear in High-Scoring Attacking note."""
    out = tmp_path / "out"
    build_playstyles(out, _make_corpus(tmp_path))
    note = (out / "High-Scoring_Attacking.md").read_text(encoding="utf-8")
    assert "Super FC" in note, "Super FC should classify as High-Scoring Attacking"


def test_defensive_low_block_classification(tmp_path: Path) -> None:
    """Iron Wall (GA≤1.0, CS=100%, Over=0%) must appear in Defensive Low-Block note."""
    out = tmp_path / "out"
    build_playstyles(out, _make_corpus(tmp_path))
    note = (out / "Defensive_Low-Block.md").read_text(encoding="utf-8")
    assert "Iron Wall" in note, "Iron Wall should classify as Defensive Low-Block"


def test_index_lists_all_seven_schemes(tmp_path: Path) -> None:
    """Index must reference all 7 scheme labels."""
    out = tmp_path / "out"
    build_playstyles(out, _make_corpus(tmp_path))
    text = _index_text(out)
    for spec in _SCHEMES:
        assert spec.label in text, f"Scheme '{spec.label}' not found in index"


def test_all_seven_scheme_files_created(tmp_path: Path) -> None:
    paths = build_playstyles(tmp_path / "out", _make_corpus(tmp_path))
    scheme_files = {p.name for p in _scheme_notes(paths)}
    expected = {f"{spec.key}.md" for spec in _SCHEMES}
    assert expected == scheme_files, f"Missing scheme files: {expected - scheme_files}"


def test_team_count_frontmatter_matches_list(tmp_path: Path) -> None:
    """team_count: N in frontmatter must equal actual wikilink count per note."""
    paths = build_playstyles(tmp_path / "out", _make_corpus(tmp_path))
    for p in _scheme_notes(paths):
        text = p.read_text(encoding="utf-8")
        m_count = re.search(r"team_count:\s*(\d+)", text)
        assert m_count, f"{p.name} missing team_count frontmatter"
        declared = int(m_count.group(1))
        links = re.findall(r"\[\[Teams/[^\]]+\]\]", text)
        assert declared == len(links), (
            f"{p.name}: team_count={declared} but found {len(links)} [[Teams/]] links"
        )


def test_scheme_note_contains_signature(tmp_path: Path) -> None:
    """Each scheme note must contain its classification rule / stat signature."""
    out = tmp_path / "out"
    build_playstyles(out, _make_corpus(tmp_path))
    for spec in _SCHEMES:
        text = (out / f"{spec.key}.md").read_text(encoding="utf-8")
        # signature text appears verbatim in the note
        assert spec.signature[:20] in text, (
            f"{spec.key}.md missing stat signature"
        )


def test_idempotent(tmp_path: Path) -> None:
    corpus = _make_corpus(tmp_path)
    out = tmp_path / "out"
    assert len(build_playstyles(out, corpus)) == len(build_playstyles(out, corpus))


def test_missing_corpus_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        build_playstyles(tmp_path / "out", tmp_path / "no_such_dir")
