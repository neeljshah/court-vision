# S28 -- pre-push guard (ops). LANDED, 5/5 CONSTRUCT. 2026-09-03

Gap: the secrets-scan and private-tree staging step lived only as prose, so the step
protecting the public repo was the one a long unattended night skips.

## Premise (Q8) -- HOLDS, not falsified

- `ls .git/hooks/` = samples plus `post-commit`; `pre-push` absent (sample only).
  No git-level enforcement, and no scanner script (`ls scripts/*secret*` empty).
- `scripts/hooks/pretooluse_guard.py` DOES block staging the private trees, the
  cookie jar, codex `auth.json` and sweeping adds -- but it is a Claude Code hook
  seeing only Bash issued inside a Claude session, so a codex worktree, a plain
  shell or a non-Claude agent pushes past it. Not edited.
- `TRACKING_PROGRAM_STATE_2026-09-02.md:88-92` is the only written definition of
  "secrets-scan" (step 4, prose, flagged "MECHANISE THIS"). `runpod-runbook.md`
  has no secrets text: the row's "three runbooks" is one plus the rules file.

## What landed

`scripts/hooks/prepush_guard.py` (128 lines, stdlib only, ASCII) reads the standard
pre-push stdin lines; range = `remote..local`, or `rev-list <local> --not --remotes`
when the remote sha is zero or unknown. `scripts/hooks/install_prepush.sh` writes
`.git/hooks/pre-push` (idempotent; run twice, identical output). Hook is live.

Refuses when (a) a commit touches `data/`, `vault/`, `.planning/`, `docs/research/`,
`docs/strategy/`, `.claude/`, a basename `ROADMAP.md`, a `youtube_cookies*` file, or
an `auth.json` under a `.codex*` dir; (b) an added line matches a pattern below; (c)
the update is a non-fast-forward (force-push is banned, so any non-descendant ref is
refused). A pure delete is allowed; a refusal names the pattern and file, never the
value.

Patterns: `sk-[A-Za-z0-9]{20,}`, `AKIA[0-9A-Z]{16}`, `ghp_[A-Za-z0-9]{30,}`,
`xox[baprs]-[A-Za-z0-9-]{10,}`, `-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----`, and
a case-insensitive assigned form (api_key / secret / token / password, then `:` or
`=`, then a quoted 16+ char literal).

## Measurement

Metric = refusal correctness. Denominator = 5 enumerated cases (CONSTRUCT, Q7).
Before = 0/5 (no hook); after = 5/5, none skipped.
`python -m pytest tests/platformkit/ops/test_prepush_guard.py -q` -> `5 passed in
6.16s`. Each case builds a tmp repo with a bare remote and drives the guard with a
faked stdin line: (1) `data/x.txt` refused, (2) `vault/y.md` refused, (3) an added
assigned-credential line refused, (4) a clean `docs/` commit allowed, (5) a
non-fast-forward ref update refused.

Live: `git push --dry-run origin master` printed `prepush_guard: 5 commits scanned,
clean` then `f8c496376..e0eb96e12  master -> master`, exit 0 (a dry run publishes
nothing). Live negative: `refs/heads/master <HEAD~4> refs/heads/master <HEAD>` piped
to the guard in master returned `prepush_guard REFUSED: non-fast-forward update to
refs/heads/master`, exit 1. Must-not-move, checked: no eval_gate threshold,
`data/registry/**`, the FWER ledger or `pretooluse_guard.py` was touched.

## NOT VERIFIED

- The private-tree and credential refusals were exercised only in constructed tmp
  repos, never against a real `origin` push.
- The pattern list is a floor, not coverage: it misses an unquoted credential, a base64 blob, a novel vendor prefix, and anything binary (no `+` lines).
- Merge commits are not scanned for their own content; parents are, when in range.
- Local and untracked: a fresh clone is unprotected until installed; `--no-verify` bypasses it.
