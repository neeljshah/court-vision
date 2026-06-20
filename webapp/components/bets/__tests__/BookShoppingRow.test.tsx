import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { BookShoppingRow } from "../BookShoppingRow";
import type { BookOddsEntry } from "../BookShoppingRow";

// BookShoppingRow.test.tsx -- per-component vitest for the book-shopping pills.
//
// Acceptance criteria:
//   - best entry has a non-color 'best' indicator (visible text tag + aria-label)
//   - empty books renders the honest unavailable state (never a guess/error)
//   - American-odds format correct for >= 2.0, <= 1.0 (evens), and 1.0 < x < 2.0
//   - no $<digit> anywhere in the DOM

const SAMPLE_BOOKS: BookOddsEntry[] = [
  { book: "DK",   odds: 1.91, is_best: false },
  { book: "FD",   odds: 1.95, is_best: true  },
  { book: "MGM",  odds: 1.87, is_best: false },
];

function renderRow(books: BookOddsEntry[], side?: string) {
  return render(<BookShoppingRow books={books} side={side} />);
}

// ---------------------------------------------------------------------------
// Unavailable / empty state
// ---------------------------------------------------------------------------

describe("BookShoppingRow -- empty state", () => {
  it("renders unavailable text when books array is empty", () => {
    renderRow([]);
    expect(screen.getByText(/unavailable/i)).toBeInTheDocument();
  });

  it("renders unavailable text when books is empty (no side prop)", () => {
    const { container } = renderRow([]);
    expect(container.textContent).toMatch(/unavailable/i);
    // Must NOT render a list
    expect(container.querySelector("ul")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Non-color 'best' indicator (WCAG 1.4.1)
// ---------------------------------------------------------------------------

describe("BookShoppingRow -- best-book accessibility", () => {
  it("the best pill has a visible 'best' text tag in the DOM", () => {
    renderRow(SAMPLE_BOOKS);
    // The word 'best' must appear as visible text (aria-hidden="true" on the
    // badge means it's visually present; acceptance is DOM text presence).
    // Use getAllByText to match the badge span.
    const bestTags = document.querySelectorAll(
      "[data-testid='best-book-pill'] span[aria-hidden='true']",
    );
    expect(bestTags.length).toBeGreaterThanOrEqual(1);
    expect(bestTags[0].textContent?.toLowerCase()).toContain("best");
  });

  it("the best pill aria-label includes 'best available line'", () => {
    renderRow(SAMPLE_BOOKS);
    const pill = document.querySelector("[data-testid='best-book-pill']");
    expect(pill).not.toBeNull();
    expect(pill?.getAttribute("aria-label")).toContain("best available line");
  });

  it("the best pill aria-label includes the book name and odds", () => {
    renderRow(SAMPLE_BOOKS);
    const pill = document.querySelector("[data-testid='best-book-pill']");
    const label = pill?.getAttribute("aria-label") ?? "";
    expect(label).toMatch(/FD/i);
    expect(label).toMatch(/-\d+|evens|\+\d+/);
  });

  it("non-best pills do NOT have 'best available line' in their aria-label", () => {
    renderRow(SAMPLE_BOOKS);
    const nonBestPills = document.querySelectorAll("[data-testid='book-pill']");
    nonBestPills.forEach((pill) => {
      expect(pill.getAttribute("aria-label") ?? "").not.toContain(
        "best available line",
      );
    });
  });

  it("exactly one pill carries data-testid=best-book-pill", () => {
    renderRow(SAMPLE_BOOKS);
    const bestPills = document.querySelectorAll("[data-testid='best-book-pill']");
    expect(bestPills).toHaveLength(1);
  });
});

// ---------------------------------------------------------------------------
// American odds format
// ---------------------------------------------------------------------------

describe("BookShoppingRow -- American odds formatting", () => {
  it("decimal >= 2.0 renders as +NNN", () => {
    // 2.50 -> +150
    renderRow([{ book: "DK", odds: 2.5 }]);
    expect(screen.getByText("+150")).toBeInTheDocument();
  });

  it("decimal <= 1.0 renders as 'evens'", () => {
    renderRow([{ book: "DK", odds: 1.0 }]);
    expect(screen.getByText("evens")).toBeInTheDocument();
  });

  it("decimal between 1.0 and 2.0 renders as -NNN", () => {
    // 1.91 -> -110 (rounded from 100/(0.91) = 109.89...)
    renderRow([{ book: "DK", odds: 1.91 }]);
    expect(screen.getByText("-110")).toBeInTheDocument();
  });

  it("even-money (2.0 exactly) renders as +100", () => {
    renderRow([{ book: "DK", odds: 2.0 }]);
    expect(screen.getByText("+100")).toBeInTheDocument();
  });

  it("long-shot odds (3.0) renders as +200", () => {
    renderRow([{ book: "DK", odds: 3.0 }]);
    expect(screen.getByText("+200")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Line display
// ---------------------------------------------------------------------------

describe("BookShoppingRow -- line display", () => {
  it("positive line renders with + prefix", () => {
    renderRow([{ book: "DK", odds: 1.91, line: 5.5 }]);
    expect(screen.getByText("+5.5")).toBeInTheDocument();
  });

  it("negative line renders without extra sign", () => {
    renderRow([{ book: "DK", odds: 2.1, line: -5.5 }]);
    expect(screen.getByText("-5.5")).toBeInTheDocument();
  });

  it("zero line renders without + prefix", () => {
    renderRow([{ book: "DK", odds: 1.91, line: 0 }]);
    expect(screen.getByText("0")).toBeInTheDocument();
  });

  it("absent line means no line element rendered", () => {
    renderRow([{ book: "DK", odds: 1.91 }]);
    // Only "DK" label and the odds string should be present; no extra number.
    expect(screen.queryByText(/^\+\d+\.\d+$/)).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// List structure and side label
// ---------------------------------------------------------------------------

describe("BookShoppingRow -- list structure", () => {
  it("renders a ul with role-friendly aria-label", () => {
    const { container } = renderRow(SAMPLE_BOOKS, "over");
    const ul = container.querySelector("ul");
    expect(ul).not.toBeNull();
    expect(ul?.getAttribute("aria-label")).toBe("Book lines for over");
  });

  it("renders one li per book entry", () => {
    const { container } = renderRow(SAMPLE_BOOKS);
    const items = container.querySelectorAll("li");
    expect(items).toHaveLength(SAMPLE_BOOKS.length);
  });

  it("renders aria-label without side when side is omitted", () => {
    const { container } = renderRow(SAMPLE_BOOKS);
    const ul = container.querySelector("ul");
    expect(ul?.getAttribute("aria-label")).toBe("Book lines");
  });
});

// ---------------------------------------------------------------------------
// Honest rails: no $ in DOM
// ---------------------------------------------------------------------------

describe("BookShoppingRow -- honest rails", () => {
  it("no $<digit> anywhere in the DOM for a normal books list", () => {
    const { container } = renderRow(SAMPLE_BOOKS);
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });

  it("no $<digit> anywhere in the empty-state DOM", () => {
    const { container } = renderRow([]);
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });
});
