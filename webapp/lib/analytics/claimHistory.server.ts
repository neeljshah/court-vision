import { readFileSync } from "node:fs";
import { join } from "node:path";
import { buildClaimHistory, type ClaimHistoryLedger } from "./claimHistory";

/** Reads the committed scoreboard at build time; browser code receives parsed values only. */
export function loadClaimHistory(): ClaimHistoryLedger {
  const path = join(process.cwd(), "public", "data", "showcase", "fwd_claim_scoreboard.json");
  return buildClaimHistory(JSON.parse(readFileSync(path, "utf-8")) as unknown);
}
