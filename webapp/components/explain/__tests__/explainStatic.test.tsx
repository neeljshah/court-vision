// Static build (NEXT_PUBLIC_DATA_MODE=snapshot): no live-endpoint pills, no loader text, the parity
// pointer line instead; the reworded how-it-works copy.
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

afterEach(() => { vi.unstubAllEnvs(); vi.resetModules(); });

async function load() {
  vi.stubEnv("NEXT_PUBLIC_DATA_MODE", "snapshot");
  vi.resetModules();
  vi.doMock("@/lib/api", async (orig) => ({ ...(await orig<object>()), getParityHeadline: vi.fn(() => new Promise(() => {})), getProductStatus: vi.fn(() => new Promise(() => {})) }));
  return {
    ...(await import("../WhatAmILookingAt")),
    ...(await import("../SelfImproveExplainer")),
    ...(await import("../HonestFindings")),
    ...(await import("../funnelStages")),
    ...(await import("../LiveExample")),
    HowItWorksPage: (await import("@/app/(terminal)/how-it-works/page")).default,
  };
}

describe("how-it-works on the static build", () => {
  it("describes recorded findings and snapshot destinations without a live health claim", async () => {
    const m = await load();
    render(<m.HowItWorksPage />);
    const findings = screen.getByLabelText("honest findings").textContent;
    expect(findings).not.toMatch(/FULLY GREEN|live grid/);
    expect(findings).toContain("recorded deep-data gate artifacts");
    expect(screen.getByRole("link", { name: "Explore the Games snapshot" })).toHaveAttribute("href", "/games");
    expect(screen.getByRole("link", { name: "Inspect Desk health" })).toHaveAttribute("href", "/desk/health");
  });

  it("hides the status pills and shows the parity pointer", async () => {
    const m = await load();
    const { container } = render(<><m.WhatAmILookingAt /><m.SelfImproveExplainer /><m.LiveExample /></>);
    expect(container.textContent).not.toMatch(/status unknown/i);
    expect(container.textContent).not.toContain("Loading a soccer example");
    expect(screen.getByTestId("parity-static").textContent).toBe("Parity status is shown on the Desk health page with its as-of date.");
  });

  it("carries the reworded yardstick, signals and controls copy", async () => {
    const m = await load();
    const all = JSON.stringify(m.FUNNEL_STAGE_DETAIL);
    expect(all).toContain("Brier score against the devigged close is the pregame yardstick; closing-line value cannot be measured yet.");
    expect(all).toContain("Candidate signals from 60 classes, each gated leak-free; none has shipped.");
    expect(all).not.toMatch(/only honest yardstick|Hundreds of per-player/);
    const { container } = render(<m.HonestFindings />);
    expect(container.textContent).toContain("cleared every control listed above");
  });
});
