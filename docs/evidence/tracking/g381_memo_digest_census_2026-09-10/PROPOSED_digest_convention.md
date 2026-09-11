# Proposed G381 digest convention

Each artifact line carries its full 64-hex SHA-256 of raw committed blob bytes
(`git cat-file -p <blob>`) and its backticked repository-relative artifact path
on that same line. Prefixes are not permitted. This is a proposal only; it is
not wired into a hook or any existing memo workflow.
