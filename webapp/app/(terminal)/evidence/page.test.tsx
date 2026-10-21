// page.test.tsx -- /evidence/: a strongest-receipt label that is a gate ledger token (the
// staged index carries DESCRIPTIVE_ONLY) renders as GateStatus, other labels stay plain text,
// and the page shows one legend for exactly the gate tokens present. Per-file vitest test.
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import index from "@/public/data/showcase/evidence_index.json";
import { GATE_GLOSS, gateStatusesIn, isGateStatus } from "@/components/evidence";
import EvidencePage from "./page";

// jsdom has no router; prefetch is a Link-only prop, not an <a> attribute.
vi.mock("next/link", () => ({
  default: ({ href, children, prefetch: _prefetch, ...rest }: {
    href: string; children: React.ReactNode; prefetch?: boolean;
  }) => <a href={href} {...rest}>{children}</a>,
}));
afterEach(cleanup);

type Claim = { strongest_receipt?: { label?: string | null } | null };
const labels = ((index as { claims: Claim[] }).claims ?? []).map((c) => c.strongest_receipt?.label ?? "");
const gates = gateStatusesIn(labels);

describe("/evidence claim index", () => {
  it("renders gate ledger labels as GateStatus and carries one legend for exactly those tokens", () => {
    render(<EvidencePage />);
    expect(gates).toContain("DESCRIPTIVE_ONLY"); // the staged index carries one
    for (const t of gates) {
      const chips = document.querySelectorAll(`[data-gate="${t}"]`);
      expect(chips.length).toBe(labels.filter((l) => l === t).length);
      for (const el of chips) {
        expect(el).toHaveClass("ev-gate");
        expect(el.getAttribute("title")).toBe(`${t}: ${GATE_GLOSS[t]}. gate ledger status, not a packet verdict.`);
      }
    }
    expect(document.querySelectorAll("[data-gate]").length).toBe(labels.filter(isGateStatus).length);
    const legend = screen.getByTestId("gate-status-legend");
    expect(legend.textContent).toBe(
      `Gate ledger statuses, not packet verdicts: ${gates.map((t) => `${t} = ${GATE_GLOSS[t]}`).join("; ")}.`,
    );
    expect(screen.getAllByTestId("gate-status-legend").length).toBe(1);
    // a plain label is still printed as text, not as a chip
    const plain = labels.find((l) => l && !isGateStatus(l));
    if (plain) expect(document.body.textContent).toContain(plain);
  });
});
