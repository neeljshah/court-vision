import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import AboutPage from "./page";

describe("About page", () => {
  it("has contact, methods and the what-this-is-not block", () => {
    render(<AboutPage />);
    expect(screen.getByRole("link", { name: "neeljshah22@gmail.com" })).toHaveAttribute("href", "mailto:neeljshah22@gmail.com");
    expect(screen.getByRole("heading", { name: "What this is not" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "How it works" })).toHaveAttribute("href", "/how-it-works/");
    expect(screen.getByRole("link", { name: "Glossary" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "retraction record" })).toHaveAttribute("href", "/evidence/retractions/");
  });

  it("uses no banned or degree wording", () => {
    const { container } = render(<AboutPage />);
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/\b(edge|roi|profit|beats?|money)\b/i);
    expect(text).not.toMatch(/degree|ph\.?d|graduat|bachelor|master'?s/i);
  });
});
