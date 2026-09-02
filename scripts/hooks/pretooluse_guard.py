#!/usr/bin/env python
"""PreToolUse guard hook (WIRED -- live as PreToolUse:Bash in ~/.claude/settings.json).

Reads the Claude Code PreToolUse stdin JSON contract:
  {session_id, cwd, hook_event_name, tool_name, tool_input:{command|file_path|...}}

BLOCK mechanism (documented): exit code 2 with the reason on stderr.

Blocks dangerous Bash commands per repo invariants:
  - any `--force`
  - a full `pytest tests/` (freezes the box) -- a single test file is allowed
Push to public `origin` master is ALLOWED per the 2026-07-09 user override
(re-authorized directly in-session); secrets-scan before every push. `--force`
stays blocked. Also emits non-blocking guidance (exit 0 + stderr) when a bash
command lacks the required `cd /c/Users/neelj/nba-ai-system &&` cwd prefix.

ASCII only. Idempotent: pure function of stdin, no side effects.
"""
import json
import re
import sys

REQUIRED_CWD_PREFIX = "cd /c/Users/neelj/nba-ai-system"


def _block(reason):
    sys.stderr.write("BLOCKED: " + reason + "\n")
    sys.exit(2)


def _warn(msg):
    sys.stderr.write("GUIDANCE: " + msg + "\n")
    sys.exit(0)


def _is_full_pytest(cmd):
    # `pytest tests/` (the whole dir) freezes the box; a single file is OK.
    for m in re.finditer(r"\bpytest\b([^\n;&|]*)", cmd):
        args = m.group(1)
        # collect non-flag tokens (test targets)
        targets = [t for t in args.split() if not t.startswith("-")]
        for t in targets:
            # a bare `tests` or `tests/` (dir, no file) -> full suite
            if re.fullmatch(r"tests/?", t):
                return True
        # bare `pytest` with no target also runs the whole suite
        if not targets:
            return True
    return False


_PRIVATE_RE = re.compile(
    r"\bgit\b[^\n;&|]*\b(add|commit)\b[^\n;&|]*"
    r"((^|[\s'\"=])data/|(^|[\s'\"=])vault/|youtube_cookies|\.codex-a[0-9]|auth\.json)")
_SWEEP_RE = re.compile(r"\bgit\b[^\n;&|]*\badd\b[^\n;&|]*\s(-A|--all|\.)(\s|$)")


_TAR_X_RE = re.compile(r"\btar\b[^\n;|&]*\s-?[a-zA-Z]*x[a-zA-Z]*\b[^\n;|&]*")


def _is_local_tar_extract(cmd):
    # Block a tar extract that lands in the main repo: no -C at all, or -C pointing at the repo root.
    for m in _TAR_X_RE.finditer(cmd):
        seg = m.group(0)
        if "ssh " in cmd[: m.start()]:
            continue  # remote extract inside an ssh command string
        # The sanctioned landing recipe archives an EXPLICIT pathspec (git archive <sha> -- <paths> | tar -x -C <repo>);
        # the 2026-09-03 clobber was a PATHLESS archive of a stale branch. Exempt archives that name their paths.
        upstream = cmd[: m.start()]
        if "git" in upstream and "archive" in upstream and " -- " in upstream:
            continue
        if "-C" not in seg:
            return True
        if re.search(r"-C\s+[\"']?(/c|C:)?/?Users/neelj/nba-ai-system[\"']?(\s|$)", seg):
            return True
    return False


def _stages_private_paths(cmd):
    return bool(_PRIVATE_RE.search(cmd))


def _is_sweeping_add(cmd):
    return bool(_SWEEP_RE.search(cmd))


def main():
    raw = sys.stdin.read()
    try:
        data = json.loads(raw) if raw.strip() else {}
    except (ValueError, TypeError):
        # malformed input -> do not block; let the tool proceed
        sys.exit(0)

    if data.get("tool_name") != "Bash":
        sys.exit(0)

    cmd = (data.get("tool_input") or {}).get("command", "") or ""

    if "--force" in cmd:
        _block("`--force` detected -- destructive. Human-gated; refusing.")

    # 2026-09-03 (PLAN_AI_ENGINEERING s2b): the public origin must never see data/, vault/,
    # the cookie jar, a codex home or auth.json; and `git add -A` / `git add .` sweep them in.
    if _stages_private_paths(cmd):
        _block("staging/committing data/, vault/, youtube_cookies, .codex-a*/ or auth.json "
               "is forbidden (public origin). Stage an explicit pathspec.")
    if _is_local_tar_extract(cmd):
        _block("`tar -x` into the MAIN repo (or with no -C target) overwrites the shared working tree "
               "with a stale archive -- 3,154 tracked files were clobbered on 2026-09-03 this way. "
               "Extract only into a pod path via ssh or an explicit scratch -C target.")
    if _is_sweeping_add(cmd):
        _block("`git add -A` / `git add .` sweeps gitignored-intent files into the commit. "
               "Stage an explicit pathspec instead.")

    if _is_full_pytest(cmd):
        _block("full `pytest tests/` freezes this box. Run a single test "
               "file instead, e.g. `pytest tests/path/test_one.py`.")

    if REQUIRED_CWD_PREFIX not in cmd:
        _warn("bash cwd is FLAKY -- prefix commands with "
              "`cd /c/Users/neelj/nba-ai-system &&` for reliable cwd.")

    sys.exit(0)


if __name__ == "__main__":
    main()
