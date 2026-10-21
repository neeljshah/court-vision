// Receipt labels do not establish gate-ledger provenance, even when vocabularies overlap.
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import index from "@/public/data/showcase/evidence_index.json";
import exhibit from "@/public/data/showcase/cf_star_removal.json";
import { ClaimIndex } from "@/components/evidence/ClaimIndex";
import { buildClaimIndex } from "@/lib/evidence.server";
import EvidencePage from "./page";

// jsdom has no router; prefetch is a Link-only prop, not an <a> attribute.
vi.mock("next/link", () => ({
  default: ({ href, children, prefetch: _prefetch, ...rest }: {
    href: string; children: React.ReactNode; prefetch?: boolean;
  }) => <a href={href} {...rest}>{children}</a>,
}));
afterEach(cleanup);

describe("/evidence claim index", () => {
  it("preserves the published descriptive exhibit label without inventing gate provenance", () => {
    render(<EvidencePage />);
    const claim = index.claims.find((c) => c.slug === "true-intelligence")!;
    expect(claim.strongest_receipt.source).toBe("scripts/platformkit/analytics_showcase/out/cf_star_removal.json");
    expect(claim.strongest_receipt.label).toBe(exhibit.label);
    const row = screen.getByRole("link", { name: /^True intelligence/ });
    expect(within(row).getByText("DESCRIPTIVE_ONLY")).toBeInTheDocument();
    expect(row).toHaveAttribute("href", "/evidence/true-intelligence/");
    expect(document.querySelector("[data-gate]")).toBeNull();
    expect(screen.queryByTestId("gate-status-legend")).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain("gate ledger status");
  });

  it("retains all published strongest-receipt labels", () => {
    render(<EvidencePage />);
    for (const claim of index.claims) {
      expect(document.body.textContent).toContain(claim.strongest_receipt.label);
    }
  });

  it("does not infer a gate result from a matching token with no source", () => {
    const data = buildClaimIndex({
      claims: [{ slug: "fixture", bucket: "Fixture", title: "Unclassified receipt",
        strongest_receipt: { source: null, label: "SHIP" } }],
    });
    render(<ClaimIndex data={data} />);
    expect(screen.getByText("SHIP")).toBeInTheDocument();
    expect(document.querySelector("[data-gate]")).toBeNull();
    expect(document.body.textContent).not.toContain("passed every gate");
  });
});
