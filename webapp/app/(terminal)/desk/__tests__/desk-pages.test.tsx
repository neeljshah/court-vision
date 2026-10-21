// desk-pages.test.tsx -- Lane D (2026-10-20): the /desk Record hub and /desk/health
// render from the staged export + committed receipts, carry an as-of on every panel,
// never read the viewer clock, and use no banned word.
import { describe, it, expect, vi, afterEach } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { render, screen, cleanup, within } from "@testing-library/react";
import DeskRecordPage from "../page";
import DeskHealthPage from "../health/page";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a>,
}));
afterEach(cleanup);

const BANNED = /\b(edge|roi|profit|beats|money)\b/i;
const VIEWER_CLOCK = /just now|\d+s ago|\d{1,2}:\d{2}:\d{2}\s?(AM|PM)/;
const src = (rel: string) => readFileSync(join(process.cwd(), rel), "utf-8");

function commonRails() {
  const text = document.body.textContent ?? "";
  expect(text).not.toMatch(BANNED);
  expect(text).not.toMatch(VIEWER_CLOCK);
  const stamps = screen.getAllByTestId("section-asof");
  expect(stamps.length).toBeGreaterThan(3);
  for (const s of stamps) expect(s.textContent).toMatch(/^as of (\d{4}-\d{2}-\d{2}|: not stated in the receipt)$/);
  expect(screen.getByTestId("desk-dates").textContent).toMatch(/2026-09-24[\s\S]*2026-10-03[\s\S]*2026-10-06/);
}

describe("/desk Record hub", () => {
  it("renders the census COVERAGE_LOW cause as a gate ledger status with its legend, never as a verdict", () => {
    render(<DeskRecordPage />);
    const census = screen.getByTestId("census-summary");
    const el = census.querySelector('[data-gate="COVERAGE_LOW"]');
    expect(el).toHaveClass("ev-gate");
    expect(el?.getAttribute("title")).toBe("COVERAGE_LOW: too little coverage. gate ledger status, not a packet verdict.");
    expect(census.querySelector('[data-verdict="COVERAGE_LOW"]')).toBeNull();
    expect(within(census).getByTestId("gate-status-legend").textContent)
      .toBe("Gate ledger statuses, not packet verdicts: COVERAGE_LOW = too little coverage.");
    expect(census.textContent).toMatch(/COVERAGE_LOW: 23 games/);
  });

  it("renders the status card, compact scoreboard, census, receipts and NotClaimed", () => {
    render(<DeskRecordPage />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Paper desk record");
    const status = screen.getByTestId("desk-status-card").textContent ?? "";
    expect(status).toMatch(/Last scored night\s*\d{4}-\d{2}-\d{2} (COMPLETE|PARTIAL)/);
    expect(status).toMatch(/\d+ of \d+ days/);
    expect(status).toMatch(/pct of days, window 2026-09-24 to 2026-10-18/);
    expect(status).toMatch(/min before the export was generated/);
    // one row per (sport, arm), INSUFFICIENT kept, per-cell detail behind <details>
    const table = screen.getByTestId("scoreboard-compact");
    const body = table.querySelectorAll(":scope > tbody > tr");
    expect(body.length).toBeLessThan(40);
    expect(table.textContent).toMatch(/INSUFFICIENT/);
    expect(table.querySelectorAll(":scope > tbody > tr > td > details").length).toBe(body.length);
    const census = screen.getByTestId("census-summary").textContent ?? "";
    expect(census).toMatch(/never judged: 79 games/);
    expect(census).toMatch(/no capture: 11 games/);
    expect(census).toMatch(/COVERAGE_LOW: 23 games/);
    expect(census).toMatch(/79 \+ 11 \+ 23 = 113/);
    const links = within(screen.getByTestId("night-receipt-links")).getAllByRole("link");
    expect(links[0].getAttribute("href")).toMatch(
      /^https:\/\/github\.com\/neeljshah\/court-vision\/blob\/master\/docs\/evidence\/forward\/nights\/\d{4}-\d{2}-\d{2}\.json$/);
    expect(screen.getByTestId("desk-not-claimed")).toBeTruthy();
    commonRails();
  });
});

describe("/desk/health", () => {
  it("renders heartbeats, uptime table, check_all count and open issues with reasons", () => {
    render(<DeskHealthPage />);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toBe("Desk health");
    const text = document.body.textContent ?? "";
    expect(text).toMatch(/heartbeat:books_root/);
    expect(text).toMatch(/Live shadow recorder:/);
    expect(text).toMatch(/Window 2026-09-24 to 2026-10-18 \(25 days\)/);
    expect(screen.getByTestId("check-all-count").textContent).toMatch(/\d+ of \d+ module self-checks PASS/);
    expect(screen.getByTestId("open-issues").textContent).toMatch(/\d+ open of \d+ issues/);
    commonRails();
  });
});

describe("source rails", () => {
  it("desk sources never read the viewer clock", () => {
    for (const f of ["app/(terminal)/desk/page.tsx", "app/(terminal)/desk/health/page.tsx",
      "components/desk/DeskStatus.tsx", "components/desk/deskExtras.server.ts", "components/desk/ScoreboardCompact.tsx"]) {
      expect(src(f)).not.toMatch(/Date\.now\(|new Date\(\)|toLocaleTimeString/);
    }
  });
});
