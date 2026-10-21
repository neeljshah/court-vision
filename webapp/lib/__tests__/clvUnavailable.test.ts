// clvUnavailable.test.ts -- the CLV sentence's as-of is the canonical forward-window
// figure's date, not a date typed into the sentence.
import { describe, expect, it } from "vitest";
import { CLV_UNAVAILABLE } from "../clvUnavailable";
import { FIGURES } from "../figures";

describe("CLV_UNAVAILABLE", () => {
  it("carries the forward_window_counts as-of and the series start, and nothing dollar-shaped", () => {
    expect(CLV_UNAVAILABLE).toContain(`as of ${FIGURES.forward_window_counts.as_of}`);
    expect(CLV_UNAVAILABLE).toContain("forward paper series since 2026-10-06, no verdict");
    expect(CLV_UNAVAILABLE.match(/\d{4}-\d{2}-\d{2}/g)).toEqual([FIGURES.forward_window_counts.as_of, "2026-10-06"]);
    expect(CLV_UNAVAILABLE).not.toMatch(/\$|edge|roi|profit/i);
  });
});
