// app/(terminal)/evidence/retractions/page.tsx -- THE retraction record (one page).
// Renders docs/JOB_EVIDENCE_PACKET.md section 4 verbatim (parsed at build time by
// packetTable.ts). The six retracted figures appear on this site only here, inside
// table rows marked Retracted, each beside the packet's replacement wording ("Say
// instead") and a date. The old /evidence/retraction-story/ and
// /analytics/findings/retraction/ routes are redirect stubs to this page.
import type { ReactNode } from "react";
import { githubDoc } from "@/components/shell/nav";
import { loadPacketTable, type PacketRow } from "./packetTable";

export const metadata = {
  title: "Retraction record",
  description:
    "Every figure this project withdrew or never verified, copied from section 4 of the evidence packet, each with the wording that replaces it.",
};

// The packet's own withdrawal record for the four retracted rows was published 2026-07-23.
const RETRACTION_RECORD_DATE = "2026-07-23";
const PACKET_URL = githubDoc("docs/JOB_EVIDENCE_PACKET.md");

/** Minimal inline markdown: **bold**, `code`, [text](url) (relative links go to GitHub). */
function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`")) return <code key={i}>{part.slice(1, -1)}</code>;
    const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(part);
    if (link) {
      const href = /^https?:/.test(link[2]) ? link[2] : githubDoc(link[2].replace(/^(\.\.\/)+/, ""));
      return <a key={i} href={href} className="underline">{link[1]}</a>;
    }
    return part;
  });
}

function rowDate(r: PacketRow): string {
  if (r.date) return r.date;
  return r.status === "Retracted" ? RETRACTION_RECORD_DATE : "not dated in the packet row";
}

export default function RetractionsPage() {
  const rows = loadPacketTable();
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6 px-4 py-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">Retraction record</h1>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          Every figure this project withdrew or could not verify, copied verbatim from section 4 of
          the evidence packet. Each row names the figure, why it fails, the wording that replaces it
          and a date. The largest withdrawal is the former headline return figure: it was a grading
          artifact, and the honest replacement is that the pregame model matches or trails the
          closing price. A retracted number appears on this site only here. Source:{" "}
          <a href={PACKET_URL} className="underline">docs/JOB_EVIDENCE_PACKET.md</a>, section 4.
        </p>
      </header>

      {rows ? (
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="w-full min-w-[720px] border-collapse text-left text-sm">
            <caption className="sr-only">Retired and retracted figures with their replacements</caption>
            <thead className="bg-secondary text-foreground">
              <tr>
                <th scope="col" className="p-3">Status and date</th>
                <th scope="col" className="p-3">Do not claim</th>
                <th scope="col" className="p-3">Why it fails</th>
                <th scope="col" className="p-3">Say instead (replacement)</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} data-status={r.status} className="border-t border-border align-top">
                  <td className="whitespace-nowrap p-3 font-medium text-foreground">
                    {r.status}
                    <br />
                    <span className="font-normal text-muted-foreground">{rowDate(r)}</span>
                  </td>
                  <td className="p-3 text-foreground">{inline(r.claim)}</td>
                  <td className="p-3 text-muted-foreground">{inline(r.why)}</td>
                  <td className="p-3 text-foreground">{inline(r.sayInstead)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          The evidence packet is not in this build. Read the table in the{" "}
          <a href={PACKET_URL} className="underline">public repository copy</a>.
        </p>
      )}

      <p className="text-sm text-muted-foreground">
        Proof files named in the table are in the public repository when they sit under docs/,
        kernel/ or scripts/platformkit/eval_gate/; any other path named there is in the private
        repository.
      </p>
    </div>
  );
}
