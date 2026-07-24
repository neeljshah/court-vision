"use client";
// Ask Scout (Tier-2) -- a CLIENT-SIDE router over the committed ask corpus.
// No LLM, no network, no fetch: tokenize the question, score it against every
// entry's q + alt_phrasings + tags, render the best precomputed envelope, and
// show an honest NO_DATA (with the closest citable answer) when nothing clears
// threshold. Consumes the Receipt foundation export for every citation.
// DESIGN_ANALYTICS Sec. 6 + mockups/ask.html.
import { useEffect, useMemo, useState, type CSSProperties, type ReactNode } from "react";
import { Receipt, type ReceiptData } from "./Receipt";
import type { Verdict } from "./VerdictDot";

export type AskStatus = "ok" | "no_data" | "refused";
export interface AskAnswer {
  status: AskStatus;
  answer: string;
  source_artifact: string;
  as_of?: string;
}
export interface AskEntry {
  q: string;
  alt_phrasings: string[];
  tags: string[];
  bucket: string;
  a: AskAnswer;
}
export interface AskTour {
  label: string;
  questions: string[];
}

// ---- pure router (exported so its scoring can be reasoned about in isolation) --
const STOP = new Set(
  ("the a an is are was were be it of to do does did what how why when who which for " +
    "on in at by vs and or my you your me i can will would should tell about any this " +
    "that with as from has have not no there").split(" ")
);
const norm = (s: string) =>
  s.toLowerCase().replace(/[^a-z0-9\s]/g, " ").replace(/\s+/g, " ").trim();
const toks = (s: string) =>
  Array.from(new Set(norm(s).split(" ").filter((t) => t.length > 1 && !STOP.has(t))));

interface Idx {
  terms: Set<string>;
  norms: string[];
}
function buildIndex(entries: AskEntry[]): Idx[] {
  return entries.map((e) => {
    const terms = new Set<string>();
    toks(e.q).forEach((t) => terms.add(t));
    (e.alt_phrasings || []).forEach((p) => toks(p).forEach((t) => terms.add(t)));
    (e.tags || []).forEach((tag) => toks(tag).forEach((t) => terms.add(t)));
    return { terms, norms: [norm(e.q), ...(e.alt_phrasings || []).map(norm)] };
  });
}
// ponytail: linear scan over ~236 entries per submit is trivially fast; no worker
// or prebuilt search index until the corpus is 100x larger.
function score(q: string, ix: Idx): number {
  const qn = norm(q);
  let s = 0;
  for (const t of toks(q)) if (ix.terms.has(t)) s += 1;
  for (const n of ix.norms) {
    if (!n) continue;
    if (n === qn) s += 5;
    else if (qn.length > 3 && (n.includes(qn) || qn.includes(n))) s += 2;
  }
  return s;
}
const THRESHOLD = 2;
export interface Resolved {
  entry: AskEntry;
  matched: boolean;
}
export function resolveQuestion(q: string, entries: AskEntry[], index: Idx[]): Resolved | null {
  if (!toks(q).length) return null;
  let best = -1;
  let bi = -1;
  index.forEach((ix, i) => {
    const s = score(q, ix);
    if (s > best) {
      best = s;
      bi = i;
    }
  });
  if (bi < 0) return null;
  return { entry: entries[bi], matched: best >= THRESHOLD };
}

// ---- verdict / receipt mapping (honest defaults: ok never over-claims green) --
const VMAP: Record<AskStatus, { verdict: Verdict; label: string }> = {
  ok: { verdict: "descriptive_only", label: "CITED" },
  no_data: { verdict: "not_testable", label: "NO_DATA" },
  refused: { verdict: "not_testable", label: "NOT ADVICE" },
};
function chipFor(a: AskAnswer): ReceiptData {
  const m = VMAP[a.status] || VMAP.ok;
  const asOf = a.as_of && a.as_of !== "unknown" ? a.as_of : undefined;
  return { sourceArtifact: a.source_artifact, asOf, verdict: m.verdict, label: m.label };
}

// ---- styles (mirror mockups/ask.html; tokens from analytics-tokens.css) -------
const barS: CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 10,
  background: "var(--paper-raised)",
  border: "1px solid var(--rule-strong)",
  borderRadius: "var(--radius-pill, 999px)",
  padding: "10px 10px 10px 18px",
  boxShadow: "var(--shadow-card)",
};
const glyphS = (neutral: boolean): CSSProperties => ({
  width: 24,
  height: 24,
  borderRadius: "50%",
  background: neutral ? "var(--null)" : "var(--signal)",
  flex: "0 0 auto",
  opacity: 0.9,
});
const inputS: CSSProperties = {
  border: 0,
  background: "transparent",
  flex: 1,
  minWidth: 0,
  fontFamily: "var(--font-sans)",
  fontSize: 16,
  color: "var(--ink)",
  outline: "none",
};
const askBtn: CSSProperties = {
  border: 0,
  background: "var(--accent)",
  color: "var(--accent-ink-on, #fff)",
  fontFamily: "var(--font-sans)",
  fontWeight: 600,
  fontSize: 15,
  padding: "10px 20px",
  borderRadius: "var(--radius-pill, 999px)",
  cursor: "pointer",
};
const pill: CSSProperties = {
  fontSize: 13,
  color: "var(--accent)",
  border: "1px solid var(--rule-strong)",
  borderRadius: "var(--radius-pill, 999px)",
  padding: "6px 13px",
  background: "var(--paper-raised)",
  cursor: "pointer",
  fontFamily: "var(--font-sans)",
  textAlign: "left",
};
const envS = (neutral: boolean): CSSProperties => ({
  background: "var(--paper-tint)",
  borderLeft: `2px solid ${neutral ? "var(--null)" : "var(--accent)"}`,
  borderRadius: "var(--radius-card, 10px)",
  padding: "20px 22px",
  display: "flex",
  gap: 14,
  marginBottom: 16,
});
const envGlyph = (neutral: boolean): CSSProperties => ({
  width: 26,
  height: 26,
  borderRadius: "50%",
  background: neutral ? "var(--null)" : "var(--signal)",
  flex: "0 0 auto",
  opacity: 0.9,
});
const qLabel: CSSProperties = { fontSize: 13, color: "var(--ink-3)", marginBottom: 6 };
const answerS: CSSProperties = { fontSize: 15.5, color: "var(--ink-2)", lineHeight: 1.6 };
const chipRow: CSSProperties = { display: "flex", flexWrap: "wrap", gap: "6px 16px", marginTop: 10 };

function Envelope({ r, query }: { r: Resolved; query: string }): ReactNode {
  const a = r.entry.a;
  const neutral = !r.matched || a.status !== "ok";
  const chip = <Receipt {...chipFor(a)} />;
  return (
    <div style={envS(neutral)}>
      <span aria-hidden style={envGlyph(neutral)} />
      <div style={{ minWidth: 0 }}>
        <div style={qLabel}>{query}</div>
        {r.matched ? (
          <div style={answerS}>
            {a.answer}
            <div style={chipRow}>{chip}</div>
          </div>
        ) : (
          <div style={answerS}>
            <strong style={{ color: "var(--ink)", fontWeight: 600 }}>No verified answer. </strong>
            Scout has no verified answer for that. The closest thing it can cite:
            <div
              style={{
                marginTop: 10,
                paddingTop: 10,
                borderTop: "1px solid var(--rule)",
              }}
            >
              <div style={{ ...qLabel, fontStyle: "italic" }}>{r.entry.q}</div>
              {a.answer}
              <div style={chipRow}>{chip}</div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export function AskBox({ entries, tours }: { entries: AskEntry[]; tours: AskTour[] }) {
  const index = useMemo(() => buildIndex(entries), [entries]);
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<Resolved | null>(null);

  const run = (q: string) => {
    setQuery(q);
    setResult(resolveQuestion(q, entries, index));
  };

  // ?q= prefill (static export -> read the URL on mount, resolve once).
  useEffect(() => {
    if (typeof window === "undefined") return;
    const q = new URLSearchParams(window.location.search).get("q");
    if (q) run(q);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div>
      <form
        style={barS}
        onSubmit={(e) => {
          e.preventDefault();
          run(query);
        }}
      >
        <span aria-hidden style={glyphS(false)} />
        <input
          style={inputS}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Ask Scout about a player, team, or metric..."
          aria-label="Ask Scout a question"
          enterKeyHint="search"
        />
        <button type="submit" style={askBtn}>
          Ask
        </button>
      </form>

      <div style={{ margin: "16px 0 10px" }}>
        {tours.map((t) => (
          <div key={t.label} style={{ marginBottom: 12 }}>
            <span
              className="overline"
              style={{ display: "block", marginBottom: 6, color: "var(--ink-3)" }}
            >
              {t.label}
            </span>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {t.questions.map((q) => (
                <button key={q} type="button" style={pill} onClick={() => run(q)}>
                  {q}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>

      <p style={{ fontSize: 13, color: "var(--ink-3)", margin: "8px 0 28px" }}>
        No LLM runs here. This is a router over a committed answers corpus -- exact
        numbers, exact sources, honest NO_DATA.
      </p>

      <div aria-live="polite">
        {result ? <Envelope r={result} query={query} /> : null}
      </div>
    </div>
  );
}

export default AskBox;
