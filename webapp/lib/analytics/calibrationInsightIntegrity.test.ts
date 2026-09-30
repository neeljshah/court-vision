import { describe, expect, it } from "vitest";
import manifest from "../../public/data/showcase/atlas_calibration_manifest.json";
import soccer from "../../public/data/insights/entities/calibration/soccer_intl_minute_0_15.json";
import inning5 from "../../public/data/insights/entities/calibration/mlb_inning_5.json";
import inning9 from "../../public/data/insights/entities/calibration/mlb_inning_9.json";

const sourcePath = "webapp/public/data/showcase/atlas_calibration_manifest.json";
const cards = [
  { entity: "soccer_intl minute 0-15", insight: soccer, stale: ["0.3065", "0.2204", "627"] },
  { entity: "mlb inning 5", insight: inning5, stale: ["0.0363", "0.0486", "6021"] },
  { entity: "mlb inning 9", insight: inning9, stale: ["0.2034", "0.071", "2282", "6021"] },
];

describe("published calibration Scout cards", () => {
  for (const { entity, insight, stale } of cards) {
    it(`${entity} agrees with its current manifest entry and describes the source limits`, () => {
      const entry = manifest.entries.find((item) => item.entity === entity);
      expect(entry).toBeDefined();
      if (!entry) return;
      const numbers: Record<string, unknown> = entry.key_numbers;
      const modelEce = numbers.model_ece;
      const marketEce = numbers.market_ece;
      const rowCount = numbers.n;
      if (typeof modelEce !== "number" || typeof marketEce !== "number" || typeof rowCount !== "number") {
        throw new Error(`${entity} is no longer a numeric checkpoint card`);
      }
      const prose = [insight.one_liner, ...insight.three_things, insight.context_note].join(" ");

      expect(insight.pack).toBe("calibration");
      expect(insight.as_of).toBe(entry.as_of);
      for (const citation of insight.cited) {
        expect(citation.path).toBe(sourcePath);
        const match = /^entries\[entity=(.+)\]\.(?:key_numbers\.([a-z_]+)|(card_type))$/.exec(citation.field);
        expect(match).not.toBeNull();
        if (!match) continue;
        expect(match[1]).toBe(entity);
        const published = match[2] ? numbers[match[2]] : entry.card_type;
        expect(published).toBeDefined();
        expect(citation.value).toBe(published);
      }
      for (const field of ["n", "model_ece", "market_ece"]) {
        expect(insight.cited.filter((item) => item.field === `entries[entity=${entity}].key_numbers.${field}`)).toHaveLength(1);
      }
      expect(insight.one_liner).toContain(modelEce.toFixed(4));
      expect(insight.one_liner).toContain(marketEce.toFixed(4));
      expect(insight.one_liner).toContain(rowCount.toLocaleString("en-US"));
      expect(prose).toMatch(/rows are not a count of unique games/i);
      expect(prose).toMatch(/snapshot, not an observation window/i);
      expect(prose).toMatch(/bin definitions/i);
      for (const oldValue of stale) expect(prose).not.toContain(oldValue);
      expect(prose).not.toMatch(/trails|better calibrated|degrades|information gap|nearly triple|weakest/i);
    });
  }
});
