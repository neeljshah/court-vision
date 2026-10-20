import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { FreshnessBadge } from "../Primitives";
import { api, isUnavailable } from "@/lib/p5api";

// ---------------------------------------------------------------------------
// Honesty-rail tests for LANE F (P6 dashboard). These gate the invariants:
//   * a stale/dead feed must NEVER read green 'fresh'
//   * a backend error degrades to the honest Unavailable sentinel
//   * no rendered component emits a $/pnl/roi/bankroll field (units only)
// ---------------------------------------------------------------------------

const HOUR_MS = 60 * 60 * 1000;

describe("FreshnessBadge tone -- stale reads amber, not green", () => {
  // Freshness-path rail: a backend that stamps status="ok"/"fresh" on a snapshot
  // whose asOf is actually hours old must NOT read green. The badge re-derives
  // the age locally and demotes the claimed-green to amber (stale-never-green).
  it("demotes a claimed-fresh status to amber when asOf is actually stale", () => {
    const old = new Date(Date.now() - 3 * HOUR_MS).toISOString();
    render(<FreshnessBadge asOf={old} status="ok" />);
    const pill = screen.getByText("ok");
    expect(pill.className).not.toContain("tier-a");
    expect(pill.className).toContain("amber");
  });

  it("keeps green when status=ok AND asOf is genuinely fresh", () => {
    const recent = new Date(Date.now() - 5_000).toISOString();
    render(<FreshnessBadge asOf={recent} status="ok" />);
    const pill = screen.getByText("ok");
    expect(pill.className).toContain("tier-a");
  });
});

describe("getJson -- backend errors degrade to Unavailable", () => {
  const realFetch = global.fetch;
  afterEach(() => {
    global.fetch = realFetch;
    vi.restoreAllMocks();
  });

  it("maps a non-ok (500) response to {status:'unavailable'}", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ should: "not be rendered" }),
    }) as unknown as typeof fetch;

    const res = await api.bestbets("nba");
    expect(isUnavailable(res)).toBe(true);
    expect((res as { reason?: string }).reason).toContain("500");
  });

  it("maps a non-JSON (HTML error page) response to Unavailable", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "text/html" }),
      json: async () => {
        throw new Error("not json");
      },
    }) as unknown as typeof fetch;

    const res = await api.bestbets("nba");
    expect(isUnavailable(res)).toBe(true);
  });
});

describe("no rendered component emits a $/pnl/roi/bankroll field", () => {
  it("source scan of components/p6 is clean of dollar/pnl/roi/bankroll output", () => {
    const testDir = dirname(fileURLToPath(import.meta.url));
    const dir = join(testDir, "..");
    const files = readdirSync(dir).filter((f) => f.endsWith(".tsx"));
    // forbid currency-symbol UI and the banned money field identifiers.
    const banned = /\bpnl\b|\bbankroll\b|\$\{?[a-zA-Z_]*?(pnl|roi|profit|dollars?)\b/i;
    const offenders: string[] = [];
    for (const f of files) {
      const src = readFileSync(join(dir, f), "utf8");
      if (banned.test(src)) offenders.push(f);
    }
    expect(offenders).toEqual([]);
  });
});

afterEach(() => vi.restoreAllMocks());
