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
});
