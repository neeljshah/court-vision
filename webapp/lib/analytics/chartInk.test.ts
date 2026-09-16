import { describe, expect, it } from "vitest";
import { cellInk, contrastRatio, relativeLuminance, sequentialFill, sequentialInk } from "./chartInk";

describe("chartInk", () => {
  it("computes relative luminance and the WCAG contrast ratio", () => {
    expect(relativeLuminance("#FFFFFF")).toBeCloseTo(1, 6);
    expect(relativeLuminance("#000000")).toBeCloseTo(0, 6);
    expect(contrastRatio("#000000", "#FFFFFF")).toBeCloseTo(21, 6);
    expect(contrastRatio("#FFFFFF", "#FFFFFF")).toBeCloseTo(1, 6);
  });

  it("picks the ink its own fill can carry", () => {
    expect(cellInk("#FFFFFF")).toBe("dark");
    expect(cellInk("#000000")).toBe("light");
  });

  it("clears 4.5:1 on every step of the published sequential ramp", () => {
    for (let step = 0; step <= 4; step += 1) {
      const fill = sequentialFill(step);
      const ink = sequentialInk(step) === "light" ? "#FFFFFF" : "#182630";
      expect(contrastRatio(fill, ink)).toBeGreaterThanOrEqual(4.5);
    }
    expect([0, 1, 2, 3, 4].map(sequentialInk)).toEqual(["dark", "dark", "dark", "light", "light"]);
  });
});
