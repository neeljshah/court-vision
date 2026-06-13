"""tests/platform/test_obsidian_emit.py — Known-value unit tests for obsidian_emit.

Covers: slug edge cases, frontmatter format, md_table format, write_note idempotency.
All tests are offline (no network, no GPU, no corpus files).

Run: python -m pytest tests/platform/test_obsidian_emit.py -q --timeout=30
"""
from __future__ import annotations

import pathlib

import pytest

from scripts.platformkit.atlas.obsidian_emit import (
    frontmatter,
    md_table,
    slug,
    write_note,
)


# ---------------------------------------------------------------------------
# slug — matches the atlas.py _slug() behavior exactly
# ---------------------------------------------------------------------------

class TestSlug:
    def test_plain_name(self) -> None:
        assert slug("Roger Federer") == "Roger_Federer"

    def test_trailing_leading_spaces(self) -> None:
        assert slug("  spaces  ") == "spaces"

    def test_apostrophe_stripped(self) -> None:
        assert slug("O'Brien") == "OBrien"

    def test_exclamation_stripped(self) -> None:
        assert "!" not in slug("Hello!")

    def test_hyphen_preserved(self) -> None:
        assert slug("Jean-Pierre") == "Jean-Pierre"

    def test_multiple_spaces_collapsed(self) -> None:
        assert slug("a  b   c") == "a_b_c"

    def test_empty_string(self) -> None:
        assert slug("") == ""

    def test_only_special_chars(self) -> None:
        assert slug("!!!") == ""

    def test_numbers_and_word_chars(self) -> None:
        assert slug("ATP 2025!") == "ATP_2025"

    def test_tab_as_whitespace(self) -> None:
        assert slug("a\tb") == "a_b"

    def test_matches_old_atlas_behavior(self) -> None:
        """slug() must produce identical output to the original _slug() regex pair."""
        import re
        _SLUG_RE = re.compile(r"[^\w\s-]")
        _SPACE_RE = re.compile(r"[\s]+")

        def _old_slug(name: str) -> str:
            s = _SLUG_RE.sub("", name).strip()
            return _SPACE_RE.sub("_", s)

        for name in ["Roger Federer", "O'Brien", "ATP 2025!", "  spaces  ", "Jean-Pierre", ""]:
            assert slug(name) == _old_slug(name), f"slug mismatch for {name!r}"


# ---------------------------------------------------------------------------
# frontmatter
# ---------------------------------------------------------------------------

class TestFrontmatter:
    def test_basic_scalars(self) -> None:
        result = frontmatter({"surface": "Hard", "total_matches": 20})
        assert result == "---\nsurface: Hard\ntotal_matches: 20\n---"

    def test_list_value(self) -> None:
        result = frontmatter({"tags": ["sport/tennis", "atlas/index"]})
        assert result == "---\ntags:\n  - sport/tennis\n  - atlas/index\n---"

    def test_pre_quoted_value(self) -> None:
        result = frontmatter({"corpus_span": '"2022-01-07 → 2022-06-15"'})
        assert 'corpus_span: "2022-01-07 → 2022-06-15"' in result

    def test_starts_and_ends_with_dashes(self) -> None:
        result = frontmatter({"k": "v"})
        assert result.startswith("---") and result.endswith("---")

    def test_empty_dict(self) -> None:
        assert frontmatter({}) == "---\n---"

    def test_order_preserved(self) -> None:
        result = frontmatter({"a": 1, "b": 2, "c": 3})
        lines = result.split("\n")
        assert lines.index("a: 1") < lines.index("b: 2") < lines.index("c: 3")

    def test_index_frontmatter_matches_atlas_format(self) -> None:
        """Reproduce the exact _Index.md frontmatter from atlas_render."""
        result = frontmatter({
            "corpus": "ATP 2015–2025",
            "total_matches": 60,
            "corpus_span": '"2022-01-07 → 2022-06-15"',
            "featured_players": 7,
            "tags": ["sport/tennis", "atlas/index"],
        })
        assert "corpus: ATP 2015–2025" in result
        assert "total_matches: 60" in result
        assert "  - sport/tennis" in result
        assert "  - atlas/index" in result

    def test_surface_frontmatter_matches_atlas_format(self) -> None:
        result = frontmatter({
            "surface": "Hard",
            "total_matches": 20,
            "corpus_share_pct": 33.3,
            "tags": ["sport/tennis", "surface/hard"],
        })
        assert "surface: Hard" in result
        assert "corpus_share_pct: 33.3" in result
        assert "  - surface/hard" in result


# ---------------------------------------------------------------------------
# write_note
# ---------------------------------------------------------------------------

class TestWriteNote:
    def test_creates_file_with_content(self, tmp_path: pathlib.Path) -> None:
        p = tmp_path / "note.md"
        result = write_note(p, "# Hello\n")
        assert result == p and p.exists()
        assert p.read_text(encoding="utf-8") == "# Hello\n"

    def test_creates_parent_dirs(self, tmp_path: pathlib.Path) -> None:
        p = tmp_path / "deep" / "dir" / "note.md"
        write_note(p, "body\n")
        assert p.exists()

    def test_idempotent_overwrite(self, tmp_path: pathlib.Path) -> None:
        """Second call with different content overwrites (not appends)."""
        p = tmp_path / "note.md"
        write_note(p, "first\n")
        write_note(p, "second\n")
        assert p.read_text(encoding="utf-8") == "second\n"

    def test_accepts_str_path(self, tmp_path: pathlib.Path) -> None:
        p = tmp_path / "str_path.md"
        write_note(str(p), "content\n")
        assert p.exists()

    def test_utf8_encoding(self, tmp_path: pathlib.Path) -> None:
        p = tmp_path / "utf8.md"
        body = "Elo: 2100–present\n"
        write_note(p, body)
        assert p.read_text(encoding="utf-8") == body

    def test_returns_path_object(self, tmp_path: pathlib.Path) -> None:
        result = write_note(tmp_path / "n.md", "x\n")
        assert isinstance(result, pathlib.Path)


# ---------------------------------------------------------------------------
# md_table
# ---------------------------------------------------------------------------

class TestMdTable:
    def test_basic_table(self) -> None:
        result = md_table(["Name", "Elo"], [["Djokovic", 2100], ["Alcaraz", 2050]])
        lines = result.split("\n")
        assert lines[0] == "| Name | Elo |"
        assert "-" in lines[1]
        assert "Djokovic" in lines[2] and "2100" in lines[2]

    def test_no_trailing_newline(self) -> None:
        assert not md_table(["H"], [["v"]]).endswith("\n")

    def test_empty_rows(self) -> None:
        lines = md_table(["Col"], []).split("\n")
        assert len(lines) == 2  # header + separator only

    def test_values_stringified(self) -> None:
        result = md_table(["N"], [[42], [3.14], [None]])
        assert "42" in result and "3.14" in result and "None" in result

    def test_row_count(self) -> None:
        lines = md_table(["H"], [["r1"], ["r2"], ["r3"]]).split("\n")
        assert len(lines) == 5  # header + sep + 3 rows

    def test_multiple_columns(self) -> None:
        result = md_table(["A", "B", "C"], [["x", "y", "z"]])
        assert "x" in result and "y" in result and "z" in result


# ---------------------------------------------------------------------------
# Import-contract: no src.* / kernel.* / domains.* / third-party
# ---------------------------------------------------------------------------

def test_obsidian_emit_import_contract() -> None:
    """obsidian_emit.py must be stdlib-only; no src/kernel/domains/nba_api/numpy/pandas."""
    import ast

    src = (
        pathlib.Path(__file__).resolve().parents[2]
        / "scripts" / "platformkit" / "atlas" / "obsidian_emit.py"
    )
    tree = ast.parse(src.read_text(encoding="utf-8"))
    banned = {"src", "kernel", "domains", "nba_api", "api", "numpy", "pandas",
              "scipy", "sklearn", "torch", "xgboost"}
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in banned:
                    violations.append(f"import {alias.name} (line {node.lineno})")
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in banned:
                violations.append(f"from {node.module} import ... (line {node.lineno})")
    assert violations == [], "obsidian_emit.py import-contract violations:\n" + "\n".join(violations)
