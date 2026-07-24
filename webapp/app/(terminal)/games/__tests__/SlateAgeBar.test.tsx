// SlateAgeBar.test.tsx -- FD-09 accept criteria
// generatedAt 5m ago -> green "5m ago" (no STALE prefix)
// generatedAt 35m ago -> red "STALE 35m ago"
// null -> "no timestamp" (neutral, not red-failed)
// No $ in any rendered output.

import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { SlateAgeBar } from "../SlateAgeBar";

const NOW = new Date("2026-06-20T12:00:00Z").getTime();

function isoMinutesAgo(minutes: number): string {
  return new Date(NOW - minutes * 60 * 1000).toISOString();
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
});
afterEach(() => {
  vi.useRealTimers();
});

describe("SlateAgeBar -- FD-09 accept criteria", () => {
  it("5m ago renders the time label without STALE prefix", () => {
    render(<SlateAgeBar generatedAt={isoMinutesAgo(5)} />);
    const el = screen.getByText(/5m ago/i);
    expect(el).toBeInTheDocument();
    expect(el.textContent).not.toMatch(/STALE/);
  });

  it("35m ago renders STALE prefix", () => {
    render(<SlateAgeBar generatedAt={isoMinutesAgo(35)} />);
    const el = screen.getByText(/STALE 35m ago/i);
    expect(el).toBeInTheDocument();
  });

  it("null generatedAt renders 'no timestamp'", () => {
    render(<SlateAgeBar generatedAt={null} />);
    expect(screen.getByText("no timestamp")).toBeInTheDocument();
  });

  it("null generatedAt does not render STALE or any age", () => {
    render(<SlateAgeBar generatedAt={null} />);
    expect(screen.queryByText(/STALE/i)).toBeNull();
    expect(screen.queryByText(/ago/i)).toBeNull();
  });

  it("exactly 30m ago is NOT stale (boundary: stale only > 30m)", () => {
    // 30 min ago = exactly at boundary -- not stale yet
    render(<SlateAgeBar generatedAt={isoMinutesAgo(30)} />);
    expect(screen.queryByText(/STALE/i)).toBeNull();
  });

  it("31m ago is stale", () => {
    render(<SlateAgeBar generatedAt={isoMinutesAgo(31)} />);
    expect(screen.getByText(/STALE/i)).toBeInTheDocument();
  });

  it("no $ in any rendered output", () => {
    const { container } = render(<SlateAgeBar generatedAt={isoMinutesAgo(5)} />);
    expect(container.textContent).not.toMatch(/\$\s*\d/);
  });
});
