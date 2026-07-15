# Pricing Tiers

> Positioning only -- no real billing. The access-control layer
> (`sell.entitlements`) enforces these feature sets programmatically.

## Free

NBA predictions only. CLV-tracked paper trail read access (out-of-sample calibration history). Honest calibration + CLV cadence. Read-only; no export; no streaming.

Features:

  [x] CLV paper trail (read)
  [x] NBA predictions
  [ ] Bulk slate download
  [ ] CLV report export (CSV/JSON)
  [ ] live_edges
  [ ] paper_place
  [ ] MLB predictions
  [ ] Soccer predictions
  [ ] Tennis predictions
  [ ] SSE streaming endpoint
  [ ] Evidence pack (OOS calibration audit + WF transcript)
  [ ] Governance run artifacts
  [ ] Methodology document

## Pro

All-sport predictions (NBA, MLB, soccer, tennis) plus full CLV report export (CSV/JSON), server-sent-events streaming endpoint, and bulk slate download. Includes everything in Free.

Features:

  [x] CLV paper trail (read)
  [x] NBA predictions
  [x] Bulk slate download
  [x] CLV report export (CSV/JSON)
  [x] live_edges
  [x] paper_place
  [x] MLB predictions
  [x] Soccer predictions
  [x] Tennis predictions
  [x] SSE streaming endpoint
  [ ] Evidence pack (OOS calibration audit + WF transcript)
  [ ] Governance run artifacts
  [ ] Methodology document

## Enterprise

Everything in Pro plus the evidence pack: OOS calibration audit, walk-forward transcript, governance run artifacts, and the methodology document. Full due-diligence access for a quant buyer.

Features:

  [x] CLV paper trail (read)
  [x] NBA predictions
  [x] Bulk slate download
  [x] CLV report export (CSV/JSON)
  [x] live_edges
  [x] paper_place
  [x] MLB predictions
  [x] Soccer predictions
  [x] Tennis predictions
  [x] SSE streaming endpoint
  [x] Evidence pack (OOS calibration audit + WF transcript)
  [x] Governance run artifacts
  [x] Methodology document

## Notes

- `[x]` = included; `[ ]` = not available on this tier.
- Unknown features are always DENIED (fail-closed on typos).
- `edge_claimed=false` is a hard constant on every API surface
  regardless of tier -- no tier asserts a monetary-edge claim.
- Enterprise tier includes the full evidence pack for due-diligence.
