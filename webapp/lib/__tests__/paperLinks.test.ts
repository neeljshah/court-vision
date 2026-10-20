import { describe, it, expect } from "vitest";
import { paperDetailHref } from "../paperLinks";

describe("paperDetailHref", () => {
  const id = encodeURIComponent("mlb|mlb|St. Louis @ Chicago|2026-07-04T01:55:44.839439+00:00|moneyline|away|kalshi");

  it("double-encodes the id, hides the dots from Next, and keeps a trailing slash", () => {
    const href = paperDetailHref(id);
    expect(href.startsWith("/paper/")).toBe(true);
    expect(href.endsWith("/")).toBe(true);
    expect(href).not.toContain(".");
    expect(href).toContain("%257C");
  });

  it("resolves back to the exported directory name after one decode", () => {
    const segment = paperDetailHref(id).slice("/paper/".length, -1);
    expect(decodeURIComponent(segment)).toBe(id);
  });
});
