// The committed Ask Scout corpus against the site's honesty rails: no retracted
// figure, no stale counts against lib/figures.ts, and the two ledger tallies
// each named for the population they count.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { COUNT_FIGURES, COMPARISON_FIGURES, RETRACTED_TOKENS } from "@/lib/figures";
import type { AskEntry } from "./askSearch";

const corpus = (JSON.parse(readFileSync(join(process.cwd(), "public/data/ask/corpus.json"), "utf8")) as { entries: AskEntry[] }).entries;
const manifest = JSON.parse(readFileSync(join(process.cwd(), "public/data/showcase/site_manifest.json"), "utf8")) as { module_count: number };
const byQuestion = (q: string): AskEntry => {
  const entry = corpus.find((candidate) => candidate.q === q);
  if (!entry) throw new Error(`corpus entry missing: ${q}`);
  return entry;
};
const text = (entry: AskEntry) => [entry.q, ...entry.alt_phrasings, entry.a.answer].join(" ");

describe("Ask Scout corpus rails", () => {
  it("prints no retracted figure anywhere in the corpus", () => {
    const bounded = (token: string) => new RegExp(`(^|[^0-9.])${token.replace(/[+.%]/g, "\\$&")}($|[^0-9])`);
    for (const entry of corpus) {
      for (const token of RETRACTED_TOKENS) expect(text(entry), `${entry.q} prints ${token}`).not.toMatch(bounded(token));
    }
  });

  it("names the research-ledger population behind the 351 nulls to 168 confirms tally", () => {
    for (const q of ["Do you publish your failed hypotheses?", "Do nulls actually outnumber your confirmed findings?"]) {
      const answer = byQuestion(q).a.answer;
      expect(answer).toMatch(/351/);
      expect(answer).toMatch(/honesty exhibit/);
      expect(answer).toMatch(/different population/);
      expect(answer).toMatch(/89 confirmed, 74 null and 34 not-testable or other out of 197/);
      expect(answer).toContain("docs/JOB_EVIDENCE_PACKET.md line 138");
    }
  });

  it("quotes the current published module count", () => {
    expect(COUNT_FIGURES.published_module_count.value).toBe(manifest.module_count);
    for (const q of ["How many analysis modules are there?", "Where do I find a specific module?"]) {
      const entry = byQuestion(q);
      expect(entry.a.answer).toContain(`${manifest.module_count} modules`);
      expect(entry.a.answer).not.toMatch(/\b54 modules/);
      // site_manifest.json carries no top-level date, so the entry must not claim one.
      expect(entry.a.as_of).toBe("unknown");
      expect(entry.a.answer).not.toMatch(/as of \d{4}-\d{2}-\d{2}/);
    }
  });

  it("carries the forward paper window counts from the canonical figures", () => {
    const window = COMPARISON_FIGURES.forward_window_counts;
    for (const q of ["Has any real money been placed?", "Tell me about the in-play backtest headline you pulled back."]) {
      const entry = byQuestion(q);
      expect(entry.a.answer).toContain(`${window.games_served} games`);
      expect(entry.a.answer).toContain(`${window.receipt_nights} receipt nights`);
      expect(entry.a.answer).toContain(`${window.complete} COMPLETE`);
      expect(entry.a.answer).toContain(`${window.qualified_of_judged} judged games qualified`);
      expect(entry.a.answer).toContain("INSUFFICIENT");
      expect(entry.a.as_of).toBe(window.as_of);
    }
  });

  it("keeps the how-was-it-built phrasing on the dated build answer", () => {
    const entry = byQuestion("How was this AI actually built?");
    expect(entry.alt_phrasings).toContain("how was it built");
    expect(entry.a.answer).toMatch(/2026-03-09 to 2026-07-22/);
  });
});
