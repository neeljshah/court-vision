// page.test.tsx -- /graveyard/: the ledger-by-type table keeps its two vocabularies apart.
// Gate ledger tokens (SHIP, SHIP_REVIEW, WORSE, ...) render as GateStatus with their gloss,
// packet verdicts (REJECT, NOT_TESTABLE, ...) as VerdictLabel, and the page carries one legend
// for exactly the gate tokens present. Per-file vitest test (never the full suite).
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import rejects from "@/public/data/showcase/reject_graveyard.json";
import { GATE_GLOSS, gateStatusesIn, isPacketVerdict } from "@/components/evidence";
import GraveyardPage from "./page";

vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => <a href={href}>{children}</a>,
}));
afterEach(cleanup);

const verdicts = Object.keys((rejects as { verdicts_by_type: Record<string, number> }).verdicts_by_type);

describe("/graveyard ledger by type", () => {
  it("renders gate tokens as GateStatus, packet verdicts as VerdictLabel, and one legend for the tokens present", () => {
    render(<GraveyardPage />);
    const table = screen.getByTestId("ledger-by-type");
    const gates = gateStatusesIn(verdicts);
    expect(gates).toEqual(expect.arrayContaining(["SHIP", "SHIP_REVIEW", "WORSE"])); // the staged ledger holds gate tokens
    for (const t of gates) {
      const el = table.querySelector(`[data-gate="${t}"]`);
      expect(el).toHaveClass("ev-gate");
      expect(el).toHaveTextContent(GATE_GLOSS[t]);
      expect(el?.getAttribute("title")).toContain("gate ledger status, not a packet verdict");
    }
    for (const v of verdicts.filter(isPacketVerdict)) {
      expect(table.querySelector(`[data-verdict="${v}"]`)).toHaveClass("ev-verdict");
    }
    expect(table.querySelectorAll("[data-gate][data-verdict]").length).toBe(0);
    expect(table.querySelectorAll("tbody > tr").length).toBe(verdicts.length);

    const legend = screen.getByTestId("gate-status-legend");
    expect(legend.textContent).toMatch(/^Gate ledger statuses, not packet verdicts: /);
    for (const t of gates) expect(legend).toHaveTextContent(`${t} = ${GATE_GLOSS[t]}`);
    expect(legend).not.toHaveTextContent("REJECT");
    expect(screen.getAllByTestId("gate-status-legend").length).toBe(1);
  });
  it("leads in plain words, dates the heading, merges nba keys and glosses SHIP", () => {
    const { container } = render(<GraveyardPage />);
    expect(container.querySelector('[data-role="lead"]')!.textContent).toContain(
      "Every idea we tested is kept here, including the ones that failed. A 'confirmed' hypothesis held up in its own test; that is not the same as shipping, and none of the 60 candidate signal classes has passed the full market-relative gate.");
    expect(container.querySelector('[data-role="asof"]')!.textContent).toMatch(/as of \d{4}-\d{2}-\d{2}/);
    const heads = [...container.querySelectorAll("th")];
    expect(heads.find((h) => h.getAttribute("title") === "confirmed")!.textContent).toBe("Held up in its own test");
    expect(heads.some((h) => /^(null|total|survival)$/.test(h.textContent ?? ""))).toBe(false);
    const nbaRows = [...container.querySelectorAll("tbody tr")].filter((r) => r.querySelector("td")?.textContent === "NBA");
    expect(nbaRows.length).toBe(2); // one in the nulls table, one (merged) in the survival table
    const gloss = container.querySelector('[data-role="ship-gloss"]')!;
    expect(gloss.textContent).toContain(String((rejects as { verdicts_by_type: Record<string, number> }).verdicts_by_type.SHIP));
    expect(gloss.textContent).toContain("not signals shipped");
  });
});
