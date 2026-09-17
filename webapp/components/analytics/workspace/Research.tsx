"use client";
import { useMemo, useState } from "react";
import { Search } from "lucide-react";
import { dateLabel, humanize, type Mechanism, type Sport } from "@/lib/analytics/dashboardTypes";
import { Empty, Pagination, Panel } from "./Primitives";

const searchText = (value: string) => value.toLowerCase().replace(/[_\s]+/g, " ").trim();

export function Research({ rows, sport }: { rows: Mechanism[]; sport: Sport }) {
  const [query, setQuery] = useState(""); const [bucket, setBucket] = useState("all"); const [page, setPage] = useState(0);
  const filtered = useMemo(() => rows.filter(r => (sport === "all" || r.sport === sport) && (bucket === "all" || r.bucket === bucket) && searchText(`${r.mechanism} ${r.verdict} ${r.corpus} ${r.evidence}`).includes(searchText(query))), [rows, sport, bucket, query]);
  const safePage = Math.min(page, Math.max(0, Math.ceil(filtered.length / 12) - 1));
  return <Panel title="The research ledger" eyebrow="Inspect the evidence" source="mechanism_ledger_export">
    <p className="cv-muted">Every published research record, including null results and work that could not be tested. Expand a record for its corpus and exact evidence.</p>
    <div className="cv-filter-row"><label className="cv-search"><Search size={17} /><input aria-label="Search research" placeholder="Search rest, momentum, surface..." value={query} onChange={e => { setQuery(e.target.value); setPage(0); }} /></label><select aria-label="Research verdict" value={bucket} onChange={e => { setBucket(e.target.value); setPage(0); }}><option value="all">All verdict groups</option><option value="confirmed">Confirmed group</option><option value="null">Null / other group</option><option value="not_testable">Not testable</option></select></div>
    <p className="cv-result-count" role="status">{filtered.length} matching records</p>
    <div className="cv-ledger">{filtered.slice(safePage * 12, safePage * 12 + 12).map((r, i) => <details key={`${r.sport}-${r.mechanism}-${safePage}-${i}`}><summary><i className={`cv-dot cv-${r.bucket}`} /><div><strong>{humanize(r.mechanism)}</strong><span>{r.sport.toUpperCase()} / {dateLabel(r.as_of)}</span></div><span className={`cv-badge cv-verdict-${r.bucket}`}>{r.verdict.replace(/_/g, " ")}</span></summary><div className="cv-record"><p>{r.evidence || "Evidence text not recorded."}</p><dl><div><dt>Corpus</dt><dd>{r.corpus || "Unrecorded"}</dd></div><div><dt>Recorded effect</dt><dd>{r.effect === null ? "Not recorded" : r.effect}</dd></div><div><dt>Recorded p-value</dt><dd>{r.p === null ? "Not recorded" : r.p.toPrecision(4)}</dd></div></dl><p className="cv-footnote">Effect units and test context are specific to each record. Repeated names can represent different runs; the ledger count is not a count of unique mechanisms.</p></div></details>)}</div>
    {!filtered.length && <Empty>No records match these filters. Try a shorter search or another verdict group.</Empty>}
    <Pagination page={safePage} total={filtered.length} onChange={setPage} />
    <p className="cv-footnote">Source grouping places partial, provisional and failed-replication results in the null/other group. The original verdict is preserved on every record. Local confirmation does not establish causality.</p>
  </Panel>;
}
