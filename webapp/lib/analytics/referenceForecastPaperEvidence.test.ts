// Locks the reference-forecast paper to its three artifacts: the recounted Wilson
// exclusions, the seven MLB games that sit in no displayed band, the soccer paired and
// unpaired deltas that share a sign, and the dead-heat phrase the review removed.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { publishedArtifacts } from "./papers.server";
import { paperStrings, validatePaper, type Paper, type PaperBlock } from "./papers";
// @ts-expect-error -- the executable scanner is deliberately dependency-free ESM.
import { PROHIBITED_TOKEN_RE } from "../../scripts/check-analytics-copy.mjs";

type Bucket = { lo: number; hi: number; n: number; impl: number; real: number; gap: number; wilson_lo: number; wilson_hi: number };
type Longshot = { sports: Record<string, { n_total: number; buckets: Bucket[]; verdict: string }> };
type Paired = { n: number; brier_t24h?: number; brier_close?: number; brier_delta_t24h_minus_close?: number; close_sharper?: boolean };
type Decay = {
  sports: Record<string, { n_games_joined: number; buckets: Record<string, { n: number; brier?: number }>; close_vs_t24h_paired: Paired }>;
  verdict: string;
};
type Accuracy = { headline: string; sports: Record<string, { n_shared: number; books: { book: string; brier: number; n: number }[] }> };
type TableBlock = Extract<PaperBlock, { type: "table" }>;
type TextBlock = Extract<PaperBlock, { type: "p" | "callout" | "math" }>;

const read = <T,>(...parts: string[]): T =>
  JSON.parse(readFileSync(join(process.cwd(), "public", "data", ...parts), "utf8")) as T;

const paper = read<Paper>("papers", "how-accurate-is-the-reference-forecast.json");
const longshot = read<Longshot>("showcase", "market_favorite_longshot.json");
const decay = read<Decay>("showcase", "micro_closing_decay.json");
const accuracy = read<Accuracy>("showcase", "bookmaker_accuracy.json");

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
/** The paper's stated rule: the band's Wilson interval excludes its own mean implied rate. */
const excludesImplied = (bucket: Bucket) => bucket.impl < bucket.wilson_lo || bucket.impl > bucket.wilson_hi;

describe("reference-forecast paper evidence", () => {
  it("counts two tennis bands and zero MLB bands whose Wilson interval excludes the implied rate", () => {
    const tennis = longshot.sports.tennis.buckets.filter(excludesImplied);
    const mlb = longshot.sports.mlb.buckets.filter(excludesImplied);
    expect(tennis).toHaveLength(2);
    expect(mlb).toHaveLength(0);
    expect(tennis.map(bucket => [bucket.lo, bucket.hi])).toEqual([[0.8, 0.9], [0.9, 1.001]]);

    const recount = paragraph("Wilson interval on the realized rate");
    expect(recount).toContain("Two of tennis's five bands do");
    expect(recount).toContain("None of MLB's four do");
    for (const bucket of tennis) {
      expect(recount).toContain(`impl ${bucket.impl}`);
      expect(recount).toContain(`wilson_lo ${bucket.wilson_lo}`);
    }
    // the closest MLB band is named with the margin by which it still contains its implied rate
    const closest = longshot.sports.mlb.buckets.reduce((best, bucket) =>
      bucket.impl - bucket.wilson_lo < best.impl - best.wilson_lo ? bucket : best);
    expect(closest.lo).toBe(0.65);
    expect(Number((closest.impl - closest.wilson_lo).toFixed(4))).toBe(0.0005);
    expect(recount).toContain("impl 0.6870 sits 0.0005 inside wilson_lo 0.6865");
    // the withdrawn miscount may not reappear
    expect(prose).not.toContain("Every one of tennis's five bands");
    expect(prose).not.toMatch(/three of MLB's four/);
  });

  it("discloses the seven MLB games that sit in the total and in no displayed band", () => {
    const mlb = longshot.sports.mlb;
    const inBands = mlb.buckets.reduce((sum, bucket) => sum + bucket.n, 0);
    expect(inBands).toBe(27976);
    expect(mlb.n_total - inBands).toBe(7);
    const tennis = longshot.sports.tennis;
    expect(tennis.buckets.reduce((sum, bucket) => sum + bucket.n, 0)).toBe(tennis.n_total);

    const disclosure = paragraph("27,976 games");
    expect(disclosure).toContain("n_total of 27,983");
    expect(disclosure).toContain("seven games sit in the total and in no displayed band");
    expect(disclosure).toContain("Tennis's five bands sum to its n_total exactly");
  });

  it("reports the paired and unpaired soccer deltas as the same sign, eleven times apart", () => {
    const paired = decay.sports.soccer_intl.close_vs_t24h_paired;
    const buckets = decay.sports.soccer_intl.buckets;
    const unpaired = Number((buckets["T-24h"].brier! - buckets.close.brier!).toFixed(6));
    expect(paired.n).toBe(7);
    expect(paired.brier_delta_t24h_minus_close).toBe(-0.021289);
    expect(unpaired).toBe(-0.001906);
    // both negative: neither reading says the close is sharper
    expect(paired.brier_delta_t24h_minus_close!).toBeLessThan(0);
    expect(unpaired).toBeLessThan(0);
    expect(Math.sign(paired.brier_delta_t24h_minus_close!)).toBe(Math.sign(unpaired));
    expect(paired.brier_delta_t24h_minus_close! / unpaired).toBeGreaterThan(10);
    expect(paired.close_sharper).toBe(false);

    const comparison = paragraph("-0.001906");
    expect(comparison).toContain("a delta of -0.021289");
    expect(comparison).toContain("Both are negative in the artifact's t24h-minus-close convention");
    expect(comparison).toContain("they differ only in magnitude, by about elevenfold");
    // the invented reversal is gone from every string in the paper
    expect(prose).not.toMatch(/reverses the sign/i);
    expect(prose).not.toMatch(/disagreeing, samples/i);
    expect(prose).not.toMatch(/even larger reversal/i);
  });

  it("keeps wnba unpaired and names its zero paired denominator", () => {
    expect(decay.sports.wnba.close_vs_t24h_paired.n).toBe(0);
    expect(decay.sports.wnba.buckets["T-24h"].n).toBe(0);
    expect(paragraph("close_vs_t24h_paired.n is 0")).toContain("no paired test exists for wnba at all");
  });

  it("quotes the source headline's dead heat without adopting it as a result", () => {
    expect(accuracy.headline).toContain("statistical dead heat");
    const rows = table("Source comparison by sport and market").rows;
    const published = Object.entries(accuracy.sports).flatMap(([sport, block]) =>
      block.books.map(book => [sport, book.book, book.brier.toFixed(4), block.n_shared.toLocaleString("en-US")]));
    expect(rows).toHaveLength(published.length);
    // every published source-sport row is in the table, and no gap is called distinguishable
    for (const [sport, book, brier, shared] of published) {
      const row = rows.find(entry => entry[0].toLowerCase() === sport && entry[2] === book);
      expect(row, `${sport} ${book}`).toBeTruthy();
      expect([row![3], row![4], row![5]]).toEqual([brier, shared, "not published"]);
    }
    const results = paragraph("barely sharpest");
    expect(results).toContain("This paper reports similar point estimates instead");
    expect(results).toContain("so a dead heat is not established here");
    expect(paper.abstract).toContain("the named sources post similar point estimates and no pairwise uncertainty is published");
    expect(paper.abstract).not.toContain("statistical dead heat");
  });

  it("passes the paper validator and its forbidden-vocabulary scan", () => {
    expect(validatePaper(paper, publishedArtifacts())).toBeNull();
    for (const value of paperStrings(paper)) expect(PROHIBITED_TOKEN_RE.test(value)).toBe(false);
  });
});
