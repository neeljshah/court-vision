# G381 preregistration amendment A1 (sealed alone, before run 2)

Run 1 (artifacts kept under `run1_git_object_ids/`, memo `memo_run1.md`) compared memo tokens against
`git hash-object --no-filters` object ids. Those are 40-hex SHA-1 object ids; every landed memo prints
`sha256sum` digests of file BYTES (64-hex) or their prefixes. Run 1 therefore classified 1,956 of 2,000
tokens UNRESOLVED by construction of the rule, not by any property of the memos. This amendment
replaces the resolution rule; the token grammar, the enumeration, the classes and the bar are unchanged.

## Resolution order (replaces the prereg section of the same name)

Artifact path candidates for the backticked name nearest the token on its line, tried in order:
(1) as written, relative to the repo root; (2) relative to the memo's evidence directory (the memo's
stem as a directory); (3) relative to the memo's own directory; (4) the basename searched inside the
memo's evidence tree (unique match required). Then, at the memo's landing commit (first master commit
adding the memo):
(a) IDENTIFIES_AT_LANDING: SHA-256 of the raw blob bytes (`git cat-file -p <blob>`, i.e. the bytes as
    committed, no filters) equals the token, or the token is a prefix (>= 8 hex) of exactly one such digest;
(b) IDENTIFIES_AT_HEAD_ONLY: the same comparison against the blob at HEAD;
(c) CRLF_ONLY: SHA-256 of the blob bytes with CRLF normalised to LF (at landing, then HEAD);
(d) ARTIFACT_UNNAMED: the token (full or unique prefix) equals the SHA-256 of ANY blob in the memo's
    evidence tree at landing or at HEAD, or of the memo itself, or of the memo's bytes above a SEAL line
    (a prereg seal names its own file);
(e) OBJECT_ID: a 40-hex token equal to a git object id reachable from the landing commit (a commit or
    blob id printed as provenance, not a digest) -- counted separately, never as UNRESOLVED;
(f) UNRESOLVED with sub-reason: artifact never committed / pod-only or absolute path / prefix ambiguous /
    token is not a digest.
Run 2 executes this order over the same enumeration; the second run must diff byte-identical.

Re-seal note: the first commit of this file (36871b4e4) carried a seal computed over the text without the blank line preceding the SEAL line; this commit seals every byte above the SEAL line.
SEAL sha256 172893096eecc7b3f37fb7c1cf60bb68b1da4acde4fc6f6d0156018a644a12e6
