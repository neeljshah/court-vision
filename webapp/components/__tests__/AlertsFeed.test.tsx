import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";

// AlertsFeed unit tests -- ASCII rail + honest-empty-state + a11y + no-$ invariants.
//
// Honesty / rail invariants verified:
//   1. No non-ASCII characters in rendered output (no Unicode ellipsis, no em-dash
//      from the component itself -- only msg content which we control in tests).
//   2. Empty state renders an honest "nothing yet" framing, not red/error.
//   3. Severity conveyed by text cue [HIGH]/[MED]/[LOW], not color alone.
//   4. The alert list has an accessible label (role=feed + aria-label).
//   5. No $<digit> pattern in the DOM at any time.

// ---------------------------------------------------------------------------
// Mock the Zustand store so we can control the alerts array without a WS.
// ---------------------------------------------------------------------------
const mockAlerts: { ts: number; severity: string; msg: string }[] = [];

vi.mock("@/lib/store", () => ({
  useAlerts: () => mockAlerts,
}));

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function setAlerts(
  entries: { ts: number; severity: string; msg: string }[],
) {
  mockAlerts.length = 0;
  mockAlerts.push(...entries);
}

function nowSec() {
  return Math.floor(Date.now() / 1000);
}

// Import after mock is in place.
import { AlertsFeed } from "../AlertsFeed";

// ---------------------------------------------------------------------------
// ASCII rail -- no non-ASCII characters emitted by the component
// ---------------------------------------------------------------------------
describe("AlertsFeed -- ASCII rail", () => {
  beforeEach(() => setAlerts([]));

  it("empty state contains no non-ASCII characters", () => {
    const { container } = render(<AlertsFeed />);
    const text = container.textContent ?? "";
    // Unicode ellipsis U+2026 and em-dash U+2014 are the two historic offenders.
    expect(text).not.toMatch(/[\u0080-\uffff]/);
  });

  it("alert row contains no non-ASCII characters in structural text", () => {
    setAlerts([{ ts: nowSec() - 30, severity: "high", msg: "Test alert" }]);
    const { container } = render(<AlertsFeed />);
    // Strip only the msg content before checking -- msg itself is caller-supplied.
    const textWithoutMsg = (container.textContent ?? "").replace("Test alert", "");
    expect(textWithoutMsg).not.toMatch(/[\u0080-\uffff]/);
  });
});

// ---------------------------------------------------------------------------
// Empty state -- honest framing, not an error/red
// ---------------------------------------------------------------------------
describe("AlertsFeed -- empty state is honest, not an error", () => {
  beforeEach(() => setAlerts([]));

  it("renders a status region when there are no alerts", () => {
    render(<AlertsFeed />);
    // role=status announces to screen-readers that this is an advisory message.
    const status = screen.getByRole("status");
    expect(status).toBeInTheDocument();
  });

  it("empty state says 'No alerts yet' (honest nothing-yet framing)", () => {
    render(<AlertsFeed />);
    expect(screen.getByText(/no alerts yet/i)).toBeInTheDocument();
  });

  it("empty state does NOT use 'error', 'failed', or 'unavailable' language", () => {
    const { container } = render(<AlertsFeed />);
    const text = (container.textContent ?? "").toLowerCase();
    expect(text).not.toMatch(/\berror\b/);
    expect(text).not.toMatch(/\bfailed\b/);
    expect(text).not.toMatch(/\bunavailable\b/);
  });

  it("empty state does NOT render red/destructive styling (no red class)", () => {
    const { container } = render(<AlertsFeed />);
    // Scan all elements -- none should carry a Tailwind red class in an empty state.
    const redElements = container.querySelectorAll('[class*="red"]');
    expect(redElements.length).toBe(0);
  });

  it("does not render the feed list when there are no alerts", () => {
    render(<AlertsFeed />);
    expect(screen.queryByRole("feed")).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// Accessible list label (role=feed + aria-label)
// ---------------------------------------------------------------------------
describe("AlertsFeed -- accessible list", () => {
  beforeEach(() =>
    setAlerts([
      { ts: nowSec() - 60, severity: "low", msg: "System check complete" },
    ]),
  );

  it("renders a list with role=feed when alerts are present", () => {
    render(<AlertsFeed />);
    const feed = screen.getByRole("feed");
    expect(feed).toBeInTheDocument();
  });

  it("the feed list has an accessible label", () => {
    render(<AlertsFeed />);
    const feed = screen.getByRole("feed");
    // Must have aria-label (not just an unlabelled list).
    expect(feed).toHaveAttribute("aria-label");
    expect(feed.getAttribute("aria-label")).not.toBe("");
  });
});

// ---------------------------------------------------------------------------
// Severity conveyed by text/aria cue, not color alone
// ---------------------------------------------------------------------------
describe("AlertsFeed -- severity text cues", () => {
  it("HIGH severity shows [HIGH] text label", () => {
    setAlerts([{ ts: nowSec() - 10, severity: "high", msg: "Critical event" }]);
    const { container } = render(<AlertsFeed />);
    expect(container.textContent).toMatch(/\[HIGH\]/i);
  });

  it("MED severity shows [MED] text label", () => {
    setAlerts([{ ts: nowSec() - 20, severity: "medium", msg: "Warning event" }]);
    const { container } = render(<AlertsFeed />);
    expect(container.textContent).toMatch(/\[MED\]/i);
  });

  it("LOW severity shows [LOW] text label", () => {
    setAlerts([{ ts: nowSec() - 30, severity: "low", msg: "Info event" }]);
    const { container } = render(<AlertsFeed />);
    expect(container.textContent).toMatch(/\[LOW\]/i);
  });

  it("unknown severity falls back to [LOW] label (no crash)", () => {
    setAlerts([{ ts: nowSec(), severity: "unknown_tier", msg: "Odd alert" }]);
    const { container } = render(<AlertsFeed />);
    expect(container.textContent).toMatch(/\[LOW\]/i);
  });

  it("each alert list item has an aria-label conveying severity + message", () => {
    setAlerts([{ ts: nowSec() - 5, severity: "high", msg: "Spike detected" }]);
    render(<AlertsFeed />);
    const feed = screen.getByRole("feed");
    const items = within(feed).getAllByRole("listitem");
    expect(items.length).toBeGreaterThan(0);
    const ariaLabel = items[0].getAttribute("aria-label") ?? "";
    expect(ariaLabel.toLowerCase()).toMatch(/high/);
    expect(ariaLabel).toMatch(/Spike detected/);
  });
});

// ---------------------------------------------------------------------------
// timeAgo formatting -- renders without non-ASCII suffixes
// ---------------------------------------------------------------------------
describe("AlertsFeed -- timeAgo formatting", () => {
  it("recent alert shows seconds-ago label ending with 'ago'", () => {
    setAlerts([{ ts: nowSec() - 45, severity: "low", msg: "Recent event" }]);
    const { container } = render(<AlertsFeed />);
    // Must include 'ago' as ASCII text; no non-ASCII ellipsis after.
    expect(container.textContent).toMatch(/\d+s ago/);
  });

  it("older alert shows minutes-ago label", () => {
    setAlerts([{ ts: nowSec() - 130, severity: "low", msg: "Old event" }]);
    const { container } = render(<AlertsFeed />);
    expect(container.textContent).toMatch(/\d+m ago/);
  });
});

// ---------------------------------------------------------------------------
// No dollar figures anywhere in the DOM
// ---------------------------------------------------------------------------
describe("AlertsFeed -- no dollar figures", () => {
  it("empty state has no dollar figure", () => {
    setAlerts([]);
    const { container } = render(<AlertsFeed />);
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });

  it("populated feed has no dollar figure in structural text", () => {
    setAlerts([
      { ts: nowSec() - 10, severity: "high", msg: "Score update" },
      { ts: nowSec() - 60, severity: "medium", msg: "Line move flagged" },
    ]);
    const { container } = render(<AlertsFeed />);
    expect(container.textContent ?? "").not.toMatch(/\$\s?\d/);
  });
});

// ---------------------------------------------------------------------------
// Multiple alerts render correctly
// ---------------------------------------------------------------------------
describe("AlertsFeed -- multiple alerts", () => {
  it("renders all provided alerts as list items", () => {
    setAlerts([
      { ts: nowSec() - 5, severity: "high", msg: "Alert one" },
      { ts: nowSec() - 60, severity: "medium", msg: "Alert two" },
      { ts: nowSec() - 120, severity: "low", msg: "Alert three" },
    ]);
    render(<AlertsFeed />);
    const feed = screen.getByRole("feed");
    const items = within(feed).getAllByRole("listitem");
    expect(items.length).toBe(3);
  });

  it("the section header 'Alerts' is always visible", () => {
    setAlerts([]);
    render(<AlertsFeed />);
    expect(screen.getByRole("heading", { name: /alerts/i })).toBeInTheDocument();
  });
});
