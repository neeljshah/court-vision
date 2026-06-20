import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { Badge, Unavailable } from "../Primitives";

// ---------------------------------------------------------------------------
// A11y tests for the shared Badge and Unavailable primitives (workstream
// r4-primitives-badge-aria). These gate three invariants:
//
//   1. Badge renders its text content (state conveyed by text, not color-only)
//   2. Badge exposes an accessible role so assistive tech surfaces status pills
//   3. Badge exposes an aria-label matching the visible text for string children
//   4. Unavailable has role="status" so AT announces degraded state
//   5. Unavailable shows (and labels with) its reason when one is supplied
//   6. Unavailable with no reason still has role="status"
//   7. Non-string Badge children (nested spans) get the role without aria-label
//   8. Existing tone/layout signature is unchanged (regression guard)
// ---------------------------------------------------------------------------

describe("Badge -- a11y (role + aria-label)", () => {
  it("1. renders its text content so state is conveyed by text, not color alone", () => {
    render(<Badge tone="green">fresh</Badge>);
    expect(screen.getByText("fresh")).toBeTruthy();
  });

  it("2. exposes role=status so the pill is announced by screen readers", () => {
    render(<Badge tone="amber">stale</Badge>);
    // getByRole throws if no element matches -- verifies the role is present.
    const badge = screen.getByRole("status");
    expect(badge).toBeTruthy();
  });

  it("3. aria-label matches the visible text for a plain-string child", () => {
    render(<Badge tone="red">down</Badge>);
    const badge = screen.getByRole("status", { name: /down/i });
    expect(badge).toBeTruthy();
    expect(badge.getAttribute("aria-label")).toBe("down");
  });

  it("3b. aria-label also matches for slate and gold tones", () => {
    const { unmount } = render(<Badge tone="slate">checking</Badge>);
    expect(screen.getByRole("status", { name: /checking/i })).toBeTruthy();
    unmount();
    render(<Badge tone="gold">tier-s</Badge>);
    expect(screen.getByRole("status", { name: /tier-s/i })).toBeTruthy();
  });

  it("7. non-string children get role=status but no aria-label override", () => {
    render(
      <Badge tone="slate">
        <span data-testid="inner">wrapped</span>
      </Badge>,
    );
    const badge = screen.getByRole("status");
    expect(badge).toBeTruthy();
    // aria-label is undefined for non-string children (no forced override)
    expect(badge.getAttribute("aria-label")).toBeNull();
    // The inner content still renders normally
    expect(screen.getByTestId("inner").textContent).toBe("wrapped");
  });

  it("8. tone classes are still applied (regression guard -- tones unchanged)", () => {
    const { unmount } = render(<Badge tone="green">ok</Badge>);
    const green = screen.getByRole("status");
    expect(green.className).toContain("tier-a");
    expect(green.className).not.toContain("amber");
    unmount();

    render(<Badge tone="amber">stale</Badge>);
    const amber = screen.getByRole("status");
    expect(amber.className).toContain("amber");
    expect(amber.className).not.toContain("tier-a");
  });
});

describe("Unavailable -- a11y (role=status + reason)", () => {
  it("4. has role=status so assistive tech announces the degraded state", () => {
    render(<Unavailable />);
    const el = screen.getByRole("status");
    expect(el).toBeTruthy();
  });

  it("5. shows the reason text when one is supplied", () => {
    render(<Unavailable reason="feed offline" />);
    expect(screen.getByText(/feed offline/i)).toBeTruthy();
  });

  it("5b. aria-label includes the reason so screen readers get the full context", () => {
    render(<Unavailable reason="no data" />);
    const el = screen.getByRole("status");
    const label = el.getAttribute("aria-label") ?? "";
    expect(label).toContain("unavailable");
    expect(label).toContain("no data");
  });

  it("6. role=status present even with no reason supplied", () => {
    render(<Unavailable />);
    const el = screen.getByRole("status");
    // aria-label should still say 'unavailable' without a reason suffix
    expect(el.getAttribute("aria-label")).toBe("unavailable");
  });

  it("still renders the 'unavailable' text label visually (regression guard)", () => {
    render(<Unavailable reason="pipeline stalled" />);
    expect(screen.getByText("unavailable")).toBeTruthy();
    expect(screen.getByText(/pipeline stalled/i)).toBeTruthy();
  });
});
