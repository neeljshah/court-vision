# G326 preregistration SUPPLEMENT -- AST sink census (2026-09-07)

Spec `docs/evidence/tracking/specs/G326_spec.md` (master `dce917b36`). Worktree a17.
Supersedes sections 2 and 3 of `g326_prereg_2026-09-07.md` (seal
`a2a5fbc7a3e4f7f655a4798c1cab78bc0e8cf718ab5321383f7e2839977fe9ad`). Sealed BEFORE the
re-sweep, committed ALONE. Sections 1, 4, 5, 6, 7 of the original prereg stand unchanged.

## Why this supplement exists

The G326 verifier REJECTED `e641f68ee`: the sealed enumeration rule was a `grep -rn` whose
DEFECT/no-DEFECT decision required the read and the hash to land on the SAME SOURCE LINE. That
is not an exhaustive denominator. It silently drops every sink whose read and hash are split
across lines or across a loop -- e.g. `autoloop/standing_prereg.py:241`,
`combo/corpus_cache.py:42`, `eval_gate/ledger_backup.py:37`. A same-line count cannot be
called CONSTRUCT-exhaustive (Q7). The enumeration is therefore replaced, not patched.

## 2'. Enumeration rule (replaces section 2)

An `ast` walk (stdlib only, no regex denominator) over EVERY `.py` under
`scripts/platformkit/**`, including `test_*` files, parsed with `ast.parse` on the file bytes.
A SINK is either:

  S1  a Call whose func resolves to `hashlib.sha256|sha1|md5|sha224|sha384|sha512|
      blake2b|blake2s|hashlib.new`, however imported (`import hashlib`, `from hashlib import
      sha256`, an aliased module or name);
  S2  a Call to `.update(...)` whose receiver is a local name bound to an S1 call in the same
      function scope (the incremental/streamed form).

Every S1 and S2 site is a row. A file that fails to parse is reported as a row with
`input_class=PARSE_ERROR`, never silently dropped. The denominator is the row count. This is
the CONSTRUCT n: exhaustive over `scripts/platformkit/**`, not a sample (Q7; A3 does not apply).

## 3'. Classification (replaces section 3) -- EXACTLY ONE class per sink, by data flow

The hashed EXPRESSION is followed backwards through same-function name bindings. First rule
that matches wins; the order below IS the precedence, so every sink lands in exactly one class:

  FILE_STREAM  the hashed bytes come from a chunked read: the sink is an S2 `.update(x)` inside
               a `for`/`while` over `f.read(n)`, or the argument derives from
               `iter(lambda: f.read(n), b"")`, or an S1 argument is a `.read(n)` with a size arg.
  FILE_WHOLE   the hashed bytes are a whole file read: `Path(...).read_bytes()`,
               `open(..., "rb").read()` with no size argument, or a name bound to one.
  TAINTED      the hashed/compared value comes from calling a helper that itself returns a
               hexdigest (`sha256(p)`, `sha256_lf(p)`, `_sha(p)`, `file_sha256(p)`, ...) --
               a function defined in the census tree whose body contains an S1/S2 sink over a
               file read. Recorded at the CALL site so the flow is counted where it executes;
               the helper's own body is counted once, in its own row.
  MEMORY       everything else: `str.encode()`, `json.dumps(...).encode()`, an f-string, a
               literal, a `subprocess`/`git cat-file` capture, an in-run slice.

For FILE_WHOLE, FILE_STREAM and TAINTED only, two further syntactic facts are recorded:

  text_or_binary  TEXT if any path literal, suffix literal or f-string reaching the sink ends in
                  `.md .csv .json .txt .yaml .yml .py`; BINARY for
                  `.mp4 .png .jpg .pt .pth .parquet .npy .npz .gz .zip .bin`; UNKNOWN when the
                  path is a parameter or a variable the walk cannot resolve syntactically.
  compared        COMMITTED if the digest is compared against a value that lives in the repo --
                  an `assert`/`==`/`!=` against a 64-hex (or 32/40-hex) literal, against a
                  subscript of parsed committed JSON/CSV, or a dict/`==` equality naming the
                  digest; RECORD_ONLY if the digest is only written into an output, printed,
                  or stored in a dict that is dumped.

## The DEFECT rule (unchanged in substance, restated over the new denominator)

  A sink is a DEFECT if and only if
      input_class in {FILE_WHOLE, FILE_STREAM, TAINTED}
      AND text_or_binary == TEXT
      AND compared == COMMITTED.

  A TEXT artifact hashed from raw bytes and compared against a value COMMITTED to the repo is a
  DEFECT: `core.autocrlf` makes the digest a function of the checkout, so the assertion is
  un-re-executable on a clone whose line endings differ. BINARY, RECORD_ONLY and MEMORY sinks
  are counted, never converted. Sinks already routed through `sha256_lf` are reported as
  ALREADY_LF and are not defects.

## Honest limits of the walker (stated before running it)

Static and syntactic. It cannot resolve a path built at runtime (those are UNKNOWN, reported,
not assumed fine), cannot follow a digest across module boundaries beyond the one TAINTED hop,
and does not execute anything. UNKNOWN is a reported class, never folded into a "fine" bucket.
The census bounds the denominator; it does not prove any seal CORRECT.

## Reconciliation duty

The census counts are reported ALONGSIDE the verifier's independently derived
154 / 122 / 32 (total / direct+tainted / streamed). Any difference is EXPLAINED, per class,
naming files. Agreement is NOT forced and the walker is NOT tuned to reproduce those numbers.

## Committed-seal split duty

The 5 LF / 8 RAW over 13 unique `(path, expected)` pairs the verifier reproduced is recomputed
over ALL pairs the walker finds in COMMITTED text sinks. Unique pairs, LF-matching,
RAW-matching and neither are reported. A differing count lists every pair.

## Artifact and seal

Output table: `docs/evidence/tracking/g326_artifact/hash_sinks.csv`, one row per sink,
columns `file,line,api,input_class,text_or_binary,compared,verdict`. Walker:
`scripts/platformkit/g326_hash_sink_census.py`, stdlib `ast` only, <= 300 LOC. The test
asserts the three verifier-named sites are present.

## Seal

SHA-256 of the LF-normalized bytes above this line: `beae43fb72cbfb8f60208527ef33fb5ab6ac5f656930cdd6e51c4a0288afd87e`
