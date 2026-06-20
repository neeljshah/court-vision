// games_depth.test.ts -- honesty + behavior guards for the games-lane depth.
//
// Source-scan: NO $-amount / pnl / roi / payout field across the games_depth
// sources, and the SHIP framing stays "vs_close UNPROVEN". Behavior: the soccer
// corners signal is the only SHIP; tennis is honestly blocked; the signal map
// degrades to an honest empty list for an unknown sport.

import { describe, it, expect } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { sportSignals } from "../sportSignals";

const HERE = dirname(fileURLToPath(import.meta.url));
const SRC_DIR = join(HERE, "..");

function gamesDepthSources(): string[] {
  return readdirSync(SRC_DIR)
    .filter((f) => f.endsWith(".ts") || f.endsWith(".tsx"))
    .map((f) => readFileSync(join(SRC_DIR, f), "utf8"));
}

describe("games_depth honesty rails", () => {
  it("declares no $-amount field name in any source", () => {
    // Forbid $-shaped FIELD names (object keys / identifiers). Honest prose such
    // as "no $/ROI/edge anywhere" is allowed; we only ban field-shaped usage:
    //   foo: <money> | foo=<money> | .pnl | "payout":
    const bannedKey =
      /\b(pnl|payout|dollars?|profit_usd|stake_usd|amount_usd|usd_amount)\b\s*[:=]/i;
    const bannedAccess = /\.(pnl|payout|profit_usd|stake_usd|amount_usd)\b/i;
    for (const src of gamesDepthSources()) {
      expect(bannedKey.test(src)).toBe(false);
      expect(bannedAccess.test(src)).toBe(false);
    }
  });

  it("has no literal dollar-amount tokens", () => {
    // No "$123" style amounts anywhere in the games_depth sources.
    const dollarAmount = /\$\s*\d/;
    for (const src of gamesDepthSources()) {
      expect(dollarAmount.test(src)).toBe(false);
    }
  });

  it("keeps the vs_close UNPROVEN framing present", () => {
    const blob = gamesDepthSources().join("\n");
    expect(/vs.?close UNPROVEN/i.test(blob)).toBe(true);
  });
});

describe("sportSignals catalog", () => {
  it("makes soccer corners the only SHIP and frames it calibration-only", () => {
    const soccer = sportSignals("soccer");
    const ships = soccer.filter((s) => s.verdict === "SHIP");
    expect(ships).toHaveLength(1);
    expect(ships[0].name.toLowerCase()).toContain("corners");
    expect(ships[0].stat.toUpperCase()).toContain("CALIBRATION");
  });

  it("treats soccer_intl with the soccer catalog", () => {
    expect(sportSignals("soccer_intl")).toEqual(sportSignals("soccer"));
  });

  it("keeps tennis honestly blocked (no SHIP)", () => {
    const tennis = sportSignals("tennis");
    expect(tennis.length).toBeGreaterThan(0);
    expect(tennis.every((s) => s.verdict === "TIER3_BLOCKED")).toBe(true);
  });

  it("returns an honest empty list for an unknown sport", () => {
    expect(sportSignals("cricket")).toEqual([]);
  });

  it("nba/mlb signals are all honest REJECTs (no fabricated edge)", () => {
    for (const sp of ["nba", "mlb"]) {
      const sigs = sportSignals(sp);
      expect(sigs.length).toBeGreaterThan(0);
      expect(sigs.every((s) => s.verdict === "REJECT")).toBe(true);
    }
  });
});
