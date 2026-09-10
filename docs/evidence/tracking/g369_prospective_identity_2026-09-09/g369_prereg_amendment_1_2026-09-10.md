# G369 PREREG AMENDMENT 1 - exercised weight paths

This amendment is sealed before any G369 live-ledger count, PIN, alignment, export, or
comparison. It supersedes only the three weight arguments in section 4 of
`g369_prereg_2026-09-09.md`; every sampling, bar, binding, alignment, repeatability,
collision, and no-write rule in the original preregistration remains byte-for-byte in force.

Reason: a post-seal read-only route search established the exercised paths as repository-root
`yolov8n.pt`, `models/weights/yolov8n_ball.pt`, and
`data/models/osnet_x0_25_imagenet.pth`. The original command incorrectly placed the first two
under `data/models/`. This correction is made before any prospective result, rather than
silently accepting missing digests.

Effective PIN command replacement:

    $M pin --ledger $LEDGER --dirs data/footage_bridge data/footage_corpus --repo . \
      --weights yolov8n.pt models/weights/yolov8n_ball.pt \
      data/models/osnet_x0_25_imagenet.pth --out $OUT

The final memo must name this amendment and both preregistration seals. The finisher must not
run the superseded command. This is an identity-path correction only; it does not alter a bar,
threshold, sampled set, or source-binding field.

SEAL RULE: the hex on the last line is the SHA-256 of every byte above that line, after
normalising CRLF to LF, including the newline ending the preceding line.
SEAL sha256 1017e4df5bf94ed64696389cb01fbf8ea5c653e08bd07fd512427c48d2217906
