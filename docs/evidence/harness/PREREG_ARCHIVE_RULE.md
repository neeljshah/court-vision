# Preregistration archive-location rule

Every S-lane preregistration names the exact scratch path used to stage each input.
The evidence memo prints the realised staging path for every staged artifact.

`scripts.platformkit.eval_gate.archive_path_check` compares those declarations and
reports one of the following per artifact:

- `MATCH`: the preregistered and realised paths are identical.
- `MISMATCH`: both paths are stated but differ.
- `UNSTATED`: either declaration is unavailable; this is reported, not quarantined.
- `ABSENT`: a memo named for review is absent in the current worktree.

For committed evidence read in place, both artifacts state `NONE (committed evidence
read in place)`. This rule is additive and does not alter any landed artifact.
