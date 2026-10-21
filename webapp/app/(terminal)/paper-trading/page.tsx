// /paper-trading -- server entry. Reads the baked demo feeds at build time
// (paperTrading.server) and seeds the client page with them, so the exported HTML
// already carries the ledger as-of date and the counts; the client's first poll
// and polling are unchanged. Without baked files the client loads as before.
// The route title lives in layout.tsx. PAPER ONLY copy is in the client page.

import PaperTradingPageClient from "./PaperTradingPageClient";
import { loadBakedPaperPayload } from "./paperTrading.server";

export default function PaperTradingPage() {
  return <PaperTradingPageClient initial={loadBakedPaperPayload()} />;
}
