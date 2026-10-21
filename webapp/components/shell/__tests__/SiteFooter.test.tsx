import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SiteFooter } from "../SiteFooter";

describe("SiteFooter", () => {
  it("carries contact, evidence links and the snapshot dates", () => {
    render(<SiteFooter dates={{ modelAsOf: "2026-07-16", deskThrough: "2026-10-16" }} />);
    expect(screen.getByRole("link", { name: "neeljshah22@gmail.com" })).toHaveAttribute("href", "mailto:neeljshah22@gmail.com");
    expect(screen.getByRole("link", { name: "Portfolio" })).toHaveAttribute("href", "https://neelshahportfolio.netlify.app/");
    expect(screen.getByRole("link", { name: "GitHub" })).toHaveAttribute("href", "https://github.com/neeljshah/court-vision");
    for (const name of ["Evidence packet", "Receipts", "Reproduce", "Retraction record", "Model cards"]) {
      expect(screen.getByRole("link", { name })).toBeTruthy();
    }
    expect(screen.getByRole("link", { name: "Retraction record" })).toHaveAttribute("href", expect.stringMatching(/^\/evidence\/retractions\/?$/));
    expect(document.body.textContent).toContain("model data as of 2026-07-16; paper desk record through 2026-10-16");
  });

  it("states the request inventory's finding: no analytics, no cookies, no third-party requests", () => {
    render(<SiteFooter dates={{ modelAsOf: null, deskThrough: null }} />);
    expect(screen.getByText("No analytics, no cookies, no third-party requests.")).toBeInTheDocument();
  });

  it("uses no banned wording and no tool names", () => {
    const { container } = render(<SiteFooter dates={{ modelAsOf: null, deskThrough: null }} />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/\b(edge|roi|profit|beats?|money)\b/i);
    expect(text).not.toMatch(/claude|codex|opus|sonnet|vitest|next\.js/i);
  });
});
