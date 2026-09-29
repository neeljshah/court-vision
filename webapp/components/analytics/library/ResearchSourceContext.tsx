"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { base, sourceUrl } from "@/lib/analytics/dashboardTypes";
import { resolveResearchSourceDestination } from "@/lib/analytics/researchSourceDestinations";
import type { ResearchField, ResearchSource } from "@/lib/analytics/researchTypes";

type SourceDocument = Record<string, unknown>;
type SourceMetadata = { period: string | null; asOfDetails: [string, string][] };

function record(value: unknown): SourceDocument {
  return value && typeof value === "object" && !Array.isArray(value) ? value as SourceDocument : {};
}

function seasonLabel(value: string): string {
  return value.replace(/_(\d{2})$/, "-$1");
}

function seasonsFromRows(value: unknown): string | null {
  if (!Array.isArray(value)) return null;
  const seasons = [...new Set(value.map(item => record(item).season).filter((season): season is string => typeof season === "string" && season.length > 0))];
  return seasons.length ? seasons.map(seasonLabel).join(", ") : null;
}

export function observationPeriod(document: SourceDocument): string | null {
  const window = record(document.observation_window);
  if (typeof window.seasons === "string" && window.seasons) return window.seasons;
  if (typeof window.start === "string" && typeof window.end === "string") return `${window.start} to ${window.end}`;
  const seasons = record(document.seasons);
  const seasonKeys = Object.keys(seasons);
  if (seasonKeys.length) return seasonKeys.map(seasonLabel).join(", ");
  for (const key of ["results", "per_team_season_frequencies"]) {
    const period = seasonsFromRows(document[key]);
    if (period) return period;
  }
  const entries = Array.isArray(document.entries) ? document.entries : [];
  const covered = [...new Set(entries.map(entry => record(record(entry).key_numbers).seasons_covered).filter((value): value is number => typeof value === "number" && Number.isFinite(value)))];
  if (covered.length === 1) return `${covered[0]} seasons in the published atlas`;
  const played = [...new Set(entries.map(entry => record(record(entry).key_numbers).seasons_played).filter((value): value is number => typeof value === "number" && Number.isFinite(value)))].sort((left, right) => left - right);
  if (played.length === 1) return `${played[0]} seasons per published player`;
  if (played.length > 1) return `${played[0]}-${played.at(-1)} seasons per published player`;
  return null;
}

function sourceFields(source: ResearchSource, fields: ResearchField[]): string[] {
  const keys = source.fields || fields.filter(field => field.sourceId === source.id).map(field => field.key);
  return keys.map(key => fields.find(field => field.key === key)?.label || key);
}

export function sourceHref(id: string): string {
  return resolveResearchSourceDestination(id).href;
}

function rowWindow(source: ResearchSource, fields: ResearchField[]): string {
  const keys = source.fields || fields.filter(field => field.sourceId === source.id).map(field => field.key);
  const labels = keys.flatMap(key => {
    const windows = source.rowWindows?.[key] || [];
    if (!windows.length) return [];
    const label = fields.find(field => field.key === key)?.label || key;
    return [`${label}: ${[...new Set(windows)].join(", ")}`];
  });
  return labels.join("; ") || "not recorded";
}

export function ResearchSourceContext({ sources, fields }: { sources?: ResearchSource[]; fields: ResearchField[] }) {
  const [metadata, setMetadata] = useState<Record<string, SourceMetadata>>({});
  useEffect(() => {
    if (!sources?.length || typeof fetch === "undefined") return;
    let active = true;
    Promise.all(sources.map(async source => {
      try {
        const response = await fetch(sourceUrl(source.id));
        const document = response.ok ? record(await response.json()) : {};
        const asOfDetails = Object.entries(record(document.as_of)).filter((entry): entry is [string, string] =>
          entry[0].trim().length > 0 && typeof entry[1] === "string" && entry[1].trim().length > 0);
        return [source.id, { period: observationPeriod(document), asOfDetails }] as const;
      } catch { return [source.id, { period: null, asOfDetails: [] }] as const; }
    })).then(items => { if (active) setMetadata(Object.fromEntries(items)); });
    return () => { active = false; };
  }, [sources]);
  if (!sources?.length) return null;
  return <section aria-label="Source context" style={{ borderTop: "1px solid var(--rule)", borderBottom: "1px solid var(--rule)", padding: "14px 0", marginBottom: 18 }}>
    <p className="cv-eyebrow">Source context</p>
    <p className="cv-muted" style={{ margin: "4px 0 10px" }}>Snapshot dates, source coverage, and selected row windows are reported separately because contributing modules do not share one window.</p>
    <ul style={{ listStyle: "none", display: "grid", gap: 10 }}>
      {sources.map(source => {
        const destination = resolveResearchSourceDestination(source.id);
        const link = destination.kind === "json"
          ? <a href={`${base}${destination.href}`} style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>{source.id}</a>
          : <Link href={destination.href} style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>{source.id}</Link>;
        return <li key={source.id} style={{ display: "grid", gap: 2 }}>
        {link}
        <span className="cv-muted" style={{ fontSize: 13 }}>Snapshot date: {source.asOf || "not recorded"}</span>
        <span className="cv-muted" style={{ fontSize: 13 }}>Source coverage: {metadata[source.id]?.period || "not recorded"}</span>
        {metadata[source.id]?.asOfDetails.map(([key, value]) => <span key={key} className="cv-muted" style={{ fontSize: 13 }}>
          Source as of, {key.replace(/^estimator_([a-z])$/, (_, letter: string) => `Estimator ${letter.toUpperCase()}`)}: {value}
        </span>)}
        <span className="cv-muted" style={{ fontSize: 13 }}>Row window: {rowWindow(source, fields)}</span>
        <span className="cv-muted" style={{ fontSize: 13 }}>Feeds: {sourceFields(source, fields).join(", ") || "no measurements recorded"}</span>
      </li>;
      })}
    </ul>
  </section>;
}
