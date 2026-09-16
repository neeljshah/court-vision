"use client";

import { useEffect, useMemo, useState } from "react";
import { VerdictDot, type Verdict } from "@/components/analytics/VerdictDot";
import { claimFamilyId, claimFamilyLabel, type ClaimHistoryFamily, type ClaimHistoryLedger } from "@/lib/analytics/claimHistory";
import "./claim-history.css";

const PAGE_SIZE = 25;
const SPORT_LABELS: Record<string, string> = {
  basketball_nba: "NBA",
  mlb: "MLB",
  soccer: "Soccer",
  tennis: "Tennis",
};

function verdictOf(status: string): Verdict {
  if (status === "verified") return "confirmed";
  if (status === "not_testable") return "not_testable";
  if (status === "provisional") return "pending";
  return "null";
}

function statusLabel(status: string): string {
  return status.replaceAll("_", " ");
}

function formatEffect(effect: number | null): string {
  return effect === null ? "not recorded" : String(effect);
}

function FamilyHistory({ family }: { family: ClaimHistoryFamily }) {
  const label = claimFamilyLabel(family);
  return <div className="ch-history">
    <p className="ch-order-note">History remains in the published source order. Undated runs are not sorted as though they had a date.</p>
    <div className="ch-scroll" data-scroll-region>
      <table aria-label={`Rerun history for ${label}`}>
        <thead><tr><th>Verdict</th><th>Status</th><th>Run date</th><th>Corpus</th><th>n</th><th>Published effect</th></tr></thead>
        <tbody>{family.history.map((run, index) => <tr key={`${run.verdict}-${run.status}-${index}`}>
          <td><span className="ch-verdict"><VerdictDot verdict={verdictOf(run.status)} />{statusLabel(run.verdict)}</span></td>
          <td>{statusLabel(run.status)}</td>
          <td>{run.runTs ? run.runTs : "run date not recorded"}</td>
          <td className="ch-corpus">{run.corpus || "corpus not recorded"}</td>
          <td className="mono">{run.n === null ? "not recorded" : run.n.toLocaleString("en-US")}</td>
          <td className="mono">{formatEffect(run.effect)} <span className="ch-unit">unit not recorded</span></td>
        </tr>)}</tbody>
      </table>
    </div>
  </div>;
}

export function ClaimHistory({ ledger }: { ledger: ClaimHistoryLedger }) {
  const [query, setQuery] = useState("");
  const [sport, setSport] = useState("all");
  const [status, setStatus] = useState("all");
  const [changedOnly, setChangedOnly] = useState(false);
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const sports = useMemo(() => Array.from(new Set(ledger.families.map(family => family.sport))), [ledger.families]);
  const statuses = useMemo(() => Array.from(new Set(ledger.families.map(family => family.currentStatus))), [ledger.families]);
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return ledger.families.filter(family =>
      (sport === "all" || family.sport === sport) &&
      (status === "all" || family.currentStatus === status) &&
      (!changedOnly || family.flipped) &&
      (!needle || `${family.hypothesis} ${claimFamilyLabel(family)} ${family.sport}`.toLowerCase().includes(needle)),
    );
  }, [changedOnly, ledger.families, query, sport, status]);
  const visibleFamilies = filtered.slice(0, visibleCount);

  function resetWindow() {
    setVisibleCount(PAGE_SIZE);
  }

  useEffect(() => {
    const openHashFamily = () => {
      const target = window.location.hash.slice(1);
      const index = ledger.families.findIndex(family => claimFamilyId(family) === target);
      if (index < 0) return;
      setQuery("");
      setSport("all");
      setStatus("all");
      setChangedOnly(false);
      setVisibleCount(Math.max(PAGE_SIZE, index + 1));
      setExpanded(new Set([target]));
    };
    openHashFamily();
    window.addEventListener("hashchange", openHashFamily);
    return () => window.removeEventListener("hashchange", openHashFamily);
  }, [ledger.families]);

  return <section className="ch-ledger" aria-labelledby="claim-history-heading">
    <div className="ch-heading">
      <div>
        <div className="overline">Published rerun history</div>
        <h2 id="claim-history-heading">Claim family ledger</h2>
        <p>Each family keeps its recorded reruns. Published effects are displayed with no cross-family ranking because their units are not recorded in this artifact.</p>
      </div>
      <p className="ch-count" aria-live="polite">{filtered.length} of {ledger.families.length} families</p>
    </div>
    <div className="ch-controls">
      <label>Search families<input aria-label="Search families" value={query} onChange={event => { setQuery(event.target.value); resetWindow(); }} placeholder="Family id or title" /></label>
      <label>Sport<select aria-label="Sport filter" value={sport} onChange={event => { setSport(event.target.value); resetWindow(); }}><option value="all">All sports</option>{sports.map(item => <option key={item} value={item}>{SPORT_LABELS[item] || item}</option>)}</select></label>
      <label>Current status<select aria-label="Current status filter" value={status} onChange={event => { setStatus(event.target.value); resetWindow(); }}><option value="all">All statuses</option>{statuses.map(item => <option key={item} value={item}>{statusLabel(item)}</option>)}</select></label>
      <label className="ch-toggle"><input aria-label="Changed verdict only" type="checkbox" checked={changedOnly} onChange={event => { setChangedOnly(event.target.checked); resetWindow(); }} />Changed verdict only</label>
    </div>
    <div className="ch-list">
      {visibleFamilies.map(family => {
        const id = claimFamilyId(family);
        const isExpanded = expanded.has(id);
        return <article className="ch-family" id={id} key={id}>
          <button className="ch-family-button" type="button" aria-expanded={isExpanded} onClick={() => setExpanded(previous => {
            const next = new Set(previous);
            if (next.has(id)) next.delete(id); else next.add(id);
            return next;
          })}>
            <span className="ch-sport">{SPORT_LABELS[family.sport] || family.sport}</span>
            <span className="ch-title">{claimFamilyLabel(family)}</span>
            <span className="ch-status"><VerdictDot verdict={verdictOf(family.currentStatus)} />{statusLabel(family.currentStatus)}</span>
            <span className="ch-runs">{family.history.length} {family.history.length === 1 ? "run" : "runs"}</span>
          </button>
          {isExpanded ? <FamilyHistory family={family} /> : null}
        </article>;
      })}
    </div>
    {visibleCount < filtered.length ? <button className="ch-more" type="button" onClick={() => setVisibleCount(previous => previous + PAGE_SIZE)}>Show more families</button> : null}
  </section>;
}

export default ClaimHistory;
