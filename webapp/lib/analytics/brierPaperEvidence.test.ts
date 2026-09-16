// Locks the Brier-decomposition paper to its two artifacts: the four signed remainders,
// the phase totals, the three separate timestamps, and the wording the review removed.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { publishedArtifacts } from "./papers.server";
import { paperStrings, validatePaper, type Paper, type PaperBlock } from "./papers";
// @ts-expect-error -- the executable scanner is deliberately dependency-free ESM.
import { PROHIBITED_TOKEN_RE } from "../../scripts/check-analytics-copy.mjs";

type SideBlock = {
  n: number; brier: number; reliability: number; resolution: number;
  uncertainty: number; reconstructed_brier: number;
};
type Murphy = { sports: Record<string, Record<"model_prob" | "market_prob", SideBlock>> };
type Grain = { n: number; brier_model: number; brier_market: number; brier_clim: number };
type Skill = { generated_at: string; sports: { mlb: { grains: Record<string, Grain> } } };
type TableBlock = Extract<PaperBlock, { type: "table" }>;
type TextBlock = Extract<PaperBlock, { type: "p" | "callout" | "math" }>;

const read = <T,>(...parts: string[]): T =>
  JSON.parse(readFileSync(join(process.cwd(), "public", "data", ...parts), "utf8")) as T;

const paper = read<Paper>("papers", "brier-decomposition-reliability-resolution.json");
const murphy = read<Murphy>("showcase", "murphy_decomposition.json");
const skill = read<Skill>("showcase", "brier_skill_scores.json");
const insight = read<{ as_of: string }>("insights", "brier_skill_scores.json");
const manifest = read<{ modules: { id: string; as_of: string | null }[] }>("showcase", "site_manifest.json");

const blocks = paper.sections.flatMap(section => section.blocks);
const prose = paperStrings(paper).join("\n");

const table = (caption: string): TableBlock => {
  const found = blocks.find(block => block.type === "table" && block.caption.includes(caption));
  if (!found) throw new Error(`no table captioned ${caption}`);
  return found as TableBlock;
};
const paragraph = (needle: string): string => {
  const found = blocks.find(block => (block.type === "p" || block.type === "callout") && block.text.includes(needle));
  if (!found) throw new Error(`no paragraph containing ${needle}`);
  return (found as TextBlock).text;
};
const moduleAsOf = (id: string) => manifest.modules.find(entry => entry.id === id)?.as_of ?? null;

describe("Brier decomposition paper evidence", () => {
  it("quotes four remainders equal to direct Brier minus reconstructed Brier", () => {
    const rows = table("Murphy decomposition by sport and side").rows;
    expect(rows).toHaveLength(4);
    for (const [sport, side, n, brier, reliability, resolution, uncertainty, reconstructed, remainder] of rows) {
      const block = murphy.sports[sport][side === "model" ? "model_prob" : "market_prob"];
      expect([n, brier, reliability, resolution, uncertainty, reconstructed]).toEqual([
        String(block.n), block.brier.toFixed(6), block.reliability.toFixed(6),
        block.resolution.toFixed(6), block.uncertainty.toFixed(6), block.reconstructed_brier.toFixed(6),
      ]);
      expect(Number(remainder), `${sport} ${side}`).toBeCloseTo(block.brier - block.reconstructed_brier, 6);
    }
    // the same four figures carry the abstract
    for (const signed of ["+0.000518", "-0.000377", "-0.065642", "-0.066812"]) {
      expect(prose).toContain(signed);
    }
  });

  it("reports the MLB remainders as small and opposite in sign, not as a 0.0005 tolerance", () => {
    const model = murphy.sports.mlb.model_prob;
    const market = murphy.sports.mlb.market_prob;
    expect(model.brier - model.reconstructed_brier).toBeCloseTo(0.000518, 6);
    expect(market.brier - market.reconstructed_brier).toBeCloseTo(-0.000377, 6);
    expect(Math.abs(model.brier - model.reconstructed_brier)).toBeGreaterThan(0.0005);
    expect(prose).not.toMatch(/within 0\.0005/i);
    expect(prose).toContain("small and opposite in sign");
  });

  it("keeps the soccer remainders without naming a cause for them", () => {
    const model = murphy.sports.soccer_intl.model_prob;
    const market = murphy.sports.soccer_intl.market_prob;
    expect(model.brier - model.reconstructed_brier).toBeCloseTo(-0.065642, 6);
    expect(market.brier - market.reconstructed_brier).toBeCloseTo(-0.066812, 6);
    expect(prose).toContain("no second bin count and no per-bin residual");
  });

  it("drops the causal story and the honesty judgement", () => {
    expect(prose).not.toMatch(/pitching change/i);
    expect(prose).not.toMatch(/injur/i);
    expect(prose).not.toMatch(/weather/i);
    expect(prose).not.toMatch(/nearly as honest/i);
    expect(prose).toContain("not about why the two forecasts differ");
  });

  it("keeps the classified phase rows apart from the corpus total", () => {
    const grains = skill.sports.mlb.grains;
    const named = ["early(inn1-3)", "mid(inn4-6)", "late(inn7+)"].reduce((sum, key) => sum + grains[key].n, 0);
    expect(named).toBe(52646);
    expect(grains.all.n).toBe(78986);
    const caution = paragraph("52,646 rows");
    expect(caution).toContain("78,986");
    expect(caution).toContain("26,340");
    expect(prose).toContain("52,646 of the all grain's 78,986 MLB rows");
  });

  it("says which timestamp is the artifact's, which the manifest's and which the insight's", () => {
    expect(skill.generated_at).toBe("2026-07-25T11:12:35.314040+00:00");
    expect(moduleAsOf("brier_skill_scores")).toBe("2026-07-25T04:34:43.456609+00:00");
    expect(insight.as_of).toBe("2026-07-24T01:08:43.969532+00:00");
    expect(murphy).not.toHaveProperty("generated_at");
    expect(murphy).not.toHaveProperty("as_of");
    expect(moduleAsOf("murphy_decomposition")).toBeNull();

    const dates = paragraph("Dates:");
    expect(dates).toContain("carries neither generated_at nor as_of");
    expect(dates).toContain("generated_at 2026-07-25T11:12:35Z, which is when that artifact was produced");
    expect(dates).toContain("site_manifest.json publishes the module with as_of 2026-07-25T04:34:43Z");
    expect(dates).toContain("insights/brier_skill_scores.json file carries as_of 2026-07-24T01:08:43Z");
  });

  it("opens Results with the MLB withdrawal status and repeats it in the abstract", () => {
    const results = paper.sections.find(section => section.id === "results");
    const first = results?.blocks[0] as TextBlock & { label?: string };
    expect(first.type).toBe("callout");
    expect(first.label).toBe("Status");
    expect(first.text).toContain("withdrawn");
    expect(first.text).toContain("126 of the 227");
    expect(first.text).toContain("27,076 of 78,986");
    const sentences = paper.abstract.split(/(?<=\.)\s+/);
    expect(sentences[sentences.length - 1]).toContain("Status:");
    expect(sentences[sentences.length - 1]).toContain("withdrawn");
    expect(paper.related).toContainEqual({ kind: "finding", id: "ingame-join-integrity" });
  });

  it("passes the paper validator and its forbidden-vocabulary scan", () => {
    expect(validatePaper(paper, publishedArtifacts())).toBeNull();
    for (const value of paperStrings(paper)) expect(PROHIBITED_TOKEN_RE.test(value)).toBe(false);
  });
});
