// app/use-it/page.tsx -- "Use it" page: how to connect the CourtVision MCP
// server to Claude, plus its tool reference. Static export: reads the
// checked-in docs/MCP_QUICKSTART.md + docs/MCP_TOOLS.md straight off disk at
// build time (no client fetch, no markdown-parser dep -- rendered verbatim
// in a monospace block, same as the .prose-console code-fence styling).

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { Panel, PanelHead } from "@/components/ui/terminal";

export const metadata = {
  title: "Use it",
  description:
    "Connect the CourtVision MCP server to Claude Code or Claude Desktop in " +
    "under five minutes, plus the 9-tool reference (every answer is a typed, " +
    "fail-closed envelope).",
};

const TOOLS: Array<{ name: string; purpose: string }> = [
  { name: "ask", purpose: "Universal front door -- routes any NL sports question through the fail-closed answer engine (20+ categories)." },
  { name: "scouting_report", purpose: "Multi-axis descriptive scouting vector for one player -- axes never collapsed into one score." },
  { name: "comparables", purpose: "K nearest players by RMS-normalized Euclidean distance over shared percentiles." },
  { name: "matchup_preview", purpose: "Fan-out preview wrapping 8 sub-resolvers (win prob, profiles, style, injuries, schedule)." },
  { name: "win_probability", purpose: "Calibrated pre-game or in-game win probability, quoted verbatim off predict_matchup.py." },
  { name: "injury_report", purpose: "Newest-first injury-status rows for a team or player, with a 7-day staleness gate." },
  { name: "analytics_receipts", purpose: "The verified-analytics receipts ledger (attribution, claim survival, verification, contradictions, system map)." },
  { name: "run_burst", purpose: "Executes a maintenance burst (network + disk writes) -- the one non-read-only tool." },
  { name: "system_health", purpose: "Cheap read-only status: last burst report, freshness SLA, fleet on/off state." },
];

// ponytail: read the checked-in docs straight off disk at build time -- this
// is a static export, so there is no server to hit later. Render verbatim in
// a monospace block rather than pulling in a markdown-parser dependency.
function loadDoc(relPath: string): string | null {
  try {
    return readFileSync(join(process.cwd(), "..", relPath), "utf-8");
  } catch {
    return null;
  }
}

export default function UseItPage() {
  const quickstart = loadDoc("docs/MCP_QUICKSTART.md");

  return (
    <main className="mx-auto flex max-w-5xl flex-col gap-6 p-6">
      <header className="prose-console">
        <p className="microlabel">use it / mcp</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-foreground">
          Connect the CourtVision MCP server
        </h1>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
          A read-only oracle over stdio JSON-RPC: 9 tools, every answer a typed
          envelope (<code>status</code> / <code>source_artifact</code> /{" "}
          <code>as_of</code>). It never answers from model memory and never
          claims a dollar edge -- an honest <code>no_data</code> is a correct
          answer, not a failure.
        </p>
      </header>

      <Panel>
        <PanelHead title="tool reference (9 tools)" />
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-border text-left">
                <th className="microlabel px-3 py-1.5">tool</th>
                <th className="microlabel px-3 py-1.5">purpose</th>
              </tr>
            </thead>
            <tbody>
              {TOOLS.map((t) => (
                <tr key={t.name} className="border-b border-border hover:bg-surface-2">
                  <td className="px-3 py-1.5 font-data">{t.name}</td>
                  <td className="px-3 py-1.5 text-muted-foreground">{t.purpose}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="border-t border-border px-3 py-2 text-[11px] text-faint">
          Full parameter/envelope reference: docs/MCP_TOOLS.md in the repo.
        </div>
      </Panel>

      <Panel>
        <PanelHead title="quickstart" />
        <div className="prose-console p-4">
          {quickstart ? (
            <pre className="whitespace-pre-wrap">
              <code>{quickstart}</code>
            </pre>
          ) : (
            <p className="m-0 text-sm text-muted-foreground">
              docs/MCP_QUICKSTART.md unavailable in this build.
            </p>
          )}
        </div>
      </Panel>
    </main>
  );
}
