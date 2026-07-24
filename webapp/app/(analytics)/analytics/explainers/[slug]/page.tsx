// One long-form explainer (editorial reading column, DESIGN Sec 2). Static
// export: generateStaticParams emits the 6 slugs from explainers.json; an
// unknown slug 404s (dynamicParams=false), matching the terminal's
// evidence/[claim] pattern. body_md is light markdown (paragraphs, one bullet
// block, `code`, **bold**, *italic*) rendered with a small inline parser --
// no markdown dependency, "three" is the only approved add for this product.
//
// Scout questions are DERIVED, not hand-curated: each essay's own "cited"
// list names an ask/<bucket>.json file, and the 3 shown questions are the
// best keyword-scored matches from that bucket in the real ask corpus (with
// any edge/ROI-worded corpus question excluded, per the no-edge rail).
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { CSSProperties, ReactNode } from "react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ScoutQuestions } from "@/components/analytics/ScoutQuestions";

type Essay = {
  slug: string;
  title: string;
  dek: string;
  body_md: string;
  cited: string[];
};
type CorpusEntry = { q: string; bucket?: string };

const EXPLAINERS_PATH = join(
  process.cwd(),
  "public",
  "data",
  "explainers",
  "explainers.json"
);
const CORPUS_PATH = join(process.cwd(), "public", "data", "ask", "corpus.json");
const EDGE_WORDS = /edge|\broi\b|profit|\$/i;

function readEssays(): Essay[] {
  const raw = readFileSync(EXPLAINERS_PATH, "utf8");
  return (JSON.parse(raw) as { essays?: Essay[] }).essays || [];
}

function readCorpus(): CorpusEntry[] {
  try {
    const raw = readFileSync(CORPUS_PATH, "utf8");
    return (JSON.parse(raw) as { entries?: CorpusEntry[] }).entries || [];
  } catch {
    return [];
  }
}

// Map this essay's "cited" ask/*.json paths to their corpus bucket names.
function citedBuckets(cited: string[]): Set<string> {
  const out = new Set<string>();
  for (const c of cited) {
    const m = c.match(/ask\/([a-z0-9_-]+)\.json$/i);
    if (m) out.add(m[1].replace(/-/g, "_"));
  }
  return out;
}

function keywordsFor(e: Essay): string[] {
  return `${e.slug} ${e.title}`
    .toLowerCase()
    .split(/[^a-z0-9]+/)
    .filter((w) => w.length > 3);
}

function scoutQuestionsFor(e: Essay): string[] {
  const buckets = citedBuckets(e.cited);
  if (buckets.size === 0) return [];
  const candidates = readCorpus().filter(
    (en) =>
      buckets.has((en.bucket || "").replace(/-/g, "_")) && !EDGE_WORDS.test(en.q)
  );
  const kws = keywordsFor(e);
  const scored = candidates.map((en, idx) => {
    const hay = en.q.toLowerCase();
    const score = kws.reduce((n, k) => n + (hay.includes(k) ? 1 : 0), 0);
    return { en, idx, score };
  });
  scored.sort((a, b) => b.score - a.score || a.idx - b.idx);
  return scored.slice(0, 3).map((s) => s.en.q);
}

// Minimal inline-markdown renderer: `code`, **bold**, *italic*. Order matters --
// the double-asterisk alternative is tried before the single one.
function renderInline(text: string): ReactNode[] {
  return text
    .split(/(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*)/g)
    .map((seg, i) => {
      if (!seg) return null;
      if (seg.startsWith("`") && seg.endsWith("`")) {
        return (
          <code key={i} className="mono" style={inlineCode}>
            {seg.slice(1, -1)}
          </code>
        );
      }
      if (seg.startsWith("**") && seg.endsWith("**")) {
        return (
          <strong key={i} style={{ color: "var(--ink)", fontWeight: 600 }}>
            {seg.slice(2, -2)}
          </strong>
        );
      }
      if (seg.startsWith("*") && seg.endsWith("*")) {
        return <em key={i}>{seg.slice(1, -1)}</em>;
      }
      return <span key={i}>{seg}</span>;
    })
    .filter(Boolean);
}

function renderBody(body: string): ReactNode[] {
  return body.split(/\n\n+/).map((block, i) => {
    const trimmed = block.trim();
    if (/^- /.test(trimmed)) {
      const items = trimmed.split(/\n/).map((l) => l.replace(/^- /, ""));
      return (
        <ul key={i} style={ulStyle}>
          {items.map((it, j) => (
            <li key={j} style={liStyle}>
              {renderInline(it)}
            </li>
          ))}
        </ul>
      );
    }
    return (
      <p key={i} style={pStyle}>
        {renderInline(trimmed)}
      </p>
    );
  });
}

export const dynamicParams = false;

export function generateStaticParams() {
  return readEssays().map((e) => ({ slug: e.slug }));
}

export function generateMetadata({
  params,
}: {
  params: { slug: string };
}): Metadata {
  const essay = readEssays().find((e) => e.slug === params.slug);
  return {
    title: essay ? essay.title : "Explainer",
    description: essay?.dek || "A long-form CourtVision Analytics explainer.",
  };
}

const inlineCode: CSSProperties = {
  fontSize: "0.88em",
  background: "var(--paper-tint)",
  padding: "1px 5px",
  borderRadius: 4,
  color: "var(--ink)",
};
const h1: CSSProperties = {
  fontFamily: "var(--font-display)",
  fontWeight: 500,
  fontSize: "clamp(1.9rem,4vw,2.6rem)",
  lineHeight: 1.1,
  letterSpacing: "-.015em",
  color: "var(--ink)",
  marginTop: 10,
};
const dekStyle: CSSProperties = {
  fontSize: 19,
  lineHeight: 1.5,
  color: "var(--ink-2)",
  marginTop: 16,
};
const pStyle: CSSProperties = {
  fontSize: 19,
  lineHeight: 1.62,
  color: "var(--ink-2)",
  marginTop: 22,
};
const ulStyle: CSSProperties = {
  marginTop: 22,
  paddingLeft: 22,
  display: "flex",
  flexDirection: "column",
  gap: 8,
};
const liStyle: CSSProperties = { fontSize: 19, lineHeight: 1.5, color: "var(--ink-2)" };
const backLink: CSSProperties = { fontSize: 13, fontWeight: 600, color: "var(--accent)" };
const sourcesWrap: CSSProperties = {
  marginTop: 48,
  paddingTop: 20,
  borderTop: "1px solid var(--rule)",
};
const sourceItem: CSSProperties = {
  fontFamily: "var(--font-mono)",
  fontSize: "11.5px",
  color: "var(--ink-3)",
  wordBreak: "break-all",
  display: "block",
  marginTop: 6,
};

export default function ExplainerPage({ params }: { params: { slug: string } }) {
  const essays = readEssays();
  const essay = essays.find((e) => e.slug === params.slug);
  if (!essay) notFound();

  const idx = essays.indexOf(essay);
  const next = essays[(idx + 1) % essays.length];

  return (
    <article className="wrap" style={{ paddingTop: 40, paddingBottom: 64 }}>
      <Link href="/analytics/explainers" style={backLink}>
        &larr; Explainers
      </Link>

      <div style={{ maxWidth: 680 }}>
        <p className="overline" style={{ marginTop: 22 }}>
          Explainer
        </p>
        <h1 style={h1}>{essay.title}</h1>
        <p style={dekStyle}>{essay.dek}</p>

        <div>{renderBody(essay.body_md)}</div>

        <div style={sourcesWrap}>
          <p className="overline">Sources</p>
          {essay.cited.map((c) => (
            <span key={c} style={sourceItem}>
              {c}
            </span>
          ))}
        </div>

        <ScoutQuestions questions={scoutQuestionsFor(essay)} heading="Ask Scout about this" />

        <p style={{ marginTop: 40, paddingTop: 20, borderTop: "1px solid var(--rule)" }}>
          <span style={{ fontSize: 13, color: "var(--ink-3)" }}>Next explainer</span>
          <br />
          <Link
            href={`/analytics/explainers/${next.slug}`}
            style={{ fontFamily: "var(--font-display)", fontSize: 19, color: "var(--ink)" }}
          >
            {next.title} &rarr;
          </Link>
        </p>
      </div>
    </article>
  );
}
