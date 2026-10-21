// paperTrading.server.ts -- build-time reader of the baked /paper-trading feeds.
// The static export's client fetch resolves to these same files (the slug that
// lib/fetchHonest.snapshotPath derives from each GET), so reading them here lets
// the server render the baked values: the exported HTML carries the ledger as-of
// date and the counts instead of "loading" and "not stated" until the client fetch
// lands. Same pattern as lib/desk.server.ts: readFileSync at build time. A missing
// or unreadable secondary file is the same honest Unavailable sentinel the client
// would get, never an empty value; without the primary trail file there is nothing
// to seed and the client path is unchanged. PAPER ONLY copy lives in the components.

import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { PaperTrail, PmTrail, ClvScoreboard } from "@/lib/p5api";
import type { PnlSeries, PaperBankroll, Unavailable } from "@/lib/types";
import { combinePaperPayload, type CombinedPayload } from "./paperPayload";

export const DEMO_DATA_DIR = join(process.cwd(), "public", "demo-data");

/** Baked file per feed, exactly as the exporter slugs the client's GET paths. */
export const PAPER_FEED_FILES = {
  trail: "api_paper_trail_limit_400.json",
  pmTrail: "api_paper_pm_trail.json",
  clv: "api_paper_clv.json",
  pnl: "api_paper_pnl_series.json",
  bankroll: "api_paper_bankroll.json",
} as const;

/** The reason the client reports for a GET the exporter never wrote (lib/fetchHonest). */
const NOT_EXPORTED: Unavailable = { status: "unavailable", reason: "not in the published snapshot" };

/** undefined = file absent; a present but unparsable file is an explicit sentinel. */
function readFeed<T>(dir: string, file: string): T | Unavailable | undefined {
  let text: string;
  try {
    text = readFileSync(join(dir, file), "utf-8");
  } catch {
    return undefined;
  }
  try {
    return JSON.parse(text) as T | Unavailable;
  } catch {
    return { status: "unavailable", reason: `baked file ${file} is not valid JSON` };
  }
}

/**
 * Assemble the same CombinedPayload fetchPaperCombined builds, from the baked files.
 * Returns undefined when the primary trail file is absent (nothing to seed).
 */
export function loadBakedPaperPayload(dir: string = DEMO_DATA_DIR): CombinedPayload | undefined {
  const trail = readFeed<PaperTrail>(dir, PAPER_FEED_FILES.trail);
  if (trail === undefined) return undefined;
  return combinePaperPayload(
    trail,
    readFeed<PmTrail>(dir, PAPER_FEED_FILES.pmTrail) ?? NOT_EXPORTED,
    readFeed<ClvScoreboard>(dir, PAPER_FEED_FILES.clv) ?? NOT_EXPORTED,
    readFeed<PnlSeries>(dir, PAPER_FEED_FILES.pnl) ?? NOT_EXPORTED,
    readFeed<PaperBankroll>(dir, PAPER_FEED_FILES.bankroll) ?? NOT_EXPORTED,
  );
}
