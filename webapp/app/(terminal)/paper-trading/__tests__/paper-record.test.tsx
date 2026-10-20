// paper-record.test.tsx -- Lane D (2026-10-20): /paper-trading renamed "Paper record":
// settled book first, July 2026 panels boxed, as-of from the export, copy rails.
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, waitFor, cleanup } from "@testing-library/react";
import { api } from "@/lib/p5api";
import type { PaperTrailRow } from "@/lib/p5api";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a>,
}));

const ROW: PaperTrailRow = {
  game_id: "KXNBAGAME-26OCT08ATLSAS", matchup: "KXNBAGAME-26OCT08ATLSAS-ATL", sport: "nba", side: "no",
  market_type: "kalshi_ingame_contract", line: null, taken_book: "kalshi", taken_decimal: 1.11,
  model_prob: null, model_ev: null, tier: null, stake_units: 0.23, status: "settled", graded: true,
  outcome: "win", clv_pct: null, beat_close: null, clv_is_proxy: false, clv_status: "no_close",
  clv_unavailable: true, clv_note: null, executed: false, ts: "2026-10-09T00:51:29Z", settled_at: null,
};
const sentinel = (reason: string) => ({ status: "unavailable" as const, reason });

function mockExport() {
  vi.spyOn(api, "getPaperTrail").mockResolvedValue({
    status: "ok", count: 1, trail: [ROW], as_of: "2026-10-09T06:00:00Z", last_night: "2026-10-08",
  } as never);
  vi.spyOn(api, "pmTrail").mockResolvedValue({ status: "ok", count: 0, generated_at: null, trades: [] } as never);
  vi.spyOn(api, "getPaperClv").mockResolvedValue(sentinel("no closing price per fill") as never);
  vi.spyOn(api, "getPaperPnlSeries").mockResolvedValue(sentinel("count ledger, no unit ledger") as never);
  vi.spyOn(api, "getPaperBankroll").mockResolvedValue(sentinel("no unit bankroll") as never);
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

async function renderPage() {
  const { default: Page } = await import("../page");
  return render(<Page />);
}

// A banned word may appear only inside a negation ("No edge is claimed", "Real-money: DENY").
const BANNED = /\b(edge|roi|profit|beats|money)\b/i;
const positiveBanned = (text: string) =>
  text.split(/(?<=[.!?])\s+/).filter((t) => BANNED.test(t) && !/\b(no|not|deny|denied)\b/i.test(t));

describe("/paper-trading -- Paper record", () => {
  it("h1 is Paper record", async () => {
    mockExport();
    const { container } = await renderPage();
    expect(container.querySelector("h1")?.textContent).toBe("Paper record");
  });

  it("settled book renders before the boxed July 2026 snapshot", async () => {
    mockExport();
    const { container } = await renderPage();
    await waitFor(() => expect(screen.getByRole("status", { name: "Unavailable paper data" })).toBeInTheDocument());
    const html = container.innerHTML;
    const settled = html.indexOf("Settled book (real paper record)");
    expect(settled).toBeGreaterThan(-1);
    expect(settled).toBeLessThan(html.indexOf("july-snapshot-box"));
    const box = screen.getByTestId("july-snapshot-box");
    expect(box.textContent).toMatch(/July 2026 model snapshot, simulated units/);
    expect(box.textContent).toMatch(/as of\s+2026-07-16/);
    // the sentinel reasons render inside the box, never a balance figure
    expect(box.textContent).toMatch(/count ledger, no unit ledger/);
    expect(screen.queryByTestId("paper-equity-chart")).not.toBeInTheDocument();
  });

  it("intro carries the ledger as-of, last night and source from the export", async () => {
    mockExport();
    await renderPage();
    await waitFor(() => {
      const intro = screen.getByTestId("paper-record-intro").textContent ?? "";
      expect(intro).toMatch(/ledger as of 2026-10-09/);
      expect(intro).toMatch(/night 2026-10-08/);
      expect(intro).toMatch(/paper_result\/LEDGER\.jsonl/);
    });
  });

  it("no viewer-clock stamp and no banned word outside a negation", async () => {
    mockExport();
    await renderPage();
    await waitFor(() => expect(screen.getByTestId("no-paper-trades")).toBeInTheDocument());
    const text = document.body.textContent ?? "";
    expect(text).not.toMatch(/just now|\d{1,2}:\d{2}:\d{2}\s?(AM|PM)/);
    expect(positiveBanned(text)).toEqual([]);
  });
});
