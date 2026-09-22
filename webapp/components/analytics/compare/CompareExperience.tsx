"use client";

import { useEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { ArrowLeftRight } from "lucide-react";
import {
  COMPARISON_PACKS,
  normalizeComparisonPack, type ComparisonEntity, type ComparisonPack, type ComparisonPackKey,
  type RawComparables, type RawManifest, type RawPercentiles,
} from "@/lib/analytics/comparisonData";
import { type TennisSurface } from "@/lib/analytics/tennisSurfaceComparison";
import { mlbAtlasFamily, mlbAtlasFamilyOptions, parseMlbAtlasFamily, type MlbAtlasFamily } from "@/lib/analytics/mlbAtlasFamily";
import { ComparisonResults } from "./ComparisonResults";
import { marqueePair } from "@/lib/analytics/compareDefaults";

const DATA_ROOT = "/data/showcase/";
type RequestedPair = { pack: ComparisonPackKey; a?: string; b?: string; family?: MlbAtlasFamily };

function publicPath(path: string): string {
  return `${process.env.NEXT_PUBLIC_BASE_PATH || ""}${DATA_ROOT}${path}`;
}

function packInfo(key: ComparisonPackKey) {
  return COMPARISON_PACKS.find((pack) => pack.key === key)!;
}

const SPORT_GROUPS = [
  { key: "nba", label: "Basketball", packs: ["nba_players", "nba_teams"] as ComparisonPackKey[] },
  { key: "mlb", label: "Baseball", packs: ["mlb_batters", "mlb_pitch"] as ComparisonPackKey[] },
  { key: "soccer", label: "Soccer", packs: ["soccer"] as ComparisonPackKey[] },
  { key: "tennis", label: "Tennis", packs: ["tennis"] as ComparisonPackKey[] },
] as const;

function sportForPack(key: ComparisonPackKey) {
  return SPORT_GROUPS.find((sport) => sport.packs.includes(key));
}

function urlSurface(value: string | null): TennisSurface {
  return value === "clay" || value === "grass" ? value : "hard";
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

async function fetchJson(path: string, signal: AbortSignal): Promise<unknown> {
  const response = await fetch(publicPath(path), { signal });
  if (!response.ok) throw new Error(`${path} unavailable`);
  return response.json();
}

export function CompareExperience() {
  const [packKey, setPackKey] = useState<ComparisonPackKey>("nba_players");
  const [requested, setRequested] = useState<RequestedPair>({ pack: "nba_players" });
  const [explicitMlbFamily, setExplicitMlbFamily] = useState<MlbAtlasFamily>();
  const [data, setData] = useState<ComparisonPack>();
  const [aSlug, setASlug] = useState("");
  const [bSlug, setBSlug] = useState("");
  const [aQuery, setAQuery] = useState("");
  const [bQuery, setBQuery] = useState("");
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [surface, setSurface] = useState<TennisSurface>("hard");
  const [urlReady, setUrlReady] = useState(false);
  const [pairReady, setPairReady] = useState(false);
  const intendedPack = useRef<ComparisonPackKey>("nba_players");
  const intentRevision = useRef(0);
  const [activeRevision, setActiveRevision] = useState(0);

  const beginNavigation = (pack: ComparisonPackKey) => {
    intendedPack.current = pack;
    intentRevision.current += 1;
    setActiveRevision(intentRevision.current);
  };

  const readUrl = () => {
    const params = new URLSearchParams(window.location.search);
    const pack = COMPARISON_PACKS.find((item) => item.key === params.get("pack"))?.key || "nba_players";
    beginNavigation(pack);
    setPairReady(false);
    setASlug("");
    setBSlug("");
    setAQuery("");
    setBQuery("");
    const family = pack === "mlb_pitch" ? parseMlbAtlasFamily(params.get("family")) : undefined;
    setRequested({ pack, a: params.get("a") || undefined, b: params.get("b") || undefined, family });
    setExplicitMlbFamily(family);
    setSurface(pack === "tennis" ? urlSurface(params.get("surface")) : "hard");
    setPackKey(pack);
    setUrlReady(true);
  };

  useEffect(() => {
    readUrl();
    window.addEventListener("popstate", readUrl);
    return () => window.removeEventListener("popstate", readUrl);
  }, []);

  useEffect(() => {
    if (!urlReady) return;
    const info = packInfo(packKey);
    const controller = new AbortController();
    setData(undefined);
    setError("");
    Promise.all([fetchJson(info.manifest, controller.signal), fetchJson("entity_percentiles.json", controller.signal), fetchJson("entity_comparables.json", controller.signal)]).then(([manifest, percentiles, comparables]) => {
      if (!validManifest(manifest) || !validPercentiles(percentiles) || !validComparables(comparables)) throw new Error("invalid comparison schema");
      if (!controller.signal.aborted) setData(normalizeComparisonPack(packKey, manifest, percentiles, comparables));
    }).catch((reason: unknown) => {
      if (!controller.signal.aborted && (!(reason instanceof DOMException) || reason.name !== "AbortError")) setError("Published comparison artifacts could not be loaded.");
    });
    return () => controller.abort();
  }, [packKey, retry, urlReady]);

  useEffect(() => {
    if (intentRevision.current !== activeRevision || !urlReady || data?.key !== packKey || !data.entities.length) return;
    const valid = new Set(data.entities.map((entity) => entity.slug));
    if (packKey === "mlb_pitch" && (requested.family && (!requested.a || !requested.b) || Boolean(requested.a) !== Boolean(requested.b))) {
      const a = requested.a && valid.has(requested.a) ? requested.a : "";
      const b = requested.b && valid.has(requested.b) ? requested.b : "";
      setASlug(a); setBSlug(b);
      setAQuery(data.entities.find((entity) => entity.slug === a)?.name || ""); setBQuery(data.entities.find((entity) => entity.slug === b)?.name || "");
      setPairReady(false);
      return;
    }
    const defaults = marqueePair(packKey, data.entities);
    const a = requested.pack === packKey && requested.a && valid.has(requested.a) ? requested.a : defaults?.[0] || data.entities[0].slug;
    const candidate = requested.pack === packKey && requested.b && valid.has(requested.b) && requested.b !== a ? requested.b : defaults?.[1];
    const b = candidate && candidate !== a ? candidate : data.entities.find((entity) => entity.slug !== a)?.slug || a;
    const requestedPairFamily = packKey === "mlb_pitch" ? mlbAtlasFamily(data.entities.find((entity) => entity.slug === a)?.sourceEntity) : undefined;
    const linkedFamily = parseMlbAtlasFamily(new URL(window.location.href).searchParams.get("family"));
    if (requestedPairFamily && requestedPairFamily === mlbAtlasFamily(data.entities.find((entity) => entity.slug === b)?.sourceEntity) && linkedFamily && linkedFamily !== requestedPairFamily) { setExplicitMlbFamily(undefined); setRequested({ ...requested, family: undefined }); const url = new URL(window.location.href); url.searchParams.delete("family"); window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`); }
    setASlug(a);
    setBSlug(b);
    setAQuery(data.entities.find((entity) => entity.slug === a)?.name || "");
    setBQuery(data.entities.find((entity) => entity.slug === b)?.name || "");
    setPairReady(true);
  }, [data, packKey, requested, urlReady, activeRevision]);

  useEffect(() => {
    if (intendedPack.current !== packKey || intentRevision.current !== activeRevision || !urlReady || !pairReady || data?.key !== packKey || !aSlug || !bSlug) return;
    const url = new URL(window.location.href);
    url.searchParams.set("pack", packKey);
    url.searchParams.set("a", aSlug);
    url.searchParams.set("b", bSlug);
    if (packKey === "tennis") url.searchParams.set("surface", surface);
    else url.searchParams.delete("surface");
    const currentPairFamily = packKey === "mlb_pitch" ? mlbAtlasFamily(data.entities.find((entity) => entity.slug === aSlug)?.sourceEntity) : undefined;
    const otherPairFamily = packKey === "mlb_pitch" ? mlbAtlasFamily(data.entities.find((entity) => entity.slug === bSlug)?.sourceEntity) : undefined;
    if (packKey === "mlb_pitch" && explicitMlbFamily && (!currentPairFamily || currentPairFamily === otherPairFamily && explicitMlbFamily === currentPairFamily)) url.searchParams.set("family", explicitMlbFamily);
    else url.searchParams.delete("family");
    window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
  }, [packKey, aSlug, bSlug, surface, urlReady, pairReady, data, activeRevision, explicitMlbFamily]);

  const a = useMemo(() => data?.entities.find((entity) => entity.slug === aSlug), [data, aSlug]);
  const b = useMemo(() => data?.entities.find((entity) => entity.slug === bSlug), [data, bSlug]);
  const info = packInfo(packKey);
  const activeSport = sportForPack(packKey);

  const changePack = (value: string) => {
    const next = value as ComparisonPackKey;
    if (next === intendedPack.current) return;
    beginNavigation(next);
    setPairReady(false);
    setData(undefined);
    setRequested({ pack: next });
    setExplicitMlbFamily(undefined);
    setASlug("");
    setBSlug("");
    setAQuery("");
    setBQuery("");
    const url = new URL(window.location.href);
    url.searchParams.set("pack", next);
    url.searchParams.delete("a");
    url.searchParams.delete("b");
    url.searchParams.delete("surface");
    url.searchParams.delete("family");
    window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
    setSurface("hard");
    setPackKey(next);
  };
  const swap = () => { setASlug(bSlug); setBSlug(aSlug); setAQuery(bQuery); setBQuery(aQuery); };
  const pairFamily = packKey === "mlb_pitch" && a && b && mlbAtlasFamily(a.sourceEntity) === mlbAtlasFamily(b.sourceEntity) ? mlbAtlasFamily(a.sourceEntity) : undefined;
  const singleFamily = packKey === "mlb_pitch" && Boolean(a) !== Boolean(b) ? mlbAtlasFamily(a?.sourceEntity || b?.sourceEntity) : undefined;
  const activeMlbFamily = packKey === "mlb_pitch" ? pairFamily || explicitMlbFamily || singleFamily : undefined;
  const selectableEntities = activeMlbFamily ? (data?.entities || []).filter((entity) => mlbAtlasFamily(entity.sourceEntity) === activeMlbFamily) : data?.entities || [];
  const writeMlbUrl = (family: MlbAtlasFamily | undefined, nextA?: string, nextB?: string) => {
    const url = new URL(window.location.href);
    if (family) url.searchParams.set("family", family); else url.searchParams.delete("family");
    if (nextA) url.searchParams.set("a", nextA); else url.searchParams.delete("a");
    if (nextB) url.searchParams.set("b", nextB); else url.searchParams.delete("b");
    window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
  };
  const chooseMlbFamily = (value: string) => {
    const family = parseMlbAtlasFamily(value);
    if (!family || family === activeMlbFamily) return;
    beginNavigation("mlb_pitch");
    setExplicitMlbFamily(family);
    setRequested({ pack: "mlb_pitch", family });
    setASlug(""); setBSlug(""); setAQuery(""); setBQuery("");
    setPairReady(false);
    writeMlbUrl(family);
  };
  const findByName = (value: string) => selectableEntities.find((entity) => entity.name.toLocaleLowerCase() === value.trim().toLocaleLowerCase());
  const chooseA = (value: string) => {
    setAQuery(value);
    if (packKey === "mlb_pitch" && !value.trim()) {
      const family = activeMlbFamily;
      beginNavigation("mlb_pitch");
      setExplicitMlbFamily(family);
      setRequested({ pack: "mlb_pitch", family, b: bSlug || undefined });
      setASlug(""); setPairReady(false);
      writeMlbUrl(family, undefined, bSlug || undefined);
      return;
    }
    const hit = findByName(value);
    if (!hit) return;
    if (packKey === "mlb_pitch") {
      if (hit.slug === bSlug) return;
      setASlug(hit.slug); setPairReady(Boolean(bSlug)); writeMlbUrl(explicitMlbFamily, hit.slug, bSlug || undefined);
      return;
    }
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
    if (packKey === "mlb_pitch" && !value.trim()) {
      const family = activeMlbFamily;
      beginNavigation("mlb_pitch");
      setExplicitMlbFamily(family);
      setRequested({ pack: "mlb_pitch", family, a: aSlug || undefined });
      setBSlug(""); setPairReady(false);
      writeMlbUrl(family, aSlug || undefined);
      return;
    }
    const hit = findByName(value);
    if (packKey !== "mlb_pitch" && hit?.slug === aSlug) {
      setBSlug(hit.slug); setASlug(bSlug); setBQuery(hit.name); setAQuery(b?.name || "");
      return;
    }
    if (hit && hit.slug !== aSlug) {
      setBSlug(hit.slug);
      if (packKey === "mlb_pitch") { setPairReady(Boolean(aSlug)); writeMlbUrl(explicitMlbFamily, aSlug || undefined, hit.slug); }
    }
  };
  const commitA = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") chooseA(event.currentTarget.value);
  };
  const commitB = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") chooseB(event.currentTarget.value);
  };
  const aMatchesInput = Boolean(a && aQuery.trim() && a.name.toLocaleLowerCase() === aQuery.trim().toLocaleLowerCase());
  const bMatchesInput = Boolean(b && bQuery.trim() && b.name.toLocaleLowerCase() === bQuery.trim().toLocaleLowerCase());
  const unmatchedQuery = !aMatchesInput ? aQuery.trim() : !bMatchesInput ? bQuery.trim() : "";
  const noMatch = Boolean(data && unmatchedQuery);
  const duplicate = noMatch && Boolean(findByName(unmatchedQuery)) && aQuery.trim().toLocaleLowerCase() === bQuery.trim().toLocaleLowerCase();

  return (
    <section className="compare-experience" aria-label="Entity comparison controls and results">
      <div className="compare-sport-switcher" aria-label="Choose a sport">
        <span className="compare-section-label">Start with a sport</span>
        <div className="compare-sport-tabs">
          {SPORT_GROUPS.map((sport) => <button key={sport.key} type="button" aria-pressed={activeSport?.key === sport.key} className={activeSport?.key === sport.key ? "is-active" : ""} onClick={() => changePack(sport.packs[0])}>{sport.label}</button>)}
        </div>
      </div>
      <div className={`compare-controls${packKey === "mlb_pitch" ? " has-family" : ""}`}>
        <label><span>Pack</span><select value={packKey} onChange={(event) => changePack(event.target.value)}>{COMPARISON_PACKS.map((pack) => <option key={pack.key} value={pack.key}>{pack.label}</option>)}</select></label>
        {packKey === "mlb_pitch" ? <label className="compare-family"><span>Record type</span><select value={activeMlbFamily || ""} onChange={(event) => chooseMlbFamily(event.target.value)} aria-label="MLB atlas record type"><option value="">Choose a record type</option>{mlbAtlasFamilyOptions(data?.entities || []).map((option) => <option key={option.family} value={option.family}>{option.label} ({option.count})</option>)}</select></label> : null}
        <label><span>Profile A</span><input list="compare-entities-a" value={aQuery} onChange={(event) => chooseA(event.target.value)} onKeyDown={commitA} placeholder="Search a profile" aria-label="Profile A" />
          <datalist id="compare-entities-a">{selectableEntities.filter((entity) => packKey !== "mlb_pitch" || entity.slug !== bSlug).map((entity) => <option key={entity.slug} value={entity.name} />)}</datalist></label>
        <button className="compare-swap" type="button" onClick={swap} disabled={!a || !b} aria-label="Swap profile A and profile B"><ArrowLeftRight aria-hidden="true" size={15} /> Swap</button>
        <label><span>Profile B</span><input list="compare-entities-b" value={bQuery} onChange={(event) => chooseB(event.target.value)} onKeyDown={commitB} placeholder="Search a profile" aria-label="Profile B" />
          <datalist id="compare-entities-b">{selectableEntities.filter((entity) => entity.slug !== aSlug).map((entity) => <option key={entity.slug} value={entity.name} />)}</datalist></label>
      </div>
      <p className="compare-status">{data ? `${data.nInPack} profiles in ${info.label}.` : "Loading published pack data..."}</p>
      {error ? <p className="compare-error" role="alert">{error} <button type="button" onClick={() => setRetry((value) => value + 1)}>Retry</button></p> : null}
      {noMatch ? <p className="compare-empty" role="status">{duplicate ? `${unmatchedQuery} is already selected. Choose a different profile for A or B.` : `No published profile named ${unmatchedQuery} in this pack.`}</p> : null}
      {pairReady && data?.key === packKey && a && b && aMatchesInput && bMatchesInput ? <ComparisonResults pack={data} a={a} b={b} manifest={info.manifest} sport={activeSport?.key} surface={surface} onSurfaceChange={setSurface} /> : null}
    </section>
  );
}
