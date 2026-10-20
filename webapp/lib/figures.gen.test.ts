import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import ts from "typescript";
import { describe, expect, it } from "vitest";
import { DEFAULT_IN, FiguresError, generate, generateFromFile, main } from "../scripts/gen-figures.mjs";

/** Evaluates the generated TypeScript module in-process (types stripped) and returns its exports. */
function load(text: string): Record<string, any> {
  const js = ts.transpileModule(text, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 } }).outputText;
  const mod = { exports: {} as Record<string, any> };
  new Function("exports", "module", js)(mod.exports, mod);
  return mod.exports;
}

const SCRIPT = resolve(__dirname, "../scripts/gen-figures.mjs");

const fixture = {
  schema: "canonical_figures/v1",
  as_of: "2026-10-06",
  retracted_tokens: ["+18.38%"],
  canonical_counts: {
    figures: [
      { key: "published_module_count", value: 77, as_of: "2026-10-19", pattern: "(\\d+) modules", source: "module_count in site_manifest.json" },
      { key: "g6_status", value: "has not started as of 2026-10-19 (zero weeks collected)", as_of: "2026-10-19", forbidden: "(?i)zero qualifying weeks", source: "docs/GO_LIVE_GATES.md G6 row" },
    ],
  },
  figures: [
    {
      key: "nba_ml_pregame_vs_close_shin", sport: "nba", market: "moneyline", metric: "Brier", devig: "shin",
      n: 372, model: 0.1735, close: 0.1666, gap: 0.0069, ci95: [-0.0038, 0.0175], dm_p: "0.20", mde: 0.0152,
      verdict: "MATCHES_CLOSE", anchor: "\\+0\\.0069\\b", source: "docs/evidence/pregame/DM_RECOMPUTE_2026-09-24.md",
      as_of: "2026-09-24", licenses: "On NBA moneyline the gap is indistinguishable from zero and underpowered.",
    },
  ],
};

describe("gen-figures", () => {
  it("turns a canonical figure JSON into a typed module", () => {
    const text = generate(fixture, "fixture.json");
    expect(text).toContain('export const FIGURES_AS_OF = "2026-10-06" as const;');
    expect(text).toContain('"published_module_count": {');
    expect(text).toContain('"kind": "count"');
    expect(text).toContain('"kind": "comparison"');
    expect(text).toContain("export type FigureKey = CountFigureKey | ComparisonFigureKey;");
    // Regex / audit-only fields never reach the module.
    expect(text).not.toContain('"pattern"');
    expect(text).not.toContain('"anchor"');
    expect(text).not.toContain('"forbidden"');

    const mod = load(text);
    expect(mod.FIGURES.published_module_count.value).toBe(77);
    expect(mod.FIGURES.nba_ml_pregame_vs_close_shin.ci95).toEqual([-0.0038, 0.0175]);
    expect(mod.FIGURES.nba_ml_pregame_vs_close_shin.verdict).toBe("MATCHES_CLOSE");
    expect(mod.FIGURE_KEYS).toEqual(["published_module_count", "g6_status", "nba_ml_pregame_vs_close_shin"]);
    expect(mod.isFigureKey("g6_status")).toBe(true);
    expect(mod.isFigureKey("nba_win_rate")).toBe(false);
    expect(mod.RETRACTED_TOKENS).toEqual(["+18.38%"]);
  });

  it("fails loudly on a malformed figure set", () => {
    expect(() => generate({ ...fixture, schema: "nope" }, "fixture.json")).toThrow(FiguresError);
    expect(() => generate({ ...fixture, schema: "nope" }, "fixture.json")).toThrow(/schema must be "canonical_figures\/v1"/);
    const dupe = { ...fixture, figures: [fixture.figures[0], fixture.figures[0]] };
    expect(() => generate(dupe)).toThrow(/duplicate key "nba_ml_pregame_vs_close_shin"/);
    const badDate = { ...fixture, canonical_counts: { figures: [{ ...fixture.canonical_counts.figures[0], as_of: "October" }] } };
    expect(() => generate(badDate)).toThrow(/"as_of" must be an ISO day/);
    const noVerdict = { ...fixture, figures: [{ ...fixture.figures[0], verdict: "" }] };
    expect(() => generate(noVerdict)).toThrow(/"verdict" must be a non-empty string/);
  });

  it("fails the build when the canonical JSON is missing", () => {
    expect(() => generateFromFile("/nonexistent/CANONICAL_FIGURES.json")).toThrow(/is missing/);
    const run = spawnSync(process.execPath, [SCRIPT, "--in", "/nonexistent/CANONICAL_FIGURES.json", "--stdout"], { encoding: "utf8" });
    expect(run.status).toBe(1);
    expect(run.stderr).toMatch(/gen-figures: .*CANONICAL_FIGURES\.json is missing/);
    expect(run.stdout).toBe("");
  });

  it("reports a stale committed module with --check and writes a fresh one otherwise", () => {
    const dir = mkdtempSync(join(tmpdir(), "figures-"));
    const out = join(dir, "figures.ts");
    writeFileSync(out, "// stale\n");
    expect(main(["--check", "--in", DEFAULT_IN, "--out", out])).toBe(1);
    expect(main(["--in", DEFAULT_IN, "--out", out])).toBe(0);
    expect(readFileSync(out, "utf8")).toContain("export const FIGURES = { ...COUNT_FIGURES, ...COMPARISON_FIGURES } as const;");
    expect(main(["--check", "--in", DEFAULT_IN, "--out", out])).toBe(0);
  });
});
