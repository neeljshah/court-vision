"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  COMPARISON_PACKS, formatMetric, formatPercentile, metricLabel, metricUnit,
  normalizeComparisonPack, type ComparisonEntity, type ComparisonPack, type ComparisonPackKey,
  type RawComparables, type RawManifest, type RawPercentiles,
} from "@/lib/analytics/comparisonData";

const DATA_ROOT = "/data/showcase/";

function publicPath(path: string): string {
  return `${process.env.NEXT_PUBLIC_BASE_PATH || ""}${DATA_ROOT}${path}`;
}

function packInfo(key: ComparisonPackKey) {
  return COMPARISON_PACKS.find((pack) => pack.key === key)!;
}

function displayDate(value?: string): string | undefined {
  return value && /^\d{4}-\d{2}-\d{2}[ T]\d{2}:/.test(value) ? value.slice(0, 10) : value;
}

function objectValue(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function validManifest(value: unknown): value is RawManifest {
  return objectValue(value) && Array.isArray(value.entries) && value.entries.every((entry) =>
    objectValue(entry) && typeof entry.entity === "string" && typeof entry.card_path === "string" && objectValue(entry.key_numbers)
  );
}

function validPercentiles(value: unknown): value is RawPercentiles {
  return objectValue(value) && objectValue(value.packs);
}

function validComparables(value: unknown): value is RawComparables {
  return objectValue(value) && objectValue(value.packs);
}

async function fetchJson(path: string): Promise<unknown> {
  const response = await fetch(publicPath(path));
  if (!response.ok) throw new Error(`${path} unavailable`);
  return response.json();
}

export function CompareExperience() {
  const [packKey, setPackKey] = useState<ComparisonPackKey>("nba_players");
  const [requested, setRequested] = useState<{ pack: ComparisonPackKey; a?: string; b?: string }>({ pack: "nba_players" });
  const [data, setData] = useState<ComparisonPack>();
  const [aSlug, setASlug] = useState("");
  const [bSlug, setBSlug] = useState("");
  const [aQuery, setAQuery] = useState("");
  const [bQuery, setBQuery] = useState("");
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);

  const readUrl = () => {
    const params = new URLSearchParams(window.location.search);
    const pack = COMPARISON_PACKS.find((item) => item.key === params.get("pack"))?.key || "nba_players";
    setRequested({ pack, a: params.get("a") || undefined, b: params.get("b") || undefined });
    setPackKey(pack);
  };

  useEffect(() => {
    readUrl();
    window.addEventListener("popstate", readUrl);
    return () => window.removeEventListener("popstate", readUrl);
  }, []);

  useEffect(() => {
    const info = packInfo(packKey);
    let active = true;
    setData(undefined);
    setError("");
    Promise.all([fetchJson(info.manifest), fetchJson("entity_percentiles.json"), fetchJson("entity_comparables.json")]).then(([manifest, percentiles, comparables]) => {
      if (!validManifest(manifest) || !validPercentiles(percentiles) || !validComparables(comparables)) throw new Error("invalid comparison schema");
      if (active) setData(normalizeComparisonPack(packKey, manifest, percentiles, comparables));
    }).catch(() => { if (active) setError("Published comparison artifacts could not be loaded."); });
    return () => { active = false; };
  }, [packKey, retry]);

  useEffect(() => {
    if (!data?.entities.length) return;
    const valid = new Set(data.entities.map((entity) => entity.slug));
    const a = requested.pack === packKey && requested.a && valid.has(requested.a) ? requested.a : data.suggestedPair?.[0] || data.entities[0].slug;
    const candidate = requested.pack === packKey && requested.b && valid.has(requested.b) && requested.b !== a ? requested.b : data.suggestedPair?.[1];
    const b = candidate && candidate !== a ? candidate : data.entities.find((entity) => entity.slug !== a)?.slug || a;
    setASlug(a);
    setBSlug(b);
    setAQuery(data.entities.find((entity) => entity.slug === a)?.name || "");
    setBQuery(data.entities.find((entity) => entity.slug === b)?.name || "");
  }, [data, packKey, requested]);

  useEffect(() => {
    if (!aSlug || !bSlug) return;
    const url = new URL(window.location.href);
    url.searchParams.set("pack", packKey);
    url.searchParams.set("a", aSlug);
    url.searchParams.set("b", bSlug);
    window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
  }, [packKey, aSlug, bSlug]);

  const a = useMemo(() => data?.entities.find((entity) => entity.slug === aSlug), [data, aSlug]);
  const b = useMemo(() => data?.entities.find((entity) => entity.slug === bSlug), [data, bSlug]);
  const info = packInfo(packKey);

  const changePack = (value: string) => {
    const next = value as ComparisonPackKey;
    setRequested({ pack: next });
    setASlug("");
    setBSlug("");
    setAQuery("");
    setBQuery("");
    const url = new URL(window.location.href);
    url.searchParams.set("pack", next);
    url.searchParams.delete("a");
    url.searchParams.delete("b");
    window.history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
    setPackKey(next);
  };
  const swap = () => { setASlug(bSlug); setBSlug(aSlug); setAQuery(bQuery); setBQuery(aQuery); };
  const findByName = (value: string) => data?.entities.find((entity) => entity.name.toLocaleLowerCase() === value.trim().toLocaleLowerCase());
  const chooseA = (value: string) => {
    setAQuery(value);
    const hit = findByName(value);
    if (!hit) return;
    if (hit.slug === bSlug) {
      setASlug(hit.slug);
      setBSlug(aSlug);
      setAQuery(hit.name);
      setBQuery(a?.name || "");
      return;
    }
    setASlug(hit.slug);
  };
  const chooseB = (value: string) => {
    setBQuery(value);
    const hit = findByName(value);
    if (hit && hit.slug !== aSlug) setBSlug(hit.slug);
  };
  const aMatchesInput = Boolean(a && aQuery.trim() && a.name.toLocaleLowerCase() === aQuery.trim().toLocaleLowerCase());
  const bMatchesInput = Boolean(b && bQuery.trim() && b.name.toLocaleLowerCase() === bQuery.trim().toLocaleLowerCase());
  const noMatch = Boolean(data && (!aMatchesInput || !bMatchesInput));

  return (
    <section className="compare-experience" aria-label="Entity comparison controls and results">
      <div className="compare-controls">
        <label><span>Pack</span><select value={packKey} onChange={(event) => changePack(event.target.value)}>{COMPARISON_PACKS.map((pack) => <option key={pack.key} value={pack.key}>{pack.label}</option>)}</select></label>
        <label><span>Profile A</span><input list="compare-entities-a" value={aQuery} onChange={(event) => chooseA(event.target.value)} placeholder="Search a profile" aria-label="Profile A" />
          <datalist id="compare-entities-a">{data?.entities.map((entity) => <option key={entity.slug} value={entity.name} />)}</datalist></label>
        <button className="compare-swap" type="button" onClick={swap} disabled={!a || !b} aria-label="Swap profile A and profile B">Swap</button>
        <label><span>Profile B</span><input list="compare-entities-b" value={bQuery} onChange={(event) => chooseB(event.target.value)} placeholder="Search a profile" aria-label="Profile B" />
          <datalist id="compare-entities-b">{data?.entities.filter((entity) => entity.slug !== aSlug).map((entity) => <option key={entity.slug} value={entity.name} />)}</datalist></label>
      </div>
      <p className="compare-status">{data ? `${data.nInPack} profiles in ${info.label}.` : "Loading published pack data..."}</p>
      {error ? <p className="compare-error" role="alert">{error} <button type="button" onClick={() => setRetry((value) => value + 1)}>Retry</button></p> : null}
      {noMatch ? <p className="compare-empty" role="status">Choose a published profile from the list.</p> : null}
      {data && a && b && aMatchesInput && bMatchesInput ? <ComparisonResults pack={data} a={a} b={b} manifest={info.manifest} /> : null}
    </section>
  );
}

function ComparisonResults({ pack, a, b, manifest }: { pack: ComparisonPack; a: ComparisonEntity; b: ComparisonEntity; manifest: string }) {
  return <>
    <div className="compare-profiles">
      <ProfileHeading entity={a} pack={pack.key} label="Profile A" />
      <ProfileHeading entity={b} pack={pack.key} label="Profile B" />
    </div>
    {pack.metricKeys.length ? <div className="compare-table-wrap"><table className="compare-table"><thead><tr><th scope="col">Metric</th><th scope="col">{a.name}</th><th scope="col">{b.name}</th></tr></thead><tbody>
      {pack.metricKeys.map((key) => <MetricRow key={key} field={key} a={a} b={b} />)}
    </tbody></table></div> : <p className="compare-empty">This pack has no published within-pack percentile fields, so it cannot show a ranked comparison.</p>}
    <p className="compare-note">Percentiles are within this pack only. Higher means a higher raw measured value, never better. Corpus labels describe the years represented by the card; they are not projections.</p>
    <p className="compare-sources">Sources: <a href={publicPath(manifest)} target="_blank" rel="noreferrer">raw manifest</a>, <a href={publicPath("entity_percentiles.json")} target="_blank" rel="noreferrer">raw percentiles</a>, and <a href={publicPath("entity_comparables.json")} target="_blank" rel="noreferrer">raw comparables</a>.</p>
  </>;
}

function ProfileHeading({ entity, pack, label }: { entity: ComparisonEntity; pack: string; label: string }) {
  const asOf = displayDate(entity.asOf);
  return <article className="compare-profile"><span>{label}</span><h2><Link href={`/analytics/players/${pack}/${entity.slug}`}>{entity.name}</Link></h2><p>{asOf ? `As of ${asOf}` : "No published as-of date"}</p></article>;
}

function MetricRow({ field, a, b }: { field: string; a: ComparisonEntity; b: ComparisonEntity }) {
  const unit = metricUnit(field);
  return <tr><th scope="row"><span>{metricLabel(field)}</span>{unit ? <small>{unit}</small> : null}</th><MetricCell value={a.values[field]} percentile={a.percentiles[field]} field={field} /><MetricCell value={b.values[field]} percentile={b.percentiles[field]} field={field} /></tr>;
}

function MetricCell({ value, percentile, field }: { value: unknown; percentile: unknown; field: string }) {
  const rank = typeof percentile === "number" ? Math.max(0, Math.min(100, percentile)) : undefined;
  return <td><strong>{formatMetric(value, field)}</strong><span className="compare-rank">{formatPercentile(percentile)}</span>{rank !== undefined ? <span className="compare-bar" aria-label={formatPercentile(rank)}><i style={{ width: `${rank}%` }} /></span> : null}</td>;
}
