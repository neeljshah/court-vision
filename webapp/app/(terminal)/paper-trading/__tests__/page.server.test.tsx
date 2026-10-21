// page.server.test.tsx -- the server page seeds the client with the baked demo
// feeds, so the FIRST render (what the static export bakes into the HTML) carries
// the ledger as-of date and the settled count, never "loading" or "not stated".
// The build-time reader folds the files exactly like fetchPaperCombined: an
// unavailable sentinel stays a sentinel (null + reason), never a fabricated value.

import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { api } from "@/lib/p5api";
import PaperTradingPage from "../page";
import { PAPER_FEED_FILES, loadBakedPaperPayload } from "../paperTrading.server";
import { payloadAsOfMs, type CombinedPayload } from "../paperPayload";

vi.mock("@/components/paper/PaperEquityChart", () => import("./equityChartStub"));
// next/link stub -- jsdom has no router; prefetch is a Link-only prop, not an <a> attribute.
vi.mock("next/link", () => ({
  default: ({ href, children, prefetch: _prefetch, ...rest }: {
    href: string; children: React.ReactNode; prefetch?: boolean;
  }) => <a href={href} {...rest}>{children}</a>,
}));

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

const missing = { status: "unavailable" as const, reason: "test: feed withheld" };
const TRAIL = { as_of: "2026-10-09T06:00:00Z", status: "ok", count: 0, trail: [] };
/** The export's own as-of stamp; the PaperTrail type does not declare it (the page casts the same way). */
const asOfOf = (p: CombinedPayload) => ((p.trail ?? {}) as { as_of?: string }).as_of ?? "";
/** A fetch that never settles: the assertions are about the first render only. */
const pending = () => new Promise<never>(() => { /* never resolves */ });

function tempDir(files: Partial<Record<keyof typeof PAPER_FEED_FILES, string>>): string {
  const dir = mkdtempSync(join(tmpdir(), "paper-demo-"));
  for (const [key, text] of Object.entries(files)) {
    writeFileSync(join(dir, PAPER_FEED_FILES[key as keyof typeof PAPER_FEED_FILES]), text);
  }
  return dir;
}

describe("loadBakedPaperPayload", () => {
  it("reads the committed demo export: the trail is present and every feed is data or a reason, never both", () => {
    const payload = loadBakedPaperPayload();
    expect(payload).toBeDefined();
    const p = payload as CombinedPayload;
    expect(p.trail).not.toBeNull();
    expect(p.trail?.trail.length).toBe(p.trail?.count);
    for (const key of ["trail", "pmTrail", "clv", "pnl", "bankroll"] as const) {
      const hasData = p[key] !== null;
      const reason = p.errors?.[key];
      expect(hasData ? reason : typeof reason).toBe(hasData ? undefined : "string");
    }
    expect(payloadAsOfMs(p)).toBe(Date.parse(asOfOf(p)));
  });

  it("keeps sentinels as sentinels and reports an absent or unparsable secondary file honestly", () => {
    const dir = tempDir({
      trail: JSON.stringify(TRAIL),
      pmTrail: JSON.stringify({ status: "unavailable", reason: "no model probability per fill" }),
      pnl: "{ not json",
      bankroll: JSON.stringify({ start_units: 100, current_units: 100, updated_at: null }),
    });
    try {
      const p = loadBakedPaperPayload(dir) as CombinedPayload;
      expect(p.trail).toMatchObject({ count: 0 });
      expect(p.pmTrail).toBeNull();
      expect(p.errors?.pmTrail).toBe("no model probability per fill");
      expect(p.clv).toBeNull();
      expect(p.errors?.clv).toBe("not in the published snapshot");
      expect(p.pnl).toBeNull();
      expect(p.errors?.pnl).toMatch(/not valid JSON/);
      expect(p.bankroll).toMatchObject({ current_units: 100 });
      expect(p.errors?.bankroll).toBeUndefined();
      expect(payloadAsOfMs(p)).toBe(Date.parse(TRAIL.as_of));
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("seeds nothing when the primary trail file is absent", () => {
    const dir = tempDir({ clv: JSON.stringify(missing) });
    try {
      expect(loadBakedPaperPayload(dir)).toBeUndefined();
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("carries no as-of stamp for a trail that states none", () => {
    expect(payloadAsOfMs(undefined)).toBeUndefined();
    expect(payloadAsOfMs({ trail: null, pmTrail: null, clv: null, pnl: null, bankroll: null })).toBeUndefined();
  });
});

describe("PaperTradingPage (server) first render", () => {
  it("shows the baked as-of date and settled count synchronously, before any client fetch", () => {
    for (const m of ["getPaperTrail", "pmTrail", "getPaperClv", "getPaperPnlSeries", "getPaperBankroll"] as const) {
      vi.spyOn(api, m).mockReturnValue(pending());
    }
    const seed = loadBakedPaperPayload() as CombinedPayload;
    const asOf = asOfOf(seed).slice(0, 10);
    expect(asOf).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    const rows = seed.trail?.trail ?? [];
    const settled = rows.filter((r) => r.graded && r.status !== "open").length;

    render(<PaperTradingPage />);

    const intro = screen.getByTestId("paper-record-intro");
    expect(intro).toHaveTextContent(`ledger as of ${asOf}`);
    expect(intro).not.toHaveTextContent("not stated");
    expect(screen.getByText(`${settled} settled / ${rows.length} total`)).toBeInTheDocument();
    expect(screen.queryByText("loading")).not.toBeInTheDocument();
    expect(screen.getByTestId("real-money-deny-banner")).toHaveTextContent("PAPER ONLY");
  });
});
