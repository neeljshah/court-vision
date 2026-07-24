// Shared scoreboard-verdict -> honesty-token mapping. ONE source of truth so the
// same cross_sport_scoreboard row never renders two different dots on two pages
// (the Home bento cell used to hardcode "not_testable" while the Forecaster table
// derived "pending" from this rule). PROVISIONAL is tested first: a provisional
// delta is never a settled "confirmed", so it renders the hollow "pending" dot
// regardless of direction. UNDERPOWERED is inconclusive (caution/not_testable),
// not a measured null.
import type { Verdict } from "@/components/analytics/VerdictDot";

export function vtok(v: string): Verdict {
  return v.includes("PROVISIONAL")
    ? "pending"
    : v.includes("UNDERPOWERED")
    ? "not_testable"
    : v.startsWith("MODEL_SHARPER")
    ? "confirmed"
    : v.startsWith("MARKET_SHARPER")
    ? "not_testable"
    : "null";
}
