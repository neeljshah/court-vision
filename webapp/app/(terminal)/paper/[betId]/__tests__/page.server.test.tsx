// page.server.test.tsx -- the server page seeds the client with the page's OWN baked fill
// in snapshot mode, so the FIRST render (what the static export bakes into the HTML) carries
// the fill's as-of date, contracts, probability and status plus the PAPER ONLY banner, never
// "not stated" or "loading". A live build seeds nothing; an id outside the baked trail seeds
// nothing; the seed is a one-row trail that invents no value.
// Per-file vitest test (never the full suite).

import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import trail from "@/public/demo-data/api_paper_trail_limit_400.json";
import { api, type PaperTrailRow } from "@/lib/p5api";
import { fillParam, fillSeedTrail } from "@/components/paper_pm/paperIds";
import { bakedFillSeed } from "@/components/paper_pm/bakedFillParams.server";
import BetDetailPage from "../page";

const mode = vi.hoisted(() => ({ snapshot: true, betId: "" }));
vi.mock("@/lib/fetchHonest", async (orig) => ({
  ...(await orig<typeof import("@/lib/fetchHonest")>()),
  get isSnapshotMode() { return mode.snapshot; },
}));
// jsdom has no app router: the client reads the same param the server page received.
vi.mock("next/navigation", () => ({ useParams: () => ({ betId: mode.betId }) }));
vi.mock("next/link", () => ({
  default: ({ href, children, prefetch: _prefetch, ...rest }: {
    href: string; children: React.ReactNode; prefetch?: boolean;
  }) => <a href={href} {...rest}>{children}</a>,
}));

afterEach(() => { cleanup(); vi.restoreAllMocks(); mode.snapshot = true; });

const baked = trail as unknown as { as_of: string; trail: PaperTrailRow[] };
const first = baked.trail[0];
/** A fetch that never settles: the assertions are about the first render only. */
const pending = () => new Promise<never>(() => { /* never resolves */ });
const prob = (p: number | null | undefined) => (p != null ? `${(p * 100).toFixed(1)}%` : "--");

describe("bakedFillSeed", () => {
  it("resolves every baked fill by its exported param, with the export's own as_of", () => {
    expect(baked.trail.length).toBeGreaterThan(0);
    for (const row of baked.trail) {
      const seed = bakedFillSeed(fillParam(row));
      expect(seed?.row).toEqual(row);
      expect(seed?.asOf).toBe(baked.as_of);
    }
    // The param may reach the page with one more layer encoded, or fully decoded.
    expect(bakedFillSeed(encodeURIComponent(fillParam(first)))?.row).toEqual(first);
    expect(bakedFillSeed(decodeURIComponent(fillParam(first)))?.row).toEqual(first);
  });

  it("seeds nothing for an unknown id or an absent/unparsable file, and no as_of when the export states none", () => {
    expect(bakedFillSeed(encodeURIComponent(`${first.sport}|${first.game_id}|nope`))).toBeUndefined();
    expect(bakedFillSeed(fillParam(first), join(tmpdir(), "no-such-trail.json"))).toBeUndefined();
    const dir = mkdtempSync(join(tmpdir(), "paper-fill-"));
    try {
      const file = join(dir, "trail.json");
      writeFileSync(file, JSON.stringify({ status: "ok", count: 1, trail: [first] }));
      expect(bakedFillSeed(fillParam(first), file)).toEqual({ row: first, asOf: null });
      writeFileSync(file, "{ not json");
      expect(bakedFillSeed(fillParam(first), file)).toBeUndefined();
    } finally {
      rmSync(dir, { recursive: true, force: true });
    }
  });

  it("fillSeedTrail is a one-row trail that carries as_of only when the export states one", () => {
    expect(fillSeedTrail({ row: first, asOf: "2026-10-09T06:00:00Z" }))
      .toEqual({ status: "ok", count: 1, trail: [first], as_of: "2026-10-09T06:00:00Z" });
    expect(fillSeedTrail({ row: first, asOf: null })).toEqual({ status: "ok", count: 1, trail: [first] });
  });
});

describe("BetDetailPage (server) first render", () => {
  it("shows the baked as-of, contracts, probability, status and the PAPER ONLY banner before any client fetch", () => {
    vi.spyOn(api, "getPaperTrail").mockReturnValue(pending());
    mode.betId = fillParam(first);
    render(<BetDetailPage params={{ betId: fillParam(first) }} />);

    const badge = screen.getByTestId("bet-detail-last-updated");
    expect(badge).toHaveTextContent(`as of ${baked.as_of.slice(0, 10)}`);
    expect(badge).not.toHaveTextContent("not stated");
    expect(screen.queryByText("loading...")).not.toBeInTheDocument();
    expect(screen.queryByText(/trade not found/)).not.toBeInTheDocument();
    expect(screen.getByTestId("detail-units")).toHaveTextContent(`${(first.stake_units as number).toFixed(2)}u`);
    expect(screen.getByTestId("detail-model-prob")).toHaveTextContent(prob(first.model_prob));
    expect(screen.getByTestId("detail-line")).toHaveTextContent((first.taken_decimal as number).toFixed(2));
    expect(screen.getByTestId("detail-result")).toHaveTextContent(first.status === "open" || !first.graded ? "pending" : /win|loss|void/);
    expect(screen.getByTestId("detail-selection")).toBeInTheDocument();
    const banner = screen.getByTestId("real-money-deny-banner");
    expect(banner).toHaveTextContent("PAPER ONLY");
    expect(banner).toHaveAttribute("role", "alert");
    expect(document.body.textContent).not.toMatch(/\$\s*\d/);
  });

  it("seeds nothing on a live (non-snapshot) build: the client loads as before, banner still shown", () => {
    mode.snapshot = false;
    vi.spyOn(api, "getPaperTrail").mockReturnValue(pending());
    mode.betId = fillParam(first);
    render(<BetDetailPage params={{ betId: fillParam(first) }} />);
    expect(screen.getByTestId("bet-detail-last-updated")).toHaveTextContent("checking");
    expect(screen.getByText("loading...")).toBeInTheDocument();
    expect(screen.getByTestId("real-money-deny-banner")).toHaveTextContent("PAPER ONLY");
  });

  it("seeds nothing for an id outside the baked trail (the export never writes such a page)", () => {
    vi.spyOn(api, "getPaperTrail").mockReturnValue(pending());
    const unknown = encodeURIComponent("nba|KXNBAGAME-NONE|no|2026-10-09T00:00:00Z|1");
    mode.betId = unknown;
    render(<BetDetailPage params={{ betId: unknown }} />);
    expect(screen.getByTestId("bet-detail-last-updated")).toHaveTextContent("as of not stated");
    expect(screen.getByText("loading...")).toBeInTheDocument();
  });
});
