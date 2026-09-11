"""Extract and replay the G393 caller and argparse setup without running mains."""
from __future__ import annotations

import argparse
import ast
import contextlib
import hashlib
import io
import json
import sys
from pathlib import Path
from typing import Any


RUN_CLIP = "scripts/run_clip.py"
DAEMON = "scripts/platformkit/track_daemon.py"
PAIR = '"--game-id", game_id,'
SINGLE = '"--game-id=" + game_id,'


def sha256_text(text: str) -> str:
    """Return the SHA-256 of UTF-8 source text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    matches = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    if len(matches) != 1:
        raise ValueError("unrecognized-%s-function" % name)
    return matches[0]


def _assignment(tree: ast.Module, name: str) -> ast.Assign:
    matches = [node for node in tree.body if isinstance(node, ast.Assign)
               and any(isinstance(target, ast.Name) and target.id == name for target in node.targets)]
    if len(matches) != 1:
        raise ValueError("unrecognized-%s-global" % name)
    return matches[0]


def extract_build_command(source: str):
    """Compile only the actual caller plus the globals it reads."""
    tree = ast.parse(source, filename=DAEMON)
    function = _function(tree, "build_command")
    parameters = {argument.arg for argument in function.args.args}
    locals_ = {node.id for node in ast.walk(function) if isinstance(node, ast.Name)
               and isinstance(node.ctx, ast.Store)}
    names = {node.id for node in ast.walk(function) if isinstance(node, ast.Name)
             and isinstance(node.ctx, ast.Load) and node.id not in parameters | locals_}
    expected = {"sys", "str", "list", "Path", "CLIP_SPORTS", "TRACKING", "SPORT_ADAPTER"}
    if names != expected:
        raise ValueError("unrecognized-build-command-globals:%s" % sorted(names))
    module = ast.Module(body=[_assignment(tree, "TRACKING"), _assignment(tree, "CLIP_SPORTS"),
                              _assignment(tree, "SPORT_ADAPTER"), function],
                        type_ignores=[])
    ast.fix_missing_locations(module)
    namespace: dict[str, Any] = {"Path": Path, "sys": sys, "str": str, "list": list}
    exec(compile(module, DAEMON, "exec"), namespace)
    return namespace["build_command"]


def extract_parser(source: str) -> argparse.ArgumentParser:
    """Compile all and only run_clip argparse construction statements."""
    main = _function(ast.parse(source, filename=RUN_CLIP), "main")
    start = next((index for index, node in enumerate(main.body)
                  if isinstance(node, ast.Assign) and len(node.targets) == 1
                  and isinstance(node.targets[0], ast.Name) and node.targets[0].id == "ap"
                  and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute)
                  and isinstance(node.value.func.value, ast.Name) and node.value.func.value.id == "argparse"
                  and node.value.func.attr == "ArgumentParser"), None)
    if start is None:
        raise ValueError("unrecognized-parser-start")
    stop = next((index for index in range(start + 1, len(main.body))
                 if isinstance(main.body[index], ast.Assign) and isinstance(main.body[index].value, ast.Call)
                 and isinstance(main.body[index].value.func, ast.Attribute)
                 and isinstance(main.body[index].value.func.value, ast.Name)
                 and main.body[index].value.func.value.id == "ap"
                 and main.body[index].value.func.attr == "parse_args"), None)
    if stop is None:
        raise ValueError("unrecognized-parser-stop")
    declarations = main.body[start + 1:stop]
    if not declarations or any(not isinstance(node, ast.Expr) or not isinstance(node.value, ast.Call)
                               or not isinstance(node.value.func, ast.Attribute)
                               or not isinstance(node.value.func.value, ast.Name)
                               or node.value.func.value.id != "ap" or node.value.func.attr != "add_argument"
                               for node in declarations):
        raise ValueError("unrecognized-parser-declarations")
    factory = ast.FunctionDef(name="_factory", args=ast.arguments(posonlyargs=[], args=[], kwonlyargs=[],
                              kw_defaults=[], defaults=[]), body=[main.body[start], *declarations,
                              ast.Return(value=ast.Name(id="ap", ctx=ast.Load()))], decorator_list=[])
    module = ast.Module(body=[factory], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace: dict[str, Any] = {"argparse": argparse}
    exec(compile(module, RUN_CLIP, "exec"), namespace)
    return namespace["_factory"]()


def proposed_source(source: str) -> str:
    """Change exactly the approved caller token pair in an in-memory source copy."""
    if source.count(PAIR) != 1 or SINGLE in source:
        raise ValueError("unrecognized-proposal-anchor")
    proposed = source.replace(PAIR, SINGLE)
    if proposed.count(SINGLE) != 1:
        raise ValueError("proposal-replacement-failed")
    return proposed


def parse_card(parser: argparse.ArgumentParser, argv: list[str]) -> dict[str, Any]:
    """Capture argparse status, stderr, and sorted namespace for one argv array."""
    stderr = io.StringIO()
    status = 0
    namespace: dict[str, Any] | None = None
    with contextlib.redirect_stderr(stderr):
        try:
            parsed = parser.parse_args(argv[2:])
            namespace = dict(sorted(vars(parsed).items()))
        except SystemExit as error:
            status = int(error.code)
    return {"argv": argv, "return_status": status, "stderr": stderr.getvalue(), "namespace": namespace}


def cases() -> list[dict[str, str]]:
    """Return the fixed 60-case construct universe plus six supplemental values."""
    result = []
    for index in range(30):
        result.append({"kind": "leading", "game_id": "-Oa_BpdVT64_s%d" % (1000 + index)})
        result.append({"kind": "ordinary", "game_id": "Oa_BpdVT64_s%d" % (1000 + index)})
    result.extend({"kind": "supplemental", "game_id": value}
                  for value in ("--help", "--frames", "-1", "-", "--", "-x=y"))
    return result


def replay(daemon_source: str, clip_source: str) -> dict[str, Any]:
    """Replay every fixed argv in original and proposed in-memory caller forms."""
    build_before = extract_build_command(daemon_source)
    proposal = proposed_source(daemon_source)
    build_after = extract_build_command(proposal)
    parser = extract_parser(clip_source)
    records = []
    for ordinal, case in enumerate(cases(), start=1):
        video = Path("input path") / ("clip %02d.mp4" % ordinal)
        before = build_before("wnba", video, case["game_id"])
        after = build_after("wnba", video, case["game_id"])
        records.append({"ordinal": ordinal, **case, "before": parse_card(parser, before),
                        "after": parse_card(parser, after)})
    return {"source_hashes": {DAEMON: sha256_text(daemon_source), RUN_CLIP: sha256_text(clip_source),
                              "proposed_track_daemon": sha256_text(proposal)}, "proposal": proposal,
            "records": records, "argument_count": len(parser._actions) - 1}


def json_line(record: dict[str, Any]) -> str:
    """Serialize a receipt record deterministically."""
    return json.dumps(record, sort_keys=True, separators=(",", ":"))
