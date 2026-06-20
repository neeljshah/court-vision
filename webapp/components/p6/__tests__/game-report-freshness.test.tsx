// game-report-freshness.test.tsx
// Verifies that GameReport's LiveFreshnessPill correctly handles the
// three freshness states without violating the stale-never-green rail:
//   absent  (null/missing as_of)  -> neutral slate "no live feed", NEVER red
//   stale   (old valid as_of)     -> red "STALE ...", kept as-is
//   fresh   (recent valid as_of)  -> green "fresh ..."
//
// Rail: absent is a MISSING-DATA state, not an error. Only a genuinely old
// timestamp drives the red/stale branch. stale-never-green is preserved for
// the real stale case.

import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { GameReport } from "../GameReport";
import type { Report } from "@/lib/types";

// ---------------------------------------------------------------------------
// Minimal Report fixture builder
// ---------------------------------------------------------------------------

function makeReport(metaAsOf: string | null | undefined, liveAsOf?: string | null): Report {
  return {
    status: "ok",
    sport: "nba",
    game_id: "test-game-001",
    pregame: {
      home: "LAL",
      away: "BOS",
      model_probs: { home: 0.55, away: 0.45 },
    },
    markets: [],
    live: liveAsOf !== undefined
      ? { status: "live", state: "live", as_of: liveAsOf ?? undefined }
      : undefined,
    meta: {
      as_of: metaAsOf,
    },
  };
}

const HOUR_MS = 60 * 60 * 1_000;

// ---------------------------------------------------------------------------
// Header freshness pill (meta.as_of)
// ---------------------------------------------------------------------------

describe("GameReport -- header LiveFreshnessPill (meta.as_of)", () => {
  it("absent meta.as_of renders neutral 'no live feed', NOT red", () => {
    const { container } = render(<GameReport report={makeReport(null)} />);
    // The text should appear somewhere in the rendered output
    const text = container.textContent ?? "";
    expect(text).toMatch(/no live feed/i);
    // Must not render the fallback red text "no feed timestamp" (old rail)
    expect(text).not.toMatch(/no feed timestamp/i);
    // The badge element for "no live feed" must not carry a red class
    const badges = container.querySelectorAll("[class*='red']");
    const redTexts = Array.from(badges).map((el) => el.textContent ?? "");
    const hasRedAbsent = redTexts.some((t) => /no live feed/i.test(t));
    expect(hasRedAbsent).toBe(false);
  });

  it("stale meta.as_of (hours old) renders red STALE badge", () => {
    const staleTs = new Date(Date.now() - 2 * HOUR_MS).toISOString();
    const { container } = render(<GameReport report={makeReport(staleTs)} />);
    const text = container.textContent ?? "";
    expect(text).toMatch(/STALE/);
    // At least one red-class element must contain "STALE"
    const badges = container.querySelectorAll("[class*='red']");
    const redTexts = Array.from(badges).map((el) => el.textContent ?? "");
    const hasRedStale = redTexts.some((t) => /STALE/i.test(t));
    expect(hasRedStale).toBe(true);
  });

  it("fresh meta.as_of (seconds old) renders 'fresh' badge (not stale, not no-live-feed)", () => {
    const freshTs = new Date(Date.now() - 5_000).toISOString();
    const { container } = render(<GameReport report={makeReport(freshTs)} />);
    const text = container.textContent ?? "";
    // "fresh" text must appear
    expect(text).toMatch(/fresh/i);
    // Neither the stale-error branch nor the absent-neutral branch should fire
    expect(text).not.toMatch(/STALE/);
    expect(text).not.toMatch(/no live feed/i);
    // The fresh badge must not carry any red tone class (stale-never-green rail)
    const badges = container.querySelectorAll("[class*='red']");
    const redTexts = Array.from(badges).map((el) => el.textContent ?? "");
    const hasRedFresh = redTexts.some((t) => /fresh/i.test(t));
    expect(hasRedFresh).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// In-game freshness pill (live.as_of)
// ---------------------------------------------------------------------------

describe("GameReport -- in-game LiveFreshnessPill (live.as_of)", () => {
  it("absent live.as_of renders neutral 'no live feed', NOT red", () => {
    const { container } = render(<GameReport report={makeReport(null, null)} />);
    const text = container.textContent ?? "";
    expect(text).toMatch(/no live feed/i);
    // The absent-timestamp badge must never be red
    const badges = container.querySelectorAll("[class*='red']");
    const redTexts = Array.from(badges).map((el) => el.textContent ?? "");
    const hasRedAbsent = redTexts.some((t) => /no live feed/i.test(t));
    expect(hasRedAbsent).toBe(false);
  });

  it("stale live.as_of renders red STALE badge", () => {
    const staleTs = new Date(Date.now() - 2 * HOUR_MS).toISOString();
    const { container } = render(<GameReport report={makeReport(staleTs, staleTs)} />);
    const text = container.textContent ?? "";
    expect(text).toMatch(/STALE/);
  });
});

// ---------------------------------------------------------------------------
// Source-level: absent branch no longer uses "no feed timestamp" text
// ---------------------------------------------------------------------------

describe("GameReport -- source no longer contains 'no feed timestamp' literal", () => {
  it("the old absent-text literal is gone from the source file", () => {
    const { readFileSync } = require("node:fs");
    const { join, dirname } = require("node:path");
    const { fileURLToPath } = require("node:url");
    const thisDir = dirname(fileURLToPath(import.meta.url));
    const src = readFileSync(
      join(thisDir, "..", "GameReport.tsx"),
      "utf8",
    ) as string;
    expect(src).not.toMatch(/no feed timestamp/);
    // New neutral text must be present
    expect(src).toMatch(/no live feed/);
    // "absent" state must be in the return type
    expect(src).toMatch(/"absent"/);
  });
});
