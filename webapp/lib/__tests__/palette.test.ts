import { describe, expect, it } from "vitest";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { PALETTE } from "@/lib/palette";

// The chart palette constants match the validated PALETTE file's hex list, in slot order,
// and the calibration page CSS exposes exactly those values for both themes.
describe("validated chart palette", () => {
  // docs/research/ is local-only (absent from the public clone): skip the file check there.
  const file = join(process.cwd(), "../docs/research/site/PALETTE_2026-10-20.md");
  const md = existsSync(file) ? readFileSync(file, "utf-8") : "";
  const rows = [...md.matchAll(/^\|\s*(\d)\s*\|\s*\w+\s*\|\s*(#[0-9a-f]{6})\s*\|\s*(#[0-9a-f]{6})\s*\|/gim)];

  it.skipIf(!md)("constants equal the PALETTE file, slot by slot", () => {
    expect(rows).toHaveLength(6);
    expect(rows.map((r) => r[2].toLowerCase())).toEqual([...PALETTE.light]);
    expect(rows.map((r) => r[3].toLowerCase())).toEqual([...PALETTE.dark]);
  });

  it("calibration.css declares both theme steps", () => {
    const css = readFileSync(join(process.cwd(), "app/(analytics)/analytics/calibration/calibration.css"), "utf-8");
    PALETTE.light.forEach((hex, i) => expect(css).toContain(`--series-${i + 1}: ${hex}`));
    PALETTE.dark.forEach((hex, i) => expect(css).toContain(`--series-${i + 1}: ${hex}`));
  });
});
