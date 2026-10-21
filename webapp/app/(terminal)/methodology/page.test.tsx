import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { BANNED_COPY, RETRACTED_TOKENS } from "@/lib/packetVerdicts";
import MethodologyPage from "./page";

// Methodology (/methodology/): the first paragraph says what the page is, the packet verdict
// (never the retired "matches the close within noise" reading) and how to check; the retracted
// figures appear only inside the do-not-claim rail.

describe("Methodology page", () => {
  it("leads with what the page is, the packet verdict and how to check", () => {
    render(<MethodologyPage />);
    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1.textContent?.trim()).toBe("How every number here is checked");
    const lede = h1.nextElementSibling!;
    expect(lede.textContent).toMatch(/how a number earns a place on this site/);
    expect(lede.textContent).toMatch(/on MLB\s+moneyline and soccer over\/under 2\.5, and matches it on NBA moneyline only\s+where the sample is too small to tell/);
    expect(lede.textContent).toMatch(/only\s+where the sample is too small to tell/);
    expect(lede.textContent).toMatch(/run the one-command harness below/);
    expect(lede.textContent).not.toMatch(/within noise/i);
    expect(screen.getByRole("button", { name: "devigged close" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "retraction record" }))
      .toHaveAttribute("href", expect.stringMatching(/^\/evidence\/retractions\/?$/));
  });

  it("prints retracted figures only inside the do-not-claim rail, and no banned copy outside it", () => {
    const { container } = render(<MethodologyPage />);
    const rail = container.querySelector("#do-not-claim")!;
    for (const t of RETRACTED_TOKENS) expect(rail.textContent).toContain(t);
    rail.remove();
    // The no-edge banner is the one place outside the rail that negates the banned words.
    container.querySelector('[role="note"]')!.remove();
    const txt = container.textContent ?? "";
    for (const t of RETRACTED_TOKENS) expect(txt).not.toContain(t);
    expect(BANNED_COPY.test(txt)).toBe(false);
  });
});
