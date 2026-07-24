// ClaimPage.tsx -- one evidence claim, rendered from parsed markdown + the staged
// artifact index (props built by lib/evidence.server buildClaimPage). Composes:
// bucket + title + lede, the strongest-receipt chip, the claim / how-it-works /
// why-matters prose, the Receipts table (artifact chips resolved at build time),
// the figures, and the reproduce block. Server component; the only client islands
// are the ReceiptChip and ReproduceBlock it mounts.
//
// Honesty: status VALIDATION_PENDING (md absent on this clone) renders the amber
// pending banner and the index teaser instead of fabricated prose. Every cited
// JSON gets a real receipt chip (as_of/verdict/verified) or an honest pending chip
// when it was not staged. No dollar-edge language is introduced here.

import * as React from "react";
import { notFound } from "next/navigation";
import { Panel, PanelHead } from "@/components/ui/terminal";
import { HonestBanner } from "@/components/showcase/HonestBanner";
import { ReproduceBlock } from "@/components/showcase/ReproduceBlock";
import { ReceiptChip } from "@/components/showcase/ReceiptChip";
import {
  loadArtifact,
  receiptChip,
  type ReceiptChipProps,
} from "@/lib/showcase.server";
import type { ClaimPageProps } from "@/lib/evidence.server";
import { ReceiptTable, type ReceiptTableRow } from "./ReceiptTable";
import { FigureWithSource } from "./FigureWithSource";

// Resolve a receipt chip from an artifact cell: find the first .json path token,
// load that staged artifact, and read its honesty header. Missing/unstaged -> an
// honest validation_pending chip. Non-JSON citations (a .py file, "git log") get
// no chip -- they are source, not a measured receipt.
function chipForArtifact(cell: string | null): ReceiptChipProps | undefined {
  if (!cell) return undefined;
  const m = cell.match(/[\w./\\-]+\.json/);
  if (!m) return undefined;
  const base = (m[0].split(/[/\\]/).pop() ?? "").replace(/\.json$/, "");
  return receiptChip(loadArtifact(base));
}

const stripTicks = (s: string) => s.replace(/`/g, "").trim();

// Public origin blob base -- for the honest "see evidence page source" fallback
// chip when a claim resolves no staged JSON receipt. (Matches RetractionCard.)
const REPO_BLOB = "https://github.com/neeljshah/court-vision/blob/main/";

// ponytail: a ~30-line markdown-ish renderer, NOT a full parser -- handles the
// only inline forms the evidence md uses (bold / code / link) plus paragraphs and
// dash lists. No new dep (react-markdown is not installed and none may be added).
// Ceiling: nested lists, tables, headings inside a section are not handled; add a
// real renderer only if the evidence prose grows those.
export function inline(text: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  // bold, then code, then link, then single-asterisk emphasis (bold matched
  // first so ** never falls through to *). em is [^*\n] so it never spans **.
  const re =
    /\*\*(.+?)\*\*|`([^`]+?)`|\[([^\]]+?)\]\(([^)]+?)\)|\*([^*\n]+?)\*/g;
  let last = 0;
  let k = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(text.slice(last, m.index));
    if (m[1] != null) out.push(<strong key={k++}>{m[1]}</strong>);
    else if (m[2] != null) out.push(<code key={k++}>{m[2]}</code>);
    else if (m[3] != null)
      out.push(
        <a key={k++} href={m[4]}>
          {m[3]}
        </a>
      );
    else out.push(<em key={k++}>{m[5]}</em>);
    last = re.lastIndex;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

// A markdown horizontal rule: a block of only --- / *** / ___ (>=3).
const isHr = (b: string) => /^([-*_])\1{2,}$/.test(b.trim());

function Prose({ md }: { md: string }) {
  const blocks = md
    .split(/\n{2,}/)
    .map((b) => b.trim())
    .filter(Boolean);
  return (
    <div className="prose-console text-sm text-muted-foreground">
      {blocks.map((b, i) => {
        if (isHr(b)) return <hr key={i} />;
        const lines = b.split("\n");
        if (lines.every((l) => /^[-*] /.test(l.trim()))) {
          return (
            <ul key={i}>
              {lines.map((l, j) => (
                <li key={j}>{inline(l.trim().replace(/^[-*] /, ""))}</li>
              ))}
            </ul>
          );
        }
        return <p key={i}>{inline(b.replace(/\n/g, " "))}</p>;
      })}
    </div>
  );
}

function Section({ title, md }: { title: string; md: string }) {
  if (!md.trim()) return null;
  return (
    <Panel>
      <PanelHead title={title} />
      <div className="p-4">
        <Prose md={md} />
      </div>
    </Panel>
  );
}

export function ClaimPage(props: ClaimPageProps) {
  if (!props.slug) notFound();
  const pending = props.status === "VALIDATION_PENDING";

  const receiptRows: ReceiptTableRow[] = props.receipts.map((r) => ({
    label: r.guarantee,
    value: r.receipt || undefined,
    artifact: stripTicks(r.artifact),
    chip: chipForArtifact(r.artifact),
  }));
  // Fresh-clone / 2-column tables yield no parsed receipts: fall back to the
  // index's cited artifacts so every claim still shows where to look.
  const citedRows: ReceiptTableRow[] =
    receiptRows.length === 0
      ? props.citedArtifacts.map((a) => ({
          label: "",
          artifact: stripTicks(a),
          chip: chipForArtifact(a),
        }))
      : [];

  const heroChip = chipForArtifact(props.strongestReceipt.source);

  // Honest fallback: a claim whose md carries no receipt table, whose index row
  // cites no artifacts, and whose strongest receipt has no JSON source resolves
  // to zero chips. Rather than a blank, point to the evidence doc on the public
  // origin -- never a fabricated number.
  const noReceipts =
    receiptRows.length === 0 && citedRows.length === 0 && !heroChip;
  const fallbackRows: ReceiptTableRow[] = noReceipts
    ? [
        {
          label: "",
          artifact: `docs/evidence/${props.slug}.md`,
          chip: {
            sourceArtifact: `docs/evidence/${props.slug}.md`,
            asOf: null,
            verified: "validation_pending",
            href: `${REPO_BLOB}docs/evidence/${props.slug}.md`,
          },
        },
      ]
    : [];
  const tableRows =
    receiptRows.length > 0
      ? receiptRows
      : citedRows.length > 0
        ? citedRows
        : fallbackRows;

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 p-6">
      <header className="prose-console">
        <p className="microlabel">evidence / {props.bucket || "claim"}</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">
          {props.title}
        </h1>
        {props.lede && (
          <p className="text-sm leading-relaxed text-muted-foreground">
            {inline(props.lede)}
          </p>
        )}
      </header>

      {pending && <HonestBanner kind="validation_pending" />}

      {props.strongestReceipt.label && (
        <Panel>
          <PanelHead title="strongest single receipt" />
          <div className="flex items-baseline gap-1 p-4 text-sm leading-relaxed text-foreground">
            <span>{inline(props.strongestReceipt.label)}</span>
            {heroChip && <ReceiptChip {...heroChip} />}
          </div>
        </Panel>
      )}

      {/* On a fresh clone props.claim is the index teaser, never fabricated prose. */}
      <Section title="the claim" md={props.claim} />

      <Section title="how it works" md={props.howItWorks} />

      {tableRows.length > 0 && (
        <Panel>
          <PanelHead
            title={
              receiptRows.length > 0
                ? "receipts"
                : citedRows.length > 0
                  ? "cited artifacts"
                  : "receipt: see evidence page source"
            }
          />
          <ReceiptTable rows={tableRows} />
        </Panel>
      )}

      {props.figures.map((f, i) => (
        <FigureWithSource
          key={i}
          src={f.src}
          alt={f.alt}
          caption={f.caption || undefined}
        />
      ))}

      <Section title="why this matters" md={props.whyMatters} />

      {props.reproduce && (
        <Panel>
          <PanelHead title="reproduce" />
          <div className="p-4">
            <ReproduceBlock command={props.reproduce} />
          </div>
        </Panel>
      )}

      <HonestBanner kind="no_edge" />
    </main>
  );
}
