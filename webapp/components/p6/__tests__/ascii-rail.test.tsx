// ascii-rail.test.tsx -- WS-A acceptance tests: zero non-ASCII characters in
// rendered output from the six owned components after the WS-A edit pass.
//
// For each component a minimal fixture is rendered and the DOM textContent is
// checked for any codepoint > U+007F.  Template-literal separators that changed
// from U+00B7 to ' | ' and em-dash fallbacks that changed to '--' and ellipsis
// that changed to '...' are all ASCII so they never trigger the check.
//
// HTML entities (&middot; &rarr;) emitted in JSX are resolved by jsdom into
// their Unicode equivalents; those are intentional characters owned by the
// component and are NOT checked here -- only raw text content that comes from
// component string literals (fallbacks, labels, separators) is the concern.
// However the task spec says "entity escapes are acceptable since SOURCE bytes
// become ASCII", and this test reflects that: we check the source bytes (via the
// static source-scan case) and are tolerant of jsdom entity resolution in the
// rendered-output cases.
//
// Source-level scan: every source file in the owned set is read as utf-8 bytes
// and scanned for codepoints > U+007F.  This is the hard gate.

import { describe, it, expect, vi } from "vitest";
import { render } from "@testing-library/react";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

// ---------------------------------------------------------------------------
// Stub: @/lib/store (TopBets uses useBets / useEVHistory)
// ---------------------------------------------------------------------------
vi.mock("@/lib/store", () => ({
  useBets: () => [],
  useEVHistory: () => [],
  useAlerts: () => [],
  useLastEventTs: () => null,
}));

// Stub: next/link (GameCard uses it; jsdom can't navigate)
vi.mock("next/link", () => ({
  default: ({ children, ...rest }: React.PropsWithChildren<Record<string, unknown>>) => (
    <a {...rest}>{children}</a>
  ),
}));

// Stub: @/components/depth (InfoTip)
vi.mock("@/components/depth", () => ({
  InfoTip: ({ ariaLabel }: { ariaLabel?: string; text?: string; term?: string }) => (
    <button aria-label={ariaLabel ?? "info"} />
  ),
}));

// Stub: @/components/games_depth (sportSignals)
vi.mock("@/components/games_depth", () => ({
  sportSignals: () => [],
}));

// Stub: @/lib/p5api (api / isUnavailable)
vi.mock("@/lib/p5api", () => ({
  api: {},
  isUnavailable: (v: unknown) => v != null && typeof v === "object" && (v as { status?: string }).status === "unavailable",
}));

// Stub: @/components/ui/button
vi.mock("@/components/ui/button", () => ({
  Button: ({ children, ...rest }: React.PropsWithChildren<Record<string, unknown>>) => (
    <button {...rest}>{children}</button>
  ),
}));

// Stub: @/components/ui/dialog
vi.mock("@/components/ui/dialog", () => ({
  Dialog: ({ children, open }: React.PropsWithChildren<{ open?: boolean }>) =>
    open ? <div role="dialog">{children}</div> : null,
  DialogContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogHeader: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogFooter: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  DialogTitle: ({ children }: React.PropsWithChildren) => <h2>{children}</h2>,
  DialogDescription: ({ children }: React.PropsWithChildren) => <p>{children}</p>,
}));

// ---------------------------------------------------------------------------
// Imports (after mocks)
// ---------------------------------------------------------------------------
import { TopBets } from "../../TopBets";
import { ClvScoreboard } from "../ClvScoreboard";
import { BestBets } from "../BestBets";

// ---------------------------------------------------------------------------
// Section 1: SOURCE-LEVEL SCAN (hard gate, per-file)
// ---------------------------------------------------------------------------

describe("WS-A ASCII rail -- source file scan (zero non-ASCII bytes)", () => {
  const thisDir = dirname(fileURLToPath(import.meta.url));

  // Owned files relative to the webapp root (two dirs above p6/__tests__)
  const webappRoot = join(thisDir, "..", "..", "..");

  const ownedFiles = [
    join(webappRoot, "components", "TopBets.tsx"),
    join(webappRoot, "app", "games", "GameCard.tsx"),
    join(webappRoot, "components", "p6", "ClvScoreboard.tsx"),
    join(webappRoot, "components", "p6", "GameReport.tsx"),
    join(webappRoot, "components", "p6", "PaperBetDialog.tsx"),
    join(webappRoot, "components", "p6", "BestBets.tsx"),
  ];

  for (const filePath of ownedFiles) {
    const shortName = filePath.split(/[\\/]/).slice(-2).join("/");
    it(`${shortName} -- zero codepoints > U+007F`, () => {
      const src = readFileSync(filePath, "utf8");
      const offenders: string[] = [];
      for (let i = 0; i < src.length; i++) {
        if (src.charCodeAt(i) > 127) {
          const lineNum = src.slice(0, i).split("\n").length;
          offenders.push(`char U+${src.charCodeAt(i).toString(16).toUpperCase().padStart(4, "0")} at line ${lineNum}`);
        }
      }
      expect(offenders, `Non-ASCII chars in ${shortName}: ${offenders.join(", ")}`).toEqual([]);
    });
  }
});

// ---------------------------------------------------------------------------
// Section 2: RENDER-LEVEL SMOKE -- no raw em-dash / middot / ellipsis in text
// ---------------------------------------------------------------------------
// Note: jsdom resolves &middot; -> U+00B7 and &rarr; -> U+2192 etc.
// Those are HTML entity *intent* expressed via ASCII source, and per the task
// spec "entity escapes are acceptable since SOURCE bytes become ASCII."
// So these render tests only verify that non-ASCII does NOT appear in
// TEXT THAT COMES FROM COMPONENT STRING LITERALS (fallbacks, labels, etc.).
// They allow the U+00B7 middot from &middot; and U+2192 from &rarr; but flag
// the historically-offending U+2014 em-dash, U+2026 ellipsis.

const BANNED_LITERAL_GLYPHS = /[—…]/; // em-dash, ellipsis

describe("WS-A ASCII rail -- TopBets empty state (no em-dash/ellipsis)", () => {
  it("empty-state text contains no em-dash or ellipsis glyphs", () => {
    const { container } = render(<TopBets />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(BANNED_LITERAL_GLYPHS);
  });
});

describe("WS-A ASCII rail -- ClvScoreboard empty/null state (no em-dash)", () => {
  it("unavailable state renders without em-dash or ellipsis", () => {
    const { container } = render(<ClvScoreboard clv={null} />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(BANNED_LITERAL_GLYPHS);
  });

  it("zero-bet settled state renders '--' not em-dash for fallback values", () => {
    const { container } = render(
      <ClvScoreboard
        clv={{
          n_bets: 0,
          pct_beat_close: null,
          mean_clv_pct: null,
          clv_is_proxy: false,
          by_sport: null,
        }}
      />,
    );
    const text = container.textContent ?? "";
    expect(text).not.toMatch(BANNED_LITERAL_GLYPHS);
    // '--' placeholder must appear (was previously the em-dash U+2014)
    expect(text).toMatch(/--/);
  });
});

describe("WS-A ASCII rail -- BestBets empty state (no em-dash)", () => {
  it("no-bets game renders without em-dash or ellipsis", () => {
    const { container } = render(
      <BestBets
        game={{ game_id: "test-001", status: "ok", best_bets: [] }}
        sport="nba"
      />,
    );
    const text = container.textContent ?? "";
    expect(text).not.toMatch(BANNED_LITERAL_GLYPHS);
  });

  it("below-floor summary line uses '--' separator not em-dash", () => {
    const { container } = render(
      <BestBets
        game={{
          game_id: "test-001",
          status: "ok",
          best_bets: [],
          candidates: [
            {
              market_type: "moneyline",
              side: "home",
              model_prob: 0.5,
              market_prob: 0.52,
              best_book: "dk",
              best_odds: 1.9,
              line: null,
              edge: -0.02,
              ev: -0.02,
              tier: null,
              decision: "no_bet",
              stake_units: 0,
              flat_unit: 0,
              kelly_units: 0,
              clv_is_proxy: false,
              reason: "below floor",
            },
          ],
        }}
        sport="nba"
      />,
    );
    const text = container.textContent ?? "";
    expect(text).not.toMatch(BANNED_LITERAL_GLYPHS);
    // The em-dash was replaced with '--' in the summary line
    expect(text).toMatch(/--\s*no bet/i);
  });
});
