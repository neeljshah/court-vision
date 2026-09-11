# G405 preregistration: discovery format admission

Status: PREPARE-ONLY. This protocol is sealed before any premise check,
discovery request, format listing, metadata request, availability calculation,
sidecar export, render, eye review, or comparison. The Claude finisher alone
performs those actions after this file is committed.

## Scope and binding premise

The finisher first reads and hashes the current feeder discovery recipe,
selector, probe eligibility, and one complete bounded discovery/queue snapshot
on the pod. It names exact queue paths and field names. A cited
`/c/Users/neelj/nba-track-aNN/...` store path resolves under this worktree
root. If compatible 30 fps evidence already exists at discovery for at least
30 current unique sources, it may declare PREMISE FALSIFIED only after rerunning
that exact before-condition and quoting its output. Missing queries,
authorization, format access, or fewer than 30 distinct basketball-family
source ids produces PARTIAL with the complete inventory; completed sections do
not stand in for discovered sources.

## Frozen population, draw, and probes

Freeze the competition query list and discovery settings before a discovery-only
pass through the same public recipe in pod scratch. The pass is at most 15
minutes and must neither download nor enqueue to the live feeder. Preserve the
returned source-id population in original order with query memberships and
discovery UTC. Deduplicate by source id, sort unique rows by competition/query/
source id, and draw 30 at floor(j*(N-1)/29+0.5), j=0..29. Freeze ids before any
probe. No replacement is allowed.

For each drawn id, run one `yt-dlp -F` listing with frozen access settings,
`--no-playlist`, a 120 second timeout, and no retry. Also run one read-only,
no-download machine-readable metadata request with the same settings and a 60
second timeout. Preserve argv, executable/version, start/end UTC, stdout,
stderr, exit, timeout and raw format records without access material.

## Availability definition and sidecar

A qualifying rendition is a listed video format with HLS protocol, h264 codec,
height 720 through 1080 inclusive, and fps 29 through 31 inclusive. Record
720p30, 1080p30, 720p60, and 1080p60 separately. Numeric format ids alone do
not establish availability. `YES` requires both inventories to bind a
qualifying rendition; `NO` requires complete successful inventories to exclude
one; incomplete, ambiguous, or disagreeing evidence is `UNKNOWN`.

Export an additive unused `discovery_queue.jsonl` containing source_id,
discovered_at, format_probe_at, query, compatible_30fps,
qualifying_format_ids, preferred_format_if_available, fallback_reason,
raw_inventory_digest, and probe_status. Preserve every inherited field. The
live queue and selector remain byte-identical.

## Accounting, repeats, and limits

The primary coverage denominator is all 30 planned source ids; publish
YES/NO/UNKNOWN counts and per-query descriptive breakdowns. Repeating a source
through query memberships never increases n. Inspect all 30 paired listing and
metadata cards in even order, including failures. Rebuild parsing, tables, and
cards twice from saved bytes only. The 30-only policy consideration is supported
only by 30/30 known YES; otherwise keep the existing 30 fps preference with 60
fps fallback. This is a user decision, never an automatic admission change.

Sign convention for any future calibration-loss delta: improvement equals
baseline loss minus candidate loss; positive means candidate better. This
protocol creates no delta or result.
SEAL sha256 4bceb8457a4cf4a43bb08969610f69c446122c391e9071ba61524fad5a073097
