import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import AboutPage from "./page";

describe("About page", () => {
  it("has contact, methods and the what-this-is-not block", () => {
    render(<AboutPage />);
    expect(screen.getByRole("link", { name: "neeljshah22@gmail.com" })).toHaveAttribute("href", "mailto:neeljshah22@gmail.com");
    expect(screen.getByRole("heading", { name: "What this is not" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "How it works" })).toHaveAttribute("href", expect.stringMatching(/^\/how-it-works\/?$/));
    expect(screen.getByRole("link", { name: "Glossary" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "retraction record" })).toHaveAttribute("href", expect.stringMatching(/^\/evidence\/retractions\/?$/));
  });

  it("leads with the headline finding, with the reference and scoring rule as glossary terms", () => {
    const { container } = render(<AboutPage />);
    const lede = container.querySelector("header p")!;
    expect(lede.textContent).toMatch(/does not\s+price games better than the market/);
    expect(lede.textContent).toMatch(/on MLB moneyline and soccer\s+over\/under 2\.5, and matches it on NBA moneyline only where the sample is too small to tell/);
    expect(screen.getByRole("button", { name: "devigged closing price" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Brier score" })).toBeTruthy();
    expect(container.textContent).not.toMatch(/within noise/i);
  });

  it("uses no banned or degree wording", () => {
    const { container } = render(<AboutPage />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/\b(edge|roi|profit|beats?|money)\b/i);
    expect(text).not.toMatch(/degree|ph\.?d|graduat|bachelor|master'?s/i);
  });
});
