// DeskShell.tsx -- shared frame for the /desk pages: the paper-only header,
// sub-navigation, and the explicit "not available" chip. Server component.

import Link from "next/link";
import type { ReactNode } from "react";
import type { Desk, Refusal } from "@/lib/desk.server";
import { Panel } from "@/components/ui/terminal";
import { ghBlob } from "./deskExtras.server";
import { ReceiptChip } from "@/components/showcase/ReceiptChip";

export const PAPER_HEADER =
  "PAPER DESK -- PAPER ONLY, simulated maker quotes on the recorded Kalshi tape; not a verdict";

const TABS = [
  { href: "/desk", label: "Record" },
  { href: "/desk/ingame", label: "How in-game works" },
  { href: "/desk/execution", label: "Execution" },
  { href: "/desk/model-cards", label: "Models" },
  { href: "/desk/health", label: "Health" },
];

/** Explicit refusal chip: a missing section is shown with its reason, never blank. */
export function NotAvailable({ refusals }: { refusals: Refusal[] }) {
  const list = refusals.length ? refusals : [{ section: "?", reason: "no data in the export" }];
  return (
    <div className="flex flex-col gap-1 px-3 py-2">
      {list.map((r, i) => (
        <span key={i} className="inline-block w-fit border border-warning/60 px-2 py-0.5 font-data text-xs text-stale">
          not available: {r.section}: {r.reason}
        </span>
      ))}
    </div>
  );
}

/** Small table helper used by every desk page. */
export function T({ head, rows }: { head: string[]; rows: ReactNode[][] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full font-data text-xs">
        <thead>
          <tr className="whitespace-nowrap border-b border-border text-left text-faint">
            {head.map((h, i) => (
              <th key={`${h}-${i}`} scope="col" className="px-3 py-1 font-normal">
                {/* A blank column header still needs a screen-reader name (axe empty-table-header). */}
                {h || <span className="sr-only">note</span>}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-border/50">
              {r.map((c, j) => <td key={j} className="px-3 py-1 align-top">{c}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Desk panel: 12 px heading, as-of from the receipt, receipt chip and a GitHub link to the source. */
export function Section({ title, asOf, source, verdict, children, id }: {
  title: string; asOf?: string | null; source?: string | null; verdict?: string | null;
  children: ReactNode; id?: string;
}) {
  return (
    <Panel>
      <div id={id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-border px-3 py-2">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{title}</h2>
        <div className="ml-auto flex flex-wrap items-baseline gap-3 font-data text-xs text-faint">
          {source ? <ReceiptChip sourceArtifact={source} asOf={asOf ?? null} verified="descriptive_only"
            verdict={verdict ?? null} href={source.includes("/") ? ghBlob(source) : null} /> : null}
          <span data-testid="section-asof">{asOf ? `as of ${asOf.slice(0, 10)}` : "as of: not stated in the receipt"}</span>
        </div>
      </div>
      {children}
    </Panel>
  );
}

export function DeskShell({ desk, title, active, children }: {
  desk: Desk | null; title: string; active: string; children: ReactNode;
}) {
  return (
    // A <div>, not a second <main>: AppShell already renders the page's main landmark
    // (axe landmark-no-duplicate-main / landmark-main-is-top-level).
    <div className="mx-auto flex max-w-6xl flex-col gap-5 p-4 sm:p-6">
      <header>
        <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{(desk?.header ?? PAPER_HEADER).replace(/paper only/i, "PAPER ONLY")}</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">{title}</h1>
        <p className="mt-1 font-data text-xs text-faint">
          {desk ? `export ${desk.date}, generated ${desk.generated_at_utc}; ${desk.refusals.length} refusal(s)` :
            "desk export not staged"}
        </p>
        <p className="mt-1 max-w-3xl text-xs text-muted-foreground" data-testid="desk-dates">
          Three dates frame this record. Capture history starts 2026-09-24, the first night in the fill-realism
          table. The first ledger night with paper fills is 2026-10-03. The prospective forward paper series, with
          schedules written before the games, runs from 2026-10-06 (evidence packet section 5). No calibration
          verdict yet, for or against the model.
        </p>
        <nav aria-label="Desk pages" className="mt-3 flex flex-wrap gap-2">
          {TABS.map((t) => (
            <Link key={t.href} href={t.href}
              className={"inline-flex min-h-6 items-center border px-2 py-0.5 text-xs " +
                (t.href === active ? "border-foreground text-foreground" : "border-border text-muted-foreground")}>
              {t.label}
            </Link>
          ))}
        </nav>
      </header>
      {children}
    </div>
  );
}
