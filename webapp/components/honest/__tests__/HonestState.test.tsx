import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { readdirSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { Unavailable, Empty, Stale, Degraded, HonestState } from "../HonestState";

// HonestState family -- gates explicit labelled states, stale-never-green, ARIA
// live-region semantics per variant, sr-only state word on custom titles, and
// that every app route segment provides error.tsx + loading.tsx boundaries.

describe("HonestState variants render an explicit, non-blank state", () => {
  it("Unavailable shows the degraded label + reason", () => {
    render(<Unavailable reason="endpoint down" />);
    expect(screen.getByText("unavailable")).toBeInTheDocument();
    expect(screen.getByText("endpoint down")).toBeInTheDocument();
  });

  it("Empty shows an honest 'nothing here' label (not an error)", () => {
    render(<Empty label="No games live now" />);
    expect(screen.getByText("No games live now")).toBeInTheDocument();
  });

  it("Stale reads as stale and NEVER as fresh/green (stale-never-green)", () => {
    const { container } = render(<Stale reason="3h old" asOf="3h ago" />);
    expect(screen.getByText("stale")).toBeInTheDocument();
    const html = container.innerHTML;
    expect(html).not.toContain("tier-a");
    expect(html).not.toContain("bg-success");
    expect(html).not.toContain("bg-green");
  });

  it("Degraded shows a fallback-mode label", () => {
    render(<Degraded reason="poll fallback active" />);
    expect(screen.getByText("degraded")).toBeInTheDocument();
  });

  it("HonestState dispatcher picks the variant and is never blank", () => {
    const { container } = render(<HonestState variant="unavailable" reason="x" />);
    expect(container.querySelector('[data-honest-state="unavailable"]')).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// ARIA live-region semantics: Unavailable -> role=alert (assertive),
// Empty/Stale/Degraded -> role=status (polite).
// ---------------------------------------------------------------------------

describe("ARIA live-region semantics per variant", () => {
  it("Unavailable uses role=alert (assertive)", () => {
    const { container } = render(<Unavailable reason="down" />);
    expect(container.querySelector('[data-honest-state="unavailable"]')!.getAttribute("role")).toBe("alert");
  });

  it("Empty uses role=status (polite)", () => {
    const { container } = render(<Empty />);
    expect(container.querySelector('[data-honest-state="empty"]')!.getAttribute("role")).toBe("status");
  });

  it("Stale uses role=status (polite)", () => {
    const { container } = render(<Stale />);
    expect(container.querySelector('[data-honest-state="stale"]')!.getAttribute("role")).toBe("status");
  });

  it("Degraded uses role=status (polite)", () => {
    const { container } = render(<Degraded />);
    expect(container.querySelector('[data-honest-state="degraded"]')!.getAttribute("role")).toBe("status");
  });

  it("HonestState(unavailable) carries role=alert", () => {
    const { container } = render(<HonestState variant="unavailable" />);
    expect(container.querySelector('[data-honest-state="unavailable"]')!.getAttribute("role")).toBe("alert");
  });

  it("HonestState(stale/degraded/empty) carry role=status", () => {
    for (const variant of ["stale", "degraded", "empty"] as const) {
      const { container, unmount } = render(<HonestState variant={variant} />);
      expect(container.querySelector(`[data-honest-state="${variant}"]`)!.getAttribute("role")).toBe("status");
      unmount();
    }
  });
});

// ---------------------------------------------------------------------------
// State word always in the accessibility tree via sr-only span when custom
// title overrides the default variant word.
// ---------------------------------------------------------------------------

describe("state word always in the accessibility tree (sr-only fallback)", () => {
  it("Unavailable with default title exposes 'unavailable' visually", () => {
    render(<Unavailable />);
    expect(screen.getByText("unavailable")).toBeInTheDocument();
  });

  it("Unavailable with custom title carries state word in sr-only span", () => {
    const { container } = render(<Unavailable title="Predictions offline" />);
    expect(screen.getByText(/Predictions offline/)).toBeInTheDocument();
    const srEl = container.querySelector('[data-sr-state="unavailable"]');
    expect(srEl).not.toBeNull();
    expect(srEl!.textContent).toMatch(/unavailable/i);
  });

  it("Empty with custom label carries state word in sr-only span", () => {
    const { container } = render(<Empty label="No live games" />);
    expect(screen.getByText("No live games")).toBeInTheDocument();
    const srEl = container.querySelector('[data-sr-state="empty"]');
    expect(srEl).not.toBeNull();
    expect(srEl!.textContent).toMatch(/nothing here yet/i);
  });

  it("Degraded with custom title carries state word in sr-only span", () => {
    const { container } = render(<Degraded title="poll mode" reason="SSE down" />);
    expect(screen.getByText("poll mode")).toBeInTheDocument();
    const srEl = container.querySelector('[data-sr-state="degraded"]');
    expect(srEl).not.toBeNull();
    expect(srEl!.textContent).toMatch(/degraded/i);
  });

  it("Stale with default title has NO duplicate sr-only span", () => {
    // Stale always passes title='stale' which matches the variant word.
    const { container } = render(<Stale reason="old" />);
    expect(container.querySelector('[data-sr-state="stale"]')).toBeNull();
  });

  it("Degraded with default title has NO duplicate sr-only span", () => {
    const { container } = render(<Degraded reason="poll" />);
    expect(container.querySelector('[data-sr-state="degraded"]')).toBeNull();
  });

  it("HonestState(unavailable) with custom title still exposes state word", () => {
    const { container } = render(<HonestState variant="unavailable" title="Service down" />);
    const srEl = container.querySelector('[data-sr-state="unavailable"]');
    expect(srEl).not.toBeNull();
    expect(srEl!.textContent).toMatch(/unavailable/i);
  });
});

// ---------------------------------------------------------------------------
// data-honest-state hook + tone invariants (no green on stale/unavailable).
// ---------------------------------------------------------------------------

describe("data-honest-state hook and tone class invariants", () => {
  it("all four variants carry the correct data-honest-state attribute", () => {
    for (const [variant, el] of [
      ["unavailable", <Unavailable key="u" />],
      ["empty",       <Empty key="e" />],
      ["stale",       <Stale key="s" />],
      ["degraded",    <Degraded key="d" />],
    ] as const) {
      const { container, unmount } = render(el);
      expect(container.querySelector(`[data-honest-state="${variant}"]`)).not.toBeNull();
      unmount();
    }
  });

  it("Unavailable never carries a green tone class", () => {
    const { container } = render(<Unavailable reason="r" />);
    const html = container.innerHTML;
    expect(html).not.toContain("tier-a");
    expect(html).not.toContain("bg-success");
    expect(html).not.toContain("bg-green");
  });

  it("Stale never carries a green tone class (stale-never-green)", () => {
    const { container } = render(<Stale reason="old" asOf="1h ago" />);
    const html = container.innerHTML;
    expect(html).not.toContain("tier-a");
    expect(html).not.toContain("bg-success");
    expect(html).not.toContain("bg-green");
  });
});

// ---------------------------------------------------------------------------
// No crash: all variants and the HonestState dispatcher render without errors.
// ---------------------------------------------------------------------------

describe("no crash: all variants and the dispatcher render without errors", () => {
  it("all four named components render with no props", () => {
    expect(() => render(<Unavailable />)).not.toThrow();
    expect(() => render(<Empty />)).not.toThrow();
    expect(() => render(<Stale />)).not.toThrow();
    expect(() => render(<Degraded />)).not.toThrow();
  });

  it("all four named components render with all props", () => {
    expect(() => render(<Unavailable reason="r" title="T" className="x" />)).not.toThrow();
    expect(() => render(<Empty label="L" hint="H" className="x" />)).not.toThrow();
    expect(() => render(<Stale reason="r" asOf="1h" className="x" />)).not.toThrow();
    expect(() => render(<Degraded reason="r" title="T" className="x" />)).not.toThrow();
  });

  it("HonestState dispatcher renders all four variants without crashing", () => {
    for (const variant of ["unavailable", "empty", "stale", "degraded"] as const) {
      const { unmount } = render(<HonestState variant={variant} reason="x" asOf="1h" title="T" />);
      unmount();
    }
  });
});

// ---------------------------------------------------------------------------
// Negative control: every app route segment has error.tsx + loading.tsx.
// ---------------------------------------------------------------------------

describe("negative control: every app route segment has error.tsx + loading.tsx", () => {
  const here = dirname(fileURLToPath(import.meta.url));
  const appDir = join(here, "..", "..", "..", "app");

  function segmentsWithPages(dir: string, acc: string[] = []): string[] {
    for (const ent of readdirSync(dir, { withFileTypes: true })) {
      if (!ent.isDirectory()) continue;
      if (ent.name === "__tests__" || ent.name === ".next") continue;
      const sub = join(dir, ent.name);
      if (readdirSync(sub).includes("page.tsx")) acc.push(sub);
      segmentsWithPages(sub, acc);
    }
    if (dir === appDir && readdirSync(dir).includes("page.tsx") && !acc.includes(dir)) acc.push(dir);
    return acc;
  }

  function hasBoundary(segment: string, file: string): boolean {
    let cur = segment;
    while (true) {
      if (existsSync(join(cur, file))) return true;
      if (cur === appDir) return false;
      const parent = dirname(cur);
      if (parent === cur) return false;
      cur = parent;
    }
  }

  const segments = segmentsWithPages(appDir);

  it("found a non-trivial set of renderable segments", () => {
    expect(segments.length).toBeGreaterThanOrEqual(7);
  });

  it("every page segment is covered by an error.tsx boundary", () => {
    expect(segments.filter((s) => !hasBoundary(s, "error.tsx"))).toEqual([]);
  });

  it("every page segment is covered by a loading.tsx boundary", () => {
    expect(segments.filter((s) => !hasBoundary(s, "loading.tsx"))).toEqual([]);
  });
});

describe("teeth: a fabricated-green stale panel would FAIL the stale check", () => {
  it("an Unavailable panel never carries a fresh/green tone class", () => {
    const { container } = render(<Unavailable reason="r" />);
    const html = container.innerHTML;
    expect(html).not.toContain("tier-a");
    expect(html).not.toContain("bg-success");
  });
});
