// Locks the MLB leaderboard paper to its artifacts: the metric's published label (called
// OR swung, never "called strikes"), the recounted contact subgroups, the 15-up-and-15-down
// truncation, and mlb_shrinkage restated as a separate fit rather than the leaderboard's own.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { publishedArtifacts } from "./papers.server";
import { paperStrings, validatePaper, type Paper, type PaperBlock } from "./papers";
// @ts-expect-error -- the executable scanner is deliberately dependency-free ESM.
import { PROHIBITED_TOKEN_RE } from "../../scripts/check-analytics-copy.mjs";

type Row = { name: string; n_ooz_called: number; ooz_strike_rate: number };
type Group = { label: string; floor?: string; corpus_id?: string; n_qualified: number; top: Row[]; bottom: Row[] };
type Leaderboards = { catcher_ooz: Group; umpire_ooz: Group; umpire_totals_gate: { verdict: string; n_umpires: number } };
type ShrinkGroup = {
  key: string; label: string; n_entities: number; pooled_mean: number; alpha: number; beta: number; kappa: number;
  biggest_regressors: { name: string; n: number; raw_rate: number; shrunk_rate: number; regression: number }[];
  top_by_shrunk: { name: string; n: number; raw_rate: number; shrunk_rate: number }[];
};
type Shrinkage = { method: string; confounds: string[]; groups: ShrinkGroup[] };
type Entry = {
  entity: string;
  key_numbers: { pitches_faced: number; n_batted_balls: number; avg_exit_velo: number; exit_velo_p90: number };
};
type Batters = { n_entries: number; entries: Entry[] };
type TableBlock = Extract<PaperBlock, { type: "table" }>;
type TextBlock = Extract<PaperBlock, { type: "p" | "callout" | "math" }>;

const read = <T,>(...parts: string[]): T =>
  JSON.parse(readFileSync(join(process.cwd(), "public", "data", ...parts), "utf8")) as T;

const paper = read<Paper>("papers", "catchers-umpires-and-hard-contact-mlb.json");
const boards = read<Leaderboards>("showcase", "mlb_descriptive_leaderboards.json");
const shrinkage = read<Shrinkage>("showcase", "mlb_shrinkage.json");
const batters = read<Batters>("showcase", "atlas_mlb_batters_manifest.json");

const blocks = paper.sections.flatMap(section => section.blocks);
const prose = paperStrings(paper).join("\n");
/** The artifacts carry accented names; the paper is ASCII by contract. */
const ascii = (value: string) => value.normalize("NFD").replace(/[̀-ͯ]/g, "");

const table = (caption: string): TableBlock => {
  const found = blocks.find(block => block.type === "table" && block.caption.includes(caption));
  if (!found) throw new Error(`no table captioned ${caption}`);
  return found as TableBlock;
};
const text = (needle: string): string => {
  const found = blocks.find(block =>
    (block.type === "p" || block.type === "callout" || block.type === "math") && block.text.includes(needle));
  if (!found) throw new Error(`no block containing ${needle}`);
  return (found as TextBlock).text;
};
const gap = (entry: Entry) => Number((entry.key_numbers.exit_velo_p90 - entry.key_numbers.avg_exit_velo).toFixed(1));
const ranked = [...batters.entries].sort((left, right) => gap(right) - gap(left));

describe("MLB leaderboard paper evidence", () => {
  it("names the metric called-or-swung, as the artifact's label does", () => {
    for (const group of [boards.catcher_ooz, boards.umpire_ooz]) {
      expect(group.label).toContain("Out-of-zone called/swung-strike rate");
      expect(group.label).toContain("NOT a called-strike or framing rate");
    }
    expect(paper.abstract).toContain("the artifact's 'called/swung-strike rate', which its label says is NOT a called-strike or framing rate");
    const method = text("Out-of-zone called/swung-strike rate");
    expect(method).toContain("counts out-of-zone pitches ruled a strike by call together with out-of-zone pitches the batter swung at");
    expect(method).toContain("its denominator is the entity's published n_ooz_called");
    const definition = blocks.find(block => block.type === "callout" && block.label === "Definition") as TextBlock;
    expect(definition.text).toContain("out-of-zone pitches ruled a strike by call or swung at by the batter");
    expect(definition.text).toContain("NOT a called-strike or framing rate");
    // the misnaming may not survive anywhere, title and subtitle included
    expect(prose).not.toMatch(/called-strike rate/i);
    for (const value of [paper.title, paper.subtitle, ...paper.keywords]) {
      expect(value).not.toMatch(/called.strike/i);
    }
  });

  it("recounts the contact subgroups as eight and four", () => {
    const largest = ranked.slice(0, 8);
    const smallest = ranked.slice(-8);
    expect(largest.filter(entry => entry.key_numbers.n_batted_balls < 350)).toHaveLength(8);
    expect(smallest.filter(entry => entry.key_numbers.n_batted_balls >= 290)).toHaveLength(4);
    const below = smallest.filter(entry => entry.key_numbers.n_batted_balls < 290).map(entry => entry.key_numbers.n_batted_balls);
    expect(Math.min(...below)).toBe(105);
    expect(Math.max(...below)).toBe(214);

    const recount = text("all eight of the largest gaps");
    expect(recount).toContain("fewer than 350 recorded batted balls");
    expect(recount).toContain("among the eight smallest only four sit at 290 or more");
    expect(recount).toContain("the other four sit between 105 and 214");
    expect(prose).not.toContain("seven of the eight largest");
    expect(prose).not.toContain("six of the eight smallest");
  });

  it("copies Table 3 from the manifest entries", () => {
    const rows = table("Batter contact quality").rows;
    expect(rows).toHaveLength(16);
    const expected = [...ranked.slice(0, 8), ...ranked.slice(-8)];
    rows.forEach((row, index) => {
      const entry = expected[index];
      expect(row[0]).toBe(ascii(entry.entity));
      expect([row[1], row[2], row[3], row[4], row[5]]).toEqual([
        gap(entry).toFixed(1), entry.key_numbers.avg_exit_velo.toFixed(1), entry.key_numbers.exit_velo_p90.toFixed(1),
        String(entry.key_numbers.n_batted_balls), String(entry.key_numbers.pitches_faced),
      ]);
    });
    expect(batters.n_entries).toBe(485);
  });

  it("discloses that only 15 top and 15 bottom rows are published for either group", () => {
    for (const group of [boards.catcher_ooz, boards.umpire_ooz]) {
      expect(group.top).toHaveLength(15);
      expect(group.bottom).toHaveLength(15);
      expect(group.n_qualified).toBeGreaterThan(30);
    }
    expect(boards.catcher_ooz.n_qualified - 30).toBe(83);
    expect(boards.umpire_ooz.n_qualified - 30).toBe(72);

    const disclosure = text("Neither out-of-zone group publishes a full table");
    expect(disclosure).toContain("lists 15 top and 15 bottom rows each");
    expect(disclosure).toContain("83 of the 113 catchers and 72 of the 102 umpires are counted in n_qualified and never named");
    expect(paper.abstract).toContain("each publishes only its top 15 and bottom 15 rows");
    // and the site page is no longer promised a table that does not exist
    expect(text("mlb_descriptive_leaderboards module page"))
      .toContain("no full 113-catcher or 102-umpire table is published anywhere");
    expect(prose).not.toContain("the full 113-catcher and 102-umpire tables");
  });

  it("restates mlb_shrinkage as a separate fit, not the leaderboard's own shrinkage", () => {
    const catchers = shrinkage.groups.find(group => group.key === "catcher_ooz") as ShrinkGroup;
    const umpires = shrinkage.groups.find(group => group.key === "umpire_ooz") as ShrinkGroup;
    expect([catchers.kappa, umpires.kappa]).toEqual([834.93, 2830.5]);
    expect([catchers.pooled_mean, umpires.pooled_mean]).toEqual([0.2813, 0.2813]);
    expect([catchers.n_entities, umpires.n_entities]).toEqual([boards.catcher_ooz.n_qualified, boards.umpire_ooz.n_qualified]);
    expect(shrinkage.method).toContain("shrunk_i = (k_i+alpha)/(n_i+alpha+beta)");
    expect(shrinkage.confounds.some(entry => entry.includes("a modeling choice, not a fact"))).toBe(true);
    // the leaderboard itself publishes no shrunk rate and no shrinkage target
    for (const group of [boards.catcher_ooz, boards.umpire_ooz]) {
      for (const row of [...group.top, ...group.bottom]) expect(row).not.toHaveProperty("shrunk_rate");
    }

    const floors = text("A floor exists because a rate over a handful of events");
    expect(floors).toContain("The leaderboard artifact does not shrink its published rates and names no shrinkage target for its floor");
    expect(floors).toContain("pooled_mean 0.2813, kappa 834.93 across 113 catchers and 2830.5 across 102 umpires");
    expect(floors).toContain("shrunk_i = (k_i + alpha)/(n_i + alpha + beta)");
    expect(floors).toContain("Its own confounds call that single-prior exchangeability a modeling choice, not a fact");
    expect(floors).toContain("The two artifacts are reported side by side here, not one derived from the other");
    // the withdrawn inference about what the floor guards against is gone
    expect(prose).not.toContain("quantified directly in this site's shrinkage artifact");
    expect(prose).not.toContain("a meaningful share of an entity's raw rate is still pulled toward");
    expect(paper.abstract).toContain("neither leaderboard publishes a shrunk rate of its own");
  });

  it("attributes each shrunk rate it quotes to that separate prior", () => {
    const catchers = shrinkage.groups.find(group => group.key === "catcher_ooz") as ShrinkGroup;
    const umpires = shrinkage.groups.find(group => group.key === "umpire_ooz") as ShrinkGroup;
    const pinto = catchers.top_by_shrunk[0];
    expect(ascii(pinto.name)).toBe("Rene Pinto");
    expect([pinto.raw_rate, pinto.shrunk_rate]).toEqual([0.3147, 0.3082]);
    expect(Number((pinto.raw_rate - pinto.shrunk_rate).toFixed(4))).toBe(0.0065);
    expect(text("raw_rate 0.3147 with shrunk_rate 0.3082"))
      .toContain("under that separate prior the leaderboard's top spot is 0.65 points smaller");

    const rosenberg = umpires.biggest_regressors[0];
    expect(rosenberg.name).toBe("Randy Rosenberg");
    expect([rosenberg.n, rosenberg.raw_rate, rosenberg.shrunk_rate]).toEqual([506, 0.3142, 0.2863]);
    expect(rosenberg.regression).toBe(0.0279);
    expect(text("the group's largest regression")).toContain("a shrunk_rate of 28.63 percent, a 2.79-point movement");
  });

  it("copies the catcher and umpire tables from the published rows", () => {
    for (const [caption, group] of [["Catcher out-of-zone strike rate", boards.catcher_ooz],
      ["Umpire out-of-zone strike rate", boards.umpire_ooz]] as const) {
      const rows = table(caption).rows;
      expect(rows).toHaveLength(12);
      const published = [...group.top.slice(0, 6), ...group.bottom.slice(-6)];
      rows.forEach((row, index) => {
        const source = published[index];
        expect(row[0]).toBe(ascii(source.name));
        expect(row[1]).toBe(`${(source.ooz_strike_rate * 100).toFixed(1)}%`);
        expect(row[2]).toBe(String(source.n_ooz_called));
      });
    }
    expect(boards.umpire_totals_gate.verdict).toBe("REJECT");
    expect(prose).toContain(`across ${boards.umpire_totals_gate.n_umpires} umpires`);
  });

  it("passes the paper validator and its forbidden-vocabulary scan", () => {
    expect(validatePaper(paper, publishedArtifacts())).toBeNull();
    for (const value of paperStrings(paper)) expect(PROHIBITED_TOKEN_RE.test(value)).toBe(false);
  });
});
