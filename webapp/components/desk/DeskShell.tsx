// DeskShell.tsx -- shared frame for the /desk pages: the paper-only header,
// sub-navigation, and the explicit "not available" chip. Server component.

import Link from "next/link";
import type { ReactNode } from "react";
import type { Desk, Refusal } from "@/lib/desk.server";
import { Panel, PanelHead } from "@/components/ui/terminal";
import { ReceiptChip } from "@/components/showcase/ReceiptChip";

export const PAPER_HEADER =
  "PAPER DESK -- paper only, simulated maker quotes on the recorded Kalshi tape; not a verdict";

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
        <span key={i} className="inline-block w-fit border border-stale/60 px-2 py-0.5 font-data text-[11px] text-stale">
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
      <table className="w-full font-data text-[12px]">
        <thead>
          <tr className="border-b border-border text-left text-faint">
            {head.map((h) => <th key={h} className="px-3 py-1 font-normal">{h}</th>)}
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

export function Section({ title, asOf, source, children }: {
  title: string; asOf?: string | null; source?: string | null; children: ReactNode;
}) {
  return (
    <Panel>
      <PanelHead
        title={title}
        asOf={asOf ?? null}
        right={source ? <ReceiptChip sourceArtifact={source} asOf={asOf ?? null} verified="descriptive_only" /> : null}
      />
      {children}
    </Panel>
  );
}

export function DeskShell({ desk, title, active, children }: {
  desk: Desk | null; title: string; active: string; children: ReactNode;
}) {
  return (
    <main className="mx-auto flex max-w-6xl flex-col gap-5 p-4 sm:p-6">
      <header>
        <p className="microlabel">{desk?.header ?? PAPER_HEADER}</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">{title}</h1>
        <p className="mt-1 font-data text-[11px] text-faint">
          {desk ? `export ${desk.date}, generated ${desk.generated_at_utc}; ${desk.refusals.length} refusal(s)` :
            "desk export not staged"}
        </p>
        <nav className="mt-3 flex flex-wrap gap-2">
          {TABS.map((t) => (
            <Link key={t.href} href={t.href}
              className={"border px-2 py-0.5 text-[12px] " +
                (t.href === active ? "border-foreground text-foreground" : "border-border text-muted-foreground")}>
              {t.label}
            </Link>
          ))}
        </nav>
      </header>
      {children}
    </main>
  );
}
