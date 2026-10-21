// betId.ts -- plain (server-safe) bet id builder.
import type { PaperTrailRow } from "@/lib/p5api";

// bet_id is constructed from the ledger row fields for stable routing.
export function toBetId(r: PaperTrailRow): string {
  // Mirrors the durable bet_id pattern from clv_ledger: sport|matchup|side|ts
  const parts = [
    r.sport || "unknown",
    r.game_id || "unknown",
    r.market_type || "moneyline",
    r.side || "home",
    r.taken_book || "paper",
  ];
  // Link hrefs go through lib/paperLinks.paperDetailHref (see its header for
  // the static-export encoding rules).
  return encodeURIComponent(parts.join("|"));
}
