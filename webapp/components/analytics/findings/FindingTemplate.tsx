// FindingTemplate.tsx -- T4 finding page (DESIGN_PRINCIPLES section 3). One template for every
// finding so a lint can check block order by data-block: claim, status, test, replication,
// inspector, evidence (the page's own exhibit), limitations, verdict-history, then the common
// footer: reproduce, source, changelog, quoted-on. Server component (reads lib/quotedOn.server).
import type { CSSProperties, ReactNode } from "react";
import Link from "next/link";
import { AsOfBadge, ReceiptChip, VerdictLabel } from "@/components/evidence";
import { QuotedOnList } from "@/components/analytics/QuotedOnList";
import { quotedOn } from "@/lib/quotedOn.server";
import { isPacketVerdict, type PacketVerdict } from "@/lib/packetVerdicts";
import { FINDING_SPECS, type FindingSpec } from "./findingSpecs";

/* eslint-disable @typescript-eslint/no-explicit-any */
type R = Record<string, any>;

export const FINDING_BLOCKS = [
  "claim", "status", "test", "replication", "inspector", "evidence",
  "limitations", "verdict-history", "reproduce", "source", "changelog", "quoted-on",
] as const;

const REPO = "https://github.com/neeljshah/court-vision";
const h1: CSSProperties = { fontFamily: "var(--font-display)", fontWeight: 500, fontSize: "clamp(2rem,4vw,2.75rem)", lineHeight: 1.08, letterSpacing: "-.015em", color: "var(--ink)", marginTop: 8 };
const claimS: CSSProperties = { fontSize: 18, lineHeight: 1.6, color: "var(--ink)", maxWidth: 760, marginTop: 16, fontWeight: 600 };
const blockS: CSSProperties = { marginTop: 24, maxWidth: 760, fontSize: 15, lineHeight: 1.6, color: "var(--ink-2)" };
const headS: CSSProperties = { fontSize: 13, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase", color: "var(--ink-3)", margin: "0 0 6px" };
const statusS: CSSProperties = { ...blockS, marginTop: 16, display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" };

const val = (x: string | ((a: R) => string), a: R) => (typeof x === "function" ? x(a) : x);

export function packetVerdicts(spec: FindingSpec, a: R): PacketVerdict[] {
  return [...new Set((spec.verdicts?.(a) ?? []).filter(isPacketVerdict))];
}

export function findingAsOf(a: R): string | null {
  const d = a.as_of ?? a.measured_on ?? a.generated_at ?? null;
  return typeof d === "string" && d ? d.slice(0, 10) : null;
}

/** Append-only verdict history from the artifact's own lineage fields; else one entry, the current verdict. */
export function verdictHistory(spec: FindingSpec, a: R): { date: string; text: string }[] {
  const date = findingAsOf(a) ?? "date not published";
  const out: { date: string; text: string }[] = [];
  const lineage: [string, string][] = [["supersedes", "supersedes"], ["superseded_by", "superseded by"], ["retracted", "retracted"], ["resolved_by", "resolved by"]];
  for (const [k, word] of lineage) {
    const v = a[k];
    if (typeof v === "string" || typeof v === "boolean") out.push({ date, text: typeof v === "boolean" ? word : `${word} ${v}` });
  }
  const vs = packetVerdicts(spec, a);
  out.push({ date, text: `current: ${vs.length ? vs.join(", ") : "no packet verdict (descriptive exhibit)"}` });
  return out;
}

function Block({ id, title, children }: { id: (typeof FINDING_BLOCKS)[number]; title: string; children: ReactNode }) {
  return (
    <section data-block={id} aria-label={title} style={blockS}>
      <h2 style={headS}>{title}</h2>
      {children}
    </section>
  );
}

export function FindingTemplate({ slug, artifact, children }: { slug: string; artifact?: R | null; children: ReactNode }) {
  const spec = FINDING_SPECS[slug];
  if (!spec) throw new Error(`FindingTemplate: no spec for "${slug}"`);
  const a: R = artifact ?? {};
  const source = spec.source ?? `scripts/platformkit/analytics_showcase/out/${spec.artifactId}.json`;
  const reproduce = spec.reproduce ?? `python scripts/platformkit/analytics_showcase/${spec.artifactId}.py`;
  const asOf = findingAsOf(a);
  const verdicts = packetVerdicts(spec, a);
  const pagePath = `webapp/app/(analytics)/analytics/findings/${slug}/page.tsx`;
  return (
    <div className="wrap" style={{ paddingTop: 48, paddingBottom: 64 }} data-template="T4">
      <p className="overline">Findings</p>
      <h1 style={h1}>{spec.title}</h1>
      <p data-block="claim" style={claimS}>{spec.claim}</p>
      <div data-block="status" aria-label="Status" style={statusS}>
        {verdicts.length ? verdicts.map((v) => <VerdictLabel key={v} verdict={v} />) : <span data-verdict="none">no packet verdict (descriptive exhibit)</span>}
        <span className="mono">n = {spec.n(a)}</span>
        <span className="mono">{spec.interval ?? "no interval"}</span>
        <AsOfBadge asOf={asOf} kind={a.as_of || a.measured_on ? "source" : "snapshot"} />
        <ReceiptChip source={source} asOf={asOf} kind={a.as_of || a.measured_on ? "source" : "snapshot"} quotedOn={quotedOn(source)} />
      </div>
      <Block id="test" title="The test that produced it">
        <ul style={{ margin: 0, paddingLeft: 20 }}>
          <li>Gate: {spec.test.gate}</li>
          <li>Corpora: {val(spec.test.corpora, a)}</li>
          <li>Folds: {val(spec.test.folds, a)}</li>
        </ul>
      </Block>
      <Block id="replication" title="Replication"><p style={{ margin: 0 }}>{val(spec.replication, a)}</p></Block>
      <Block id="inspector" title="Inspector">
        <p style={{ margin: 0 }}>{spec.inspector ? <Link href={spec.inspector.href}>{spec.inspector.label}</Link> : "No inspector page for this finding."}</p>
      </Block>
      <div data-block="evidence">{children}</div>
      <Block id="limitations" title="Limitations">
        <ul style={{ margin: 0, paddingLeft: 20 }}>{spec.limitations.map((l) => <li key={l}>{l}</li>)}</ul>
      </Block>
      <Block id="verdict-history" title="Verdict history">
        <ol style={{ margin: 0, paddingLeft: 20 }}>
          {verdictHistory(spec, a).map((e) => <li key={e.date + e.text}><time className="mono">{e.date}</time>: {e.text}</li>)}
        </ol>
      </Block>
      <footer>
        <Block id="reproduce" title="Reproduce"><pre className="mono" style={{ margin: 0, whiteSpace: "pre-wrap" }}>{reproduce}</pre></Block>
        <Block id="source" title="Source path">
          <p className="mono" style={{ margin: 0 }}>{source}</p>
          <p className="mono" style={{ margin: 0 }}>{reproduce.replace(/^python /, "")}</p>
        </Block>
        <Block id="changelog" title="Change log">
          <ul style={{ margin: 0, paddingLeft: 20 }}>
            <li><time className="mono">{asOf ?? "date not published"}</time>: source artifact dated</li>
            <li><a href={`${REPO}/commits/master/${encodeURI(pagePath)}`}>page history on GitHub</a></li>
          </ul>
        </Block>
        <Block id="quoted-on" title="Quoted on"><QuotedOnList artifact={source} /></Block>
      </footer>
    </div>
  );
}

export default FindingTemplate;
