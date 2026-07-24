// askPicks.ts -- build-time picker for "Ask Scout" suggestion pills.
// The flagship pages seeded their pills with hand-written PARAPHRASES that the
// shipped Ask router (AskBox.resolveQuestion) never phrase-resolves, so every
// pill dead-ended on "No verified answer. Here is the closest thing...". Instead
// pull VERBATIM corpus questions (status ok) -- an exact question always phrase-
// resolves to its own ok answer -- chosen by topical keyword seeds so each page's
// pills stay on-subject. Mirrors the module page's corpusQuestions() gate. Clone-
// safe: a missing corpus returns [] and ScoutQuestions renders nothing. ASCII only.
import { readFileSync } from "node:fs";
import { join } from "node:path";

interface Entry {
  q: string;
  tags?: string[];
  a?: { status?: string };
}

// Each seed is a space-separated keyword group -> the single best-matching ok
// question (most keyword hits across q + tags). Order preserved, picks deduped;
// a seed with no keyword hit is dropped (never a fabricated or off-topic pill).
export function pickQuestions(seeds: string[]): string[] {
  let entries: Entry[] = [];
  try {
    const raw = readFileSync(join(process.cwd(), "public", "data", "ask", "corpus.json"), "utf-8");
    entries = ((JSON.parse(raw).entries as Entry[]) || []).filter((e) => e?.a?.status === "ok");
  } catch {
    return [];
  }
  const hay = (e: Entry) => (e.q + " " + (e.tags || []).join(" ")).toLowerCase();
  const used = new Set<number>();
  const out: string[] = [];
  for (const seed of seeds) {
    const kws = seed.toLowerCase().split(/\s+/).filter(Boolean);
    let best = -1;
    let bestScore = 0;
    entries.forEach((e, i) => {
      if (used.has(i)) return;
      const h = hay(e);
      const s = kws.reduce((n, k) => n + (h.includes(k) ? 1 : 0), 0);
      if (s > bestScore) {
        bestScore = s;
        best = i;
      }
    });
    if (best >= 0) {
      used.add(best);
      out.push(entries[best].q);
    }
  }
  return out;
}
