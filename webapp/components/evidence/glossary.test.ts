import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { GLOSSARY, GLOSSARY_IDS, GLOSSARY_PATH } from "./glossary";

// docs/GLOSSARY.md wraps entries at ~100 columns; join the continuation lines so an entry
// is one "- **Term** -- text" sentence, then require every kit entry verbatim.
const glossary = readFileSync(join(__dirname, "../../..", GLOSSARY_PATH), "utf8")
  .replace(/\n[ \t]+/g, " ");

describe("Term glossary", () => {
  it.each(GLOSSARY_IDS)("%s is copied verbatim from docs/GLOSSARY.md", (id) => {
    const { term, text } = GLOSSARY[id];
    expect(glossary).toContain(`- **${term}** -- ${text}`);
  });

  it("covers the six terms the site tooltips need", () => {
    expect([...GLOSSARY_IDS].sort()).toEqual(["brier", "calibration-vs-resolution", "crps", "devigged-close", "diebold-mariano", "mde"]);
  });

  it("uses calibration language only", () => {
    for (const id of GLOSSARY_IDS) expect(GLOSSARY[id].text).not.toMatch(/\b(ROI|profit|bankroll|edge)\b/i);
  });
});
