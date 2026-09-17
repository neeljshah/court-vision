// Locks the reliability paper to its two artifacts: every quoted cell, the gap sign
// convention, the all-state vs derived late-inning ECE labels, and the withdrawal status.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { publishedArtifacts } from "./papers.server";
import { paperStrings, validatePaper, type Paper, type PaperBlock } from "./papers";
// @ts-expect-error -- the executable scanner is deliberately dependency-free ESM.
import { PROHIBITED_TOKEN_RE } from "../../scripts/check-analytics-copy.mjs";

type Bin = {
  bin_lo: number; bin_hi: number; n: number; n_games: number;
  mean_p: number; mean_y: number; gap: number; gap_ci: [number, number]; significant: boolean;
};
type Side = "model" | "market";
type Stability = { sports: { mlb: { sides: Record<`${Side}_prob`, { bins: Bin[] }> } } };
type StateBucket = {
  time_bucket: string; prob_bucket: string; source: string;
  n: number; mean_p: number; mean_y: number; calibration_error: number;
};
type StateConditioned = {
  sports: { mlb: { model_ece_n_weighted: number; market_ece_n_weighted: number; buckets: StateBucket[] } };
};
type TableBlock = Extract<PaperBlock, { type: "table" }>;
type TextBlock = Extract<PaperBlock, { type: "p" | "callout" | "math" }>;

const read = <T,>(...parts: string[]): T =>
  JSON.parse(readFileSync(join(process.cwd(), "public", "data", ...parts), "utf8")) as T;

const paper = read<Paper>("papers", "calibration-reliability-by-sport-and-state.json");
const stability = read<Stability>("showcase", "calibration_stability.json");
const state = read<StateConditioned>("showcase", "state_conditioned_calibration.json");

const blocks = paper.sections.flatMap(section => section.blocks);
const prose = paperStrings(paper).join("\n");
const four = (value: number) => value.toFixed(4);

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
const sentenceWith = (source: string, needle: string) =>
  source.split(/(?<=\.)\s+/).find(part => part.includes(needle)) || "";

// The state artifact's coarse band labels against the band column the paper prints.
const BANDS: Record<string, string> = {
  "0-0.2": "0-.2", "0.2-0.4": ".2-.4", "0.4-0.6": ".4-.6", "0.6-0.8": ".6-.8", "0.8-1.0": ".8-1",
};

const lateCells = state.sports.mlb.buckets.filter(bucket => bucket.time_bucket === "late(inn7+)");
const lateWeighted = (source: Side) => {
  const cells = lateCells.filter(cell => cell.source === source);
  const rows = cells.reduce((sum, cell) => sum + cell.n, 0);
  return { rows, ece: cells.reduce((sum, cell) => sum + cell.calibration_error * cell.n, 0) / rows };
};

describe("reliability paper evidence", () => {
  it("quotes all twenty aggregate bin rows exactly as calibration_stability.json holds them", () => {
    const rows = table("MLB aggregate reliability bins").rows;
    const expected = (["model", "market"] as const).flatMap(side =>
      stability.sports.mlb.sides[`${side}_prob`].bins.map(bin => [
        `${bin.bin_lo.toFixed(1)}-${bin.bin_hi.toFixed(1)}`, side, String(bin.n), String(bin.n_games),
        four(bin.mean_p), four(bin.mean_y), four(bin.gap),
        `${four(bin.gap_ci[0])} to ${four(bin.gap_ci[1])}`, bin.significant ? "yes" : "no",
      ]));
    const byKey = (list: string[][]) => [...list].sort((left, right) => `${left[0]}${left[1]}`.localeCompare(`${right[0]}${right[1]}`));
    expect(rows).toHaveLength(20);
    expect(byKey(rows)).toEqual(byKey(expected));
  });

  it("quotes the ten late-inning cells exactly as state_conditioned_calibration.json holds them", () => {
    const rows = table("MLB late-inning (inn7+) state-conditioned cells").rows;
    expect(rows).toHaveLength(10);
    for (const [band, source, n, meanP, meanY, error] of rows) {
      const cell = lateCells.find(entry => entry.source === source && entry.prob_bucket === BANDS[band]);
      expect(cell, `${band} ${source}`).toBeDefined();
      expect([n, meanP, meanY, error]).toEqual([
        String(cell!.n), four(cell!.mean_p), four(cell!.mean_y), four(cell!.calibration_error),
      ]);
    }
  });

  it("states the gap sign convention the artifact actually uses", () => {
    // mean_p, mean_y and gap are each published rounded to four places, so the identity
    // holds to one unit in the last place, and never with the operands the other way round.
    for (const side of ["model_prob", "market_prob"] as const) {
      for (const bin of stability.sports.mlb.sides[side].bins) {
        const ulps = Math.abs(Math.round(bin.gap * 1e4) - Math.round((bin.mean_y - bin.mean_p) * 1e4));
        expect(ulps, `${side} ${bin.bin_lo}`).toBeLessThanOrEqual(1);
      }
    }
    expect(prose).toContain("gap = mean_y - mean_p");
    expect(prose).toContain("mean_y minus mean_p");
    expect(prose).not.toContain("mean_p minus mean_y");
    expect(prose).not.toContain("gap = mean_p - mean_y");
  });

  it("labels 0.0494 and 0.0397 as the all-state n-weighted ECE", () => {
    expect(state.sports.mlb.model_ece_n_weighted).toBe(0.0494);
    expect(state.sports.mlb.market_ece_n_weighted).toBe(0.0397);
    const said = paragraph("model_ece_n_weighted");
    expect(said).toContain("all-state");
    expect(said).toContain("0.0494");
    expect(said).toContain("0.0397");
    expect(sentenceWith(paper.abstract, "0.0494")).toContain("all-state");
    expect(sentenceWith(paper.abstract, "0.0494")).not.toMatch(/late.inning/i);
    // the withdrawn revision-1 pair may appear only where the paper retracts it
    expect(prose).not.toMatch(/0\.079 model against 0\.0591 market/);
  });

  it("derives the late-inning ECE from the published cells and says it is derived", () => {
    const model = lateWeighted("model");
    const market = lateWeighted("market");
    expect(model.rows).toBe(7442);
    expect(market.rows).toBe(7442);
    expect(model.ece).toBeCloseTo(0.0395, 4);
    expect(market.ece).toBeCloseTo(0.0454, 4);
    const said = paragraph("derived");
    expect(said).toContain(four(model.ece));
    expect(said).toContain(four(market.ece));
    expect(said).toContain("7,442");
    expect(said).toContain("late(inn7+)");
  });

  it("opens Results with the MLB withdrawal status and repeats it in the abstract", () => {
    const results = paper.sections.find(section => section.id === "results");
    const first = results?.blocks[0] as TextBlock & { label?: string };
    expect(first.type).toBe("callout");
    expect(first.label).toBe("Status");
    expect(first.text).toContain("withdrawn");
    expect(first.text).toContain("126 of the 227");
    expect(first.text).toContain("27,076 of 78,986");
    expect(first.text).toContain("1 of the 51 international-soccer files");
    const sentences = paper.abstract.split(/(?<=\.)\s+/);
    expect(sentences[sentences.length - 1]).toContain("Status:");
    expect(sentences[sentences.length - 1]).toContain("withdrawn");
    expect(paper.related).toContainEqual({ kind: "finding", id: "ingame-join-integrity" });
  });

  it("retracts the revision-1 top-bin and late-cell conclusions instead of restating them", () => {
    const top = stability.sports.mlb.sides.model_prob.bins[9];
    expect([top.gap, top.significant]).toEqual([0.0282, false]);
    const lateHigh = lateCells.find(cell => cell.source === "model" && cell.prob_bucket === ".8-1");
    expect(lateHigh?.calibration_error).toBe(0.0397);
    // Both headline misses of revision 1 are gone from the data, so each may appear exactly once,
    // inside the paragraph that withdraws it, and never as a current reading.
    for (const withdrawn of ["-0.2909", "0.2357"]) {
      const carriers = blocks.filter(
        block => (block.type === "p" || block.type === "callout") && block.text.includes(withdrawn));
      expect(carriers, withdrawn).toHaveLength(1);
      const said = (carriers[0] as TextBlock).text;
      expect(said, withdrawn).toMatch(/revision 1/i);
      expect(said, withdrawn).toContain("an artifact of the join defect");
    }
    // and the values that replaced them are the ones the paper reports
    expect(prose).toContain(four(top.gap));
    expect(prose).toContain(four(lateHigh!.calibration_error));
  });

  it("drops the claims that overreach the evidence", () => {
    expect(prose).not.toMatch(/perfectly calibrated/i);
    expect(prose).not.toMatch(/non-overlapping/i);
    expect(prose).not.toMatch(/underpowered/i);
    expect(prose).toContain("not identically selected");
    expect(prose).toContain("they do not establish that the two sets are disjoint");
    expect(prose).toContain("A significant interval is a departure that was detected, not a measure of how much data stands behind it");
  });

  it("passes the paper validator and its forbidden-vocabulary scan", () => {
    expect(validatePaper(paper, publishedArtifacts())).toBeNull();
    for (const value of paperStrings(paper)) expect(PROHIBITED_TOKEN_RE.test(value)).toBe(false);
  });
});
