import { describe, expect, it } from "vitest";
import { displayMeasurement } from "./labTypes";

describe("displayMeasurement", () => {
  it("keeps missing, true zero, and tiny nonzero measurements distinct", () => {
    const field = { key: "hhi", label: "HHI contribution", unit: "number" as const };
    expect(displayMeasurement(null, field)).toBe("Unavailable");
    expect(displayMeasurement(0, field)).toBe("0");
    expect(displayMeasurement(-0, field)).toBe("0");
    expect(displayMeasurement(0.0036, field)).toBe("0.0036");
    expect(displayMeasurement(0.00000001, field)).toBe("<0.000001");
    expect(displayMeasurement(-0.00000001, field)).toBe(">-0.000001");
  });

  it("scales fractions before formatting percent and percentage-point units", () => {
    expect(displayMeasurement(0.218, { key: "share", label: "Share", unit: "percent" })).toBe("21.8%");
    expect(displayMeasurement(-0.0618, { key: "gap", label: "Gap", unit: "pp" })).toBe("-6.18 pp");
    expect(displayMeasurement(-0, { key: "gap", label: "Gap", unit: "pp" })).toBe("0 pp");
  });
});
