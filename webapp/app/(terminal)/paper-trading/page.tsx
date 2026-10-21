// /paper-trading -- server entry. Reads the baked demo feeds at build time
// (paperTrading.server) and seeds the client page with them, so the exported HTML
// already carries the ledger as-of date and the counts; the client's first poll
// and polling are unchanged. Snapshot builds only: a live API build never shows the
// baked ledger as its record. Without baked files the client loads as before.
// The route title lives in layout.tsx. PAPER ONLY copy is in the client page.

import PaperTradingPageClient from "./PaperTradingPageClient";
import { isSnapshotMode } from "@/lib/fetchHonest";
import { loadBakedPaperPayload } from "./paperTrading.server";

export default function PaperTradingPage() {
  return <PaperTradingPageClient initial={isSnapshotMode ? loadBakedPaperPayload() : undefined} />;
}
