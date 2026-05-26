"""L43_runbook_generator.py — Runbook documentation generator for the execute_loop.

Reads every L*.py module via AST (never imports them) and writes RUNBOOK.md.

Environment variables
---------------------
  None required. Defaults work out-of-the-box.

Invariants
----------
  - Pure stdlib; no third-party imports.
  - Only top-level (non-private) symbols are documented.
  - Write is atomic: tmp file + os.replace so no partial state.
  - L29 (gated, no module file) renders as a placeholder section.
"""
from __future__ import annotations

import ast
import argparse
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_LAYER_RE     = re.compile(r"^L(\d{1,2})_.*\.py$")
_ENV_CONST_RE = re.compile(r".*_(MODE|ENV_VAR)$|^(PAPER|LIVE)_.*")
_MODE_DOC_RE  = re.compile(r"(?i)(paper|live)[\s_-]*mode|MODE GATING")

_DEFAULT_LAYERS_DIR = Path(__file__).resolve().parent
_DEFAULT_STATE      = _DEFAULT_LAYERS_DIR / "state.json"
_DEFAULT_OUT        = _DEFAULT_LAYERS_DIR / "RUNBOOK.md"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------
@dataclass
class PublicSymbol:
    kind: str       # "function" | "class"
    name: str
    signature: str
    summary: str


@dataclass
class LayerInfo:
    layer_id: str          # "L01"
    layer_num: int
    name: str
    status: str
    module_path: Optional[Path]
    module_doc: str
    publics: list = field(default_factory=list)          # list[PublicSymbol]
    env_constants: list = field(default_factory=list)    # list[tuple[str,str]]
    mode_block: Optional[str] = None
    imports_from_layers: list = field(default_factory=list)  # list[str]


# ---------------------------------------------------------------------------
# RunbookGenerator
# ---------------------------------------------------------------------------
class RunbookGenerator:
    def __init__(
        self,
        layers_dir: Path,
        state_json_path: Path,
        output_path: Path,
    ) -> None:
        self.layers_dir = layers_dir
        self.state_json_path = state_json_path
        self.output_path = output_path

    def discover_layers(self) -> list[Path]:
        """Return sorted list of L*.py paths in layers_dir."""
        paths = [
            p for p in self.layers_dir.iterdir()
            if p.is_file() and _LAYER_RE.match(p.name)
        ]
        return sorted(paths, key=lambda p: int(_LAYER_RE.match(p.name).group(1)))

    def parse_layer(self, path: Path) -> LayerInfo:
        """AST-parse a single layer file; never imports it."""
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)

        module_doc = ast.get_docstring(tree) or ""
        publics: list[PublicSymbol] = []
        env_constants: list[tuple[str, str]] = []
        imports_from_layers: list[str] = []

        for node in tree.body:
            # Public functions / async functions
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("_"):
                    sig = _build_func_sig(node)
                    summary = _first_line(ast.get_docstring(node))
                    publics.append(PublicSymbol("function", node.name, sig, summary))

            # Public classes
            elif isinstance(node, ast.ClassDef):
                if not node.name.startswith("_"):
                    bases = ", ".join(ast.unparse(b) for b in node.bases)
                    sig = f"class {node.name}({bases})" if bases else f"class {node.name}"
                    summary = _first_line(ast.get_docstring(node))
                    publics.append(PublicSymbol("class", node.name, sig, summary))

            # Top-level assignments — env constants
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and _ENV_CONST_RE.match(target.id):
                        try:
                            val = ast.unparse(node.value)
                        except Exception:
                            val = "..."
                        env_constants.append((target.id, val))

            # ImportFrom — cross-layer references
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                if "execute_loop" in mod:
                    m = re.search(r"\.(L\d{1,2})", mod)
                    if m:
                        imports_from_layers.append(m.group(1))

        # Scan for os.environ.get / os.getenv calls anywhere
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                # environ.get(VAR_NAME) → Attribute(attr='get', value=Attribute(attr='environ'))
                # os.getenv(VAR_NAME)   → Attribute(attr='getenv', value=Name(id='os'))
                # environ.get(VAR_NAME) → Attribute(attr='get', value=Name(id='environ'))
                is_env_get = False
                if isinstance(func, ast.Attribute):
                    if func.attr == "get" and isinstance(func.value, ast.Attribute) and func.value.attr == "environ":
                        is_env_get = True
                    elif func.attr in ("get", "getenv") and isinstance(func.value, ast.Name) and func.value.id in ("environ", "os"):
                        is_env_get = True
                elif isinstance(func, ast.Name) and func.id == "getenv":
                    is_env_get = True
                if is_env_get and node.args:
                    first = node.args[0]
                    if isinstance(first, ast.Constant) and isinstance(first.value, str):
                        key = first.value
                        default = ast.unparse(node.args[1]) if len(node.args) > 1 else "None"
                        env_constants.append((key, default))

        # De-duplicate env constants preserving order
        seen: set[str] = set()
        deduped: list[tuple[str, str]] = []
        for k, v in env_constants:
            if k not in seen:
                seen.add(k)
                deduped.append((k, v))
        env_constants = deduped

        mode_block: Optional[str] = None
        if module_doc and _MODE_DOC_RE.search(module_doc):
            mode_block = _extract_mode_block(module_doc)

        m = _LAYER_RE.match(path.name)
        layer_num = int(m.group(1)) if m else 0
        layer_id = f"L{layer_num:02d}"

        return LayerInfo(
            layer_id=layer_id,
            layer_num=layer_num,
            name=path.stem,
            status="shipped",
            module_path=path,
            module_doc=module_doc,
            publics=publics,
            env_constants=env_constants,
            mode_block=mode_block,
            imports_from_layers=sorted(set(imports_from_layers)),
        )

    @staticmethod
    def build_cross_reference(layers: list[LayerInfo]) -> dict[str, list[str]]:
        """Return {layer_id: [layer_ids it imports from]} for layers with cross-refs."""
        return {
            li.layer_id: li.imports_from_layers
            for li in layers
            if li.imports_from_layers
        }

    def build_runbook(self) -> str:
        """Parse state.json + all layer files; return full RUNBOOK.md markdown."""
        state = json.loads(self.state_json_path.read_text(encoding="utf-8"))
        layer_registry: dict[str, dict] = state.get("layers", {})

        file_map: dict[int, Path] = {}
        for p in self.discover_layers():
            m = _LAYER_RE.match(p.name)
            if m:
                file_map[int(m.group(1))] = p

        layers: list[LayerInfo] = []
        for lkey, ldata in layer_registry.items():
            num = int(lkey.lstrip("L"))
            layer_id = f"L{num:02d}"
            status = ldata.get("status", "unknown")
            name = ldata.get("name", lkey)
            path = file_map.get(num)

            if path and path.exists():
                info = self.parse_layer(path)
                info.layer_id = layer_id
                info.layer_num = num
                info.name = name
                info.status = status
            else:
                # Gated or missing
                info = LayerInfo(
                    layer_id=layer_id,
                    layer_num=num,
                    name=name,
                    status=status,
                    module_path=None,
                    module_doc="",
                )
            layers.append(info)

        layers.sort(key=lambda li: li.layer_num)
        xref = self.build_cross_reference(layers)

        lines: list[str] = []
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines.append(f"# Execute Loop Runbook\n")
        lines.append(f"_Generated {ts} — do not edit by hand._\n")

        # Table of contents
        lines.append("## Table of Contents\n")
        for li in layers:
            anchor = f"{li.layer_id.lower()}--{li.name.lower().replace(' ', '-').replace('/', '')}"
            lines.append(f"- [{li.layer_id} — {li.name}](#{anchor})")
        lines.append("- [Cross-Reference Table](#cross-reference-table)")
        lines.append("")

        # Per-layer sections
        for li in layers:
            ships = layer_registry.get(f"L{li.layer_num}", {}).get("ships", [])
            last = ships[-1] if ships else {}
            tests = last.get("tests", "—")
            loc = last.get("loc", "—")

            lines.append(f"## {li.layer_id} — {li.name}\n")
            lines.append(f"**Status:** `{li.status}` | **Tests:** {tests} | **LOC:** {loc}\n")

            if li.module_path is None:
                lines.append("_(gated — no module)_\n")
                continue

            if li.module_doc:
                lines.append("> " + li.module_doc.replace("\n", "\n> ") + "\n")

            # Public API
            if li.publics:
                lines.append("### Public API\n")
                for sym in li.publics:
                    lines.append(f"```python")
                    lines.append(sym.signature)
                    lines.append("```")
                    if sym.summary:
                        lines.append(f"_{sym.summary}_\n")
                    else:
                        lines.append("")

            # Environment variables
            if li.env_constants:
                lines.append("### Environment Variables\n")
                lines.append("| Name | Default / Value |")
                lines.append("|------|----------------|")
                for k, v in li.env_constants:
                    lines.append(f"| `{k}` | `{v}` |")
                lines.append("")

            # Paper vs live mode
            if li.mode_block:
                lines.append("### Paper vs Live Mode\n")
                lines.append("```")
                lines.append(li.mode_block)
                lines.append("```\n")

            # How to run
            lines.append("### How to Run\n")
            rel = li.module_path.relative_to(self.layers_dir.parent.parent)
            lines.append(f"```bash")
            lines.append(f"conda run -n basketball_ai python {rel}")
            lines.append("```\n")

        # Cross-Reference Table
        lines.append("## Cross-Reference Table\n")
        lines.append("| Layer | Imports From |")
        lines.append("|-------|-------------|")
        if xref:
            for lid, deps in sorted(xref.items()):
                lines.append(f"| `{lid}` | {', '.join(f'`{d}`' for d in deps)} |")
        else:
            lines.append("| — | — |")
        lines.append("")

        return "\n".join(lines)

    def write_atomic(self) -> Path:
        """Build RUNBOOK.md and write atomically via tmp+os.replace; return output path."""
        markdown = self.build_runbook()
        tmp = self.output_path.with_suffix(self.output_path.suffix + ".tmp")
        tmp.write_text(markdown, encoding="utf-8")
        os.replace(tmp, self.output_path)
        return self.output_path


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------
def _build_func_sig(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    try:
        args_str = ast.unparse(node.args)
    except Exception:
        args_str = "..."
    ret = ""
    if node.returns:
        try:
            ret = f" -> {ast.unparse(node.returns)}"
        except Exception:
            pass
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    return f"{prefix} {node.name}({args_str}){ret}"


def _first_line(doc: Optional[str]) -> str:
    if not doc:
        return ""
    return doc.strip().splitlines()[0].strip()


def _extract_mode_block(doc: str) -> str:
    """Extract the mode-gating paragraph from a module docstring."""
    lines = doc.splitlines()
    start = None
    for i, line in enumerate(lines):
        if _MODE_DOC_RE.search(line):
            start = i
            break
    if start is None:
        return doc
    end = len(lines)
    for i in range(start + 1, len(lines)):
        if lines[i].strip() == "" and i > start + 1:
            end = i
            break
    return "\n".join(lines[start:end]).strip()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Generate RUNBOOK.md by AST-parsing all L*.py execute_loop modules."
    )
    parser.add_argument(
        "--layers-dir", type=Path, default=_DEFAULT_LAYERS_DIR,
        help="Directory containing L*.py modules (default: same dir as this script)"
    )
    parser.add_argument(
        "--state", type=Path, default=_DEFAULT_STATE,
        help="Path to state.json (default: <layers-dir>/state.json)"
    )
    parser.add_argument(
        "--out", type=Path, default=_DEFAULT_OUT,
        help="Output path for RUNBOOK.md"
    )
    args = parser.parse_args(argv)

    gen = RunbookGenerator(
        layers_dir=args.layers_dir,
        state_json_path=args.state,
        output_path=args.out,
    )
    out = gen.write_atomic()
    size = out.stat().st_size
    lines = out.read_text(encoding="utf-8").count("\n")
    print(f"RUNBOOK.md written → {out}  ({size:,} bytes, {lines:,} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
