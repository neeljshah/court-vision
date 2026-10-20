import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AsOfBadge, asOfText } from "./AsOfBadge";

describe("AsOfBadge", () => {
  it("renders a machine-readable time element with the kit wording", () => {
    render(<AsOfBadge asOf="2026-10-19" />);
    const time = screen.getByText("as of 2026-10-19");
    expect(time.tagName).toBe("TIME");
    expect(time).toHaveAttribute("dateTime", "2026-10-19");
    expect(time.parentElement).toHaveAttribute("title", "Source as of 2026-10-19");
    expect(time.parentElement).toHaveClass("ev-asof");
  });

  it("trims a timestamp to its day and words a generation stamp as generated", () => {
    render(<AsOfBadge asOf="2026-07-22T20:15:22.041778+00:00" kind="snapshot" />);
    expect(screen.getByText("generated 2026-07-22")).toHaveAttribute("dateTime", "2026-07-22");
  });

  it("treats a placeholder as a missing date and flags it", () => {
    render(<AsOfBadge asOf="Published snapshot" />);
    const badge = screen.getByText("date not published").parentElement as HTMLElement;
    expect(badge).toHaveClass("ev-asof--missing");
    expect(badge).toHaveAttribute("title", "The source artifact carries no as-of date.");
  });

  it("flags stale data visibly, not by colour alone", () => {
    render(<AsOfBadge asOf="2026-10-16" stale />);
    expect(screen.getByText("STALE")).toBeInTheDocument();
    expect(screen.getByText("STALE").parentElement).toHaveClass("ev-asof--stale");
  });

  it("renders an observation window", () => {
    render(<AsOfBadge asOf={{ start: "2026-10-06", end: "2026-10-16" }} kind="window" />);
    expect(screen.getByText("window 2026-10-06 to 2026-10-16")).toBeInTheDocument();
    expect(asOfText("2025-26 regular season", "window").text).toBe("window 2025-26 regular season");
  });
});
