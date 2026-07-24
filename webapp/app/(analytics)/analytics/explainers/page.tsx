// Explainers index -- six long-form essays for a smart fan (DESIGN Sec 2 editorial
// typography). Reads public/data/explainers/explainers.json at build time; every
// number inside each essay is already verbatim-sourced there (see its own
// generated_note + "cited" list) -- this index only lists them. No showcase JSON
// needed, so nothing here can be missing on a fresh clone.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import type { CSSProperties } from "react";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Explainers",
  description:
    "Six long-form essays on how the possession simulator thinks, what calibration means, and why the graveyard of null results is the point.",
};

type Essay = { slug: string; title: string; dek: string; cited: string[] };

function readEssays(): Essay[] {
  const raw = readFileSync(
    join(process.cwd(), "public", "data", "explainers", "explainers.json"),
    "utf8"
  );
  const parsed = JSON.parse(raw) as { essays?: Essay[] };
  return parsed.essays || [];
}

const h1: CSSProperties = {
  fontFamily: "var(--font-display)",
  fontWeight: 500,
  fontSize: "clamp(2rem,4vw,2.75rem)",
  letterSpacing: "-.015em",
  color: "var(--ink)",
  marginTop: 8,
};
const lede: CSSProperties = {
  fontSize: 17,
  lineHeight: 1.65,
  color: "var(--ink-2)",
  maxWidth: 640,
  marginTop: 14,
};
const row: CSSProperties = {
  display: "block",
  padding: "26px 0",
  borderTop: "1px solid var(--rule)",
  textDecoration: "none",
  color: "inherit",
};
const num: CSSProperties = {
  fontFamily: "var(--font-mono)",
  fontSize: 12,
  color: "var(--ink-3)",
};
const title: CSSProperties = {
  fontFamily: "var(--font-display)",
  fontWeight: 500,
  fontSize: 25,
  letterSpacing: "-.01em",
  color: "var(--ink)",
  marginTop: 6,
};
const dek: CSSProperties = {
  fontSize: 15.5,
  lineHeight: 1.6,
  color: "var(--ink-2)",
  marginTop: 8,
  maxWidth: 640,
};
const meta: CSSProperties = {
  fontFamily: "var(--font-mono)",
  fontSize: 11.5,
  color: "var(--ink-3)",
  marginTop: 12,
};

export default function ExplainersIndexPage() {
  const essays = readEssays();

  return (
    <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }}>
      <p className="overline">Explainers</p>
      <h1 style={h1}>Long-form essays for a smart fan</h1>
      <p style={lede}>
        Six essays on how the possession simulator thinks, what calibration actually
        means, why the graveyard of null results is the point, and what the on-page
        AI can and cannot tell you. Every number inside traces back to a committed
        artifact &mdash; see each essay&rsquo;s sources at the bottom of the page.
      </p>

      <div style={{ marginTop: 28 }}>
        {essays.map((e, i) => (
          <Link key={e.slug} href={`/analytics/explainers/${e.slug}`} style={row}>
            <span style={num}>{String(i + 1).padStart(2, "0")}</span>
            <div style={title}>{e.title}</div>
            <p style={dek}>{e.dek}</p>
            <p style={meta}>
              {e.cited.length} source{e.cited.length === 1 ? "" : "s"} cited
            </p>
          </Link>
        ))}
      </div>
    </div>
  );
}
