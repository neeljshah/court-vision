// Public Scout retrieval with a separately documented local MCP integration.
import type { Metadata } from "next";
import Link from "next/link";
import { AskBox, type AskTour } from "@/components/analytics/AskBox";
import type { AskEntry } from "@/lib/analytics/askSearch";
import { loadScoutCorpus } from "@/lib/analytics/scoutCorpus.server";
import "../workspace.css";
import styles from "./ask.module.css";

export const metadata: Metadata = {
  title: "Ask Scout",
  description: "Search CourtVision's published player profiles, metrics, and research answers. Inspect the source and snapshot date behind every result.",
};
const BUCKETS = [
  { key: "calibration-market", label: "Calibration & the market" },
  { key: "players-teams", label: "Players & teams" },
  { key: "system-honesty", label: "How the system works" },
  { key: "no_data_honest", label: "Data availability" },
];
function buildTours(entries: AskEntry[]): AskTour[] {
  return BUCKETS.map(b => ({ label: b.label, questions: entries.filter(e => e.bucket === b.key).slice(0, 2).map(e => e.q) })).filter(t => t.questions.length > 0);
}
const MCP_CONFIG = `{
  "mcpServers": {
    "courtvision": {
      "command": "python",
      "args": ["-m", "scripts.platformkit.mcp_server.server"],
      "cwd": "<REPO_ROOT>",
      "env": { "PYTHONPATH": "." }
    }
  }
}`;
const DOC = "https://github.com/neeljshah/court-vision/blob/master/docs/MCP_QUICKSTART.md";
const SPORT_TAGS = new Set(["mlb", "nba", "soccer", "tennis"]);

function countSports(entries: AskEntry[]): number {
  return new Set(entries.flatMap((entry) => entry.tags).map((tag) => tag.toLowerCase().trim()).filter((tag) => SPORT_TAGS.has(tag))).size;
}

export default function AskPage() {
  const entries = loadScoutCorpus();
  const sportCount = countSports(entries);
  return <div className="cv-workspace"><div className={`cv-workspace-inner ${styles.page}`}>
    <header className="cv-masthead"><div>
      <p className="cv-eyebrow"><span className="cv-square" /> Research assistant / Published evidence</p>
      <h1>Start with a question.<br />Follow the evidence.</h1>
      <p>Find a player profile, understand a metric, or inspect a research result. Every answer keeps its source and snapshot date.</p>
    </div></header>
    <div className={styles.coverage} aria-label="Search coverage">
      <span><b>{entries.length.toLocaleString("en-US")}</b> searchable entries</span>
      <span><b>{sportCount}</b> sports</span><span>Historical snapshots</span><span>Search runs in your browser</span>
    </div>
    <AskBox entries={entries} tours={buildTours(entries)} />
    <section className={styles.next} aria-labelledby="scout-next">
      <h2 id="scout-next">Turn an answer into an investigation.</h2>
      <div className={styles.tierGrid}>
        <Link href="/analytics/compare/"><span>01 / Compare</span><h3>Put two profiles side by side</h3><p>Compare reported metrics and available percentiles within the same population.</p></Link>
        <Link href="/analytics/lab/"><span>02 / Measure</span><h3>Explore a measurement</h3><p>Change metrics, inspect individual observations, and download the rows behind a chart.</p></Link>
        <Link href="/analytics/evidence/"><span>03 / Inspect</span><h3>Open the evidence gallery</h3><p>Explore published visualizations alongside their methods and source artifacts.</p></Link>
      </div>
    </section>
    <details className={styles.connect}>
      <summary>Developer integration: connect a local CourtVision MCP server</summary>
      <div className={styles.connectBody}>
        <div><p className="cv-eyebrow">Documented integration / Requires setup</p>
          <h2>Use CourtVision tools from Claude.</h2>
          <p>The repository documents a set of typed MCP tools for scouting, comparisons, matchup previews, and source receipts. Tool availability depends on the artifacts in your local installation. Missing data returns an explicit status.</p>
          <ol><li>Clone the repository and follow the Python setup in the quickstart.</li><li>Replace <code>&lt;REPO_ROOT&gt;</code> with your clone's absolute path in the Desktop configuration.</li><li>Restart Claude and verify the tool connection.</li></ol>
          <p>This public page searches committed snapshots. It does not connect to your Claude session or run the MCP backend. A hosted connector requires a separately available endpoint.</p>
          <a href={DOC} target="_blank" rel="noopener noreferrer">Read the full MCP quickstart on GitHub</a>
        </div><pre>{MCP_CONFIG}</pre>
      </div>
    </details>
  </div></div>;
}
