// app/(analytics)/analytics/players/page.tsx -- the Entities atlas index.
//
// Reading-Room browse surface for the 1,549 descriptive cards across 7 packs.
// Top: a marquee of the 60 insight-backed entities (each has a precomputed Scout
// read). Behind it: the full pack tables (every entry, all scalar key_numbers),
// grouped by pack, each row linking to its entity card. Server component, static
// export -- reads the staged manifests + insight envelopes at build. No live data.
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import Link from "next/link";
import { asOfDate } from "@/lib/analytics/format";

type KN = Record<string, unknown>;
type Entry = { entity: string; card_path: string; key_numbers: KN; as_of?: string };
type Manifest = { generated_at?: string; n_entries?: number; entries: Entry[] };
type Insight = {
  pack: string; slug: string; display_name: string; one_liner: string;
  cited?: Array<{ field?: string; value: unknown }>; as_of?: string;
};

type Pack = { slug: string; manifest: string; label: string; sport: string };
const PACKS: Pack[] = [
  { slug: "nba_players", manifest: "atlas_nba_manifest.json", label: "NBA players", sport: "NBA" },
  { slug: "nba_teams", manifest: "atlas_nba_teams_manifest.json", label: "NBA teams", sport: "NBA" },
  { slug: "mlb_batters", manifest: "atlas_mlb_batters_manifest.json", label: "MLB batters", sport: "MLB" },
  { slug: "mlb_pitch", manifest: "atlas_mlb_pitch_manifest.json", label: "MLB pitch types", sport: "MLB" },
  { slug: "soccer", manifest: "atlas_soccer_manifest.json", label: "Soccer teams", sport: "Soccer" },
  { slug: "tennis", manifest: "atlas_tennis_manifest.json", label: "Tennis players", sport: "Tennis" },
  { slug: "calibration", manifest: "atlas_calibration_manifest.json", label: "Calibration checkpoints", sport: "Cross-sport" },
];
const SPORT_COLOR: Record<string, string> = { NBA: "#1D5C7A", MLB: "#1E6B45", Soccer: "#6A5A8C", Tennis: "#C6852B", "Cross-sport": "#8A8078" };

const SHOWCASE = join(process.cwd(), "public", "data", "showcase");
const INSIGHTS = join(process.cwd(), "public", "data", "insights", "entities");

function base(p: string): string { return (p.split(/[\\/]/).pop() || p).replace(/\.[a-z0-9]+$/i, ""); }
function slugify(s: string): string { return s.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, ""); }
function withSlugs(entries: Entry[]): Array<{ slug: string; entry: Entry }> {
  const seen = new Set<string>();
  return entries.map((entry) => {
    let s = base(entry.card_path);
    if (seen.has(s)) s = slugify(entry.entity);
    seen.add(s);
    return { slug: s, entry };
  });
}
function readManifest(pack: Pack): Manifest | null {
  try { return JSON.parse(readFileSync(join(SHOWCASE, pack.manifest), "utf-8")) as Manifest; }
  catch { return null; }
}
function readInsights(pack: string): Insight[] {
  let files: string[] = [];
  try { files = readdirSync(join(INSIGHTS, pack)); } catch { return []; }
  const out: Insight[] = [];
  for (const f of files) {
    if (!f.endsWith(".json")) continue;
    try { out.push(JSON.parse(readFileSync(join(INSIGHTS, pack, f), "utf-8")) as Insight); } catch { /* skip */ }
  }
  return out;
}
function fmt(v: unknown): string {
  if (v === null || v === undefined) return "--";
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : String(parseFloat(v.toFixed(3)));
  return String(v);
}
// Pad integer-valued pct/per36 cells to one decimal so a whole number does not
// read as a typo beside its 1-decimal siblings. Lossless: fractional values keep
// their own precision (never rounded).
function fmtCell(k: string, v: unknown): string {
  if (typeof v === "number" && Number.isInteger(v) && /pct|per36/i.test(k)) return v.toFixed(1);
  return fmt(v);
}
function label(k: string): string {
  return k.replace(/^career_/, "").replace(/_/g, " ")
    .replace(/\bpct\b/g, "%").replace(/per36/g, "/36")
    .replace(/\bfg3\b/g, "3P").replace(/\bfg\b/g, "FG").replace(/\bft\b/g, "FT")
    .replace(/\bpts\b/g, "PTS").replace(/\breb\b/g, "REB").replace(/\bast\b/g, "AST").trim();
}
function nameFor(entry: Entry): string {
  const full = entry.key_numbers.team_full_name;
  if (typeof full === "string" && full) return full;
  return entry.entity.replace(/^(pitch_type|team):/, "$1 ").replace(/_/g, " ");
}
// table columns: rank every scalar key_number by fill rate across the WHOLE pack,
// then take the six densest (dropping any column >50% blank). Trusting entries[0]'s
// keys surfaced columns that were mostly "--" -- packs are heterogeneous/sparse
// (tennis surface splits, MLB velo p50/p90, calibration's alternate schemas), so a
// column present on row 0 could be null on three-quarters of the pack and read as
// broken. Fill-rate ranking keeps only columns that actually carry data.
function colKeys(entries: Entry[]): string[] {
  const isScalar = (v: unknown) => typeof v === "number" || typeof v === "string" || typeof v === "boolean";
  const filled = new Map<string, number>(); // key -> count of non-null scalar cells
  const order: string[] = []; // first-seen order (stable tiebreak for equal fill)
  for (const e of entries) {
    for (const [k, v] of Object.entries(e.key_numbers || {})) {
      if (/_id$/.test(k) || k === "team_full_name") continue;
      if (!filled.has(k)) { filled.set(k, 0); order.push(k); }
      if (v != null && isScalar(v)) filled.set(k, (filled.get(k) ?? 0) + 1);
    }
  }
  const n = entries.length || 1;
  const fillOf = (k: string) => filled.get(k) ?? 0;
  const ranked = order.sort((a, b) => fillOf(b) - fillOf(a));
  const kept = ranked.filter((k) => fillOf(k) / n >= 0.5).slice(0, 6);
  return kept.length ? kept : ranked.slice(0, 6); // fall back if a pack has no dense column
}
// The hero tile is a numeral slot (big serif tabular figures + metric label), so
// headline the first cited value that is actually a NUMBER. NBA-team cards lead
// their cited list with a player NAME (top_contributor); typesetting a name as a
// figure is a category error and overflows the fixed card -- skip to the first
// numeric cite (minutes / PRA rate). Numeric-first entities are unaffected.
function heroStat(ins: Insight): { value: string; label: string } | null {
  const c = (ins.cited || []).find((x) => typeof x.value === "number");
  if (!c) return null;
  const seg = (c.field || "").split(".").pop() || "";
  return { value: fmt(c.value), label: label(seg) };
}

export const metadata = {
  title: "Entities",
  description: "1,549 descriptive cards across basketball, baseball, soccer, and tennis. Measured historical rates held to conservative sample floors. No edge is claimed.",
};

// Client-side name filter (progressive enhancement, same vanilla-JS pattern as
// browse/page.tsx FILTER_JS): the page stays a server component -- no client file,
// no fetch. Show/hide any [data-name] (marquee cards + table rows) by substring,
// then hide a whole .pl-fsec section when none of its entities match so no empty
// pack header is left stranded. Inert if JS is off (everything renders visible).
const FILTER_JS = `(function(){var inp=document.getElementById('plsearch');if(!inp)return;var items=document.querySelectorAll('[data-name]');var secs=document.querySelectorAll('.pl-fsec');function apply(){var q=inp.value.toLowerCase().trim();for(var i=0;i<items.length;i++){var m=!q||items[i].getAttribute('data-name').indexOf(q)!==-1;items[i].style.display=m?'':'none';}for(var j=0;j<secs.length;j++){var d=secs[j].querySelectorAll('[data-name]'),any=false;for(var k=0;k<d.length;k++){if(d[k].style.display!=='none'){any=true;break;}}secs[j].style.display=any?'':'none';}}inp.addEventListener('input',apply);})();`;

const STYLES = `
.pl-search{width:100%;max-width:440px;font-family:var(--font-sans);font-size:15px;color:var(--ink);background:var(--paper-raised);border:1px solid var(--rule-strong);border-radius:var(--radius-pill,999px);padding:11px 18px;min-height:44px;margin:22px 0 6px}
.pl-search::placeholder{color:var(--ink-3)}
.pl-marq{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px}
.pl-card{display:flex;flex-direction:column;background:var(--paper-raised);border:1px solid var(--rule);border-radius:var(--radius-card);box-shadow:var(--shadow-card);padding:18px;transition:box-shadow var(--dur-base) var(--ease-ui),border-color var(--dur-base) var(--ease-ui),transform var(--dur-base) var(--ease-ui)}
.pl-card:hover{box-shadow:var(--shadow-raise);border-color:var(--accent);transform:translateY(-2px);text-decoration:none}
.pl-clamp{display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
/* pack-jump chips: the atlas is ~1,549 rows across 7 packs; without a shortcut a
   phone visitor finger-scrolls past ~482 NBA rows to reach MLB/soccer/tennis.
   Anchor links (section ids already exist), not sticky -- a pinned bar would eat
   the viewport the nav fix just reclaimed. 44px min touch target. */
.pl-jump{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 8px}
.pl-jump a{display:inline-flex;align-items:center;min-height:44px;font-size:13px;color:var(--ink-2);border:1px solid var(--rule-strong);border-radius:var(--radius-pill,999px);padding:6px 14px;white-space:nowrap;background:var(--paper-raised)}
.pl-jump a:hover{border-color:var(--accent);color:var(--ink);text-decoration:none}
.pl-jump a .n{color:var(--ink-3);margin-left:7px;font-variant-numeric:tabular-nums}
/* Edge-fade scroll cue (same recipe as charts/Figure.tsx scrollFrame): a paper
   fade + soft shadow at each edge that self-hides at the scroll start/end via the
   local-vs-scroll background-attachment mix. The sticky Entity column made the
   overflowing stat columns look like the whole table; this "more this way" hint
   tells a phone reader to swipe. Charts + Forecaster tables already wear it. */
.pl-tblwrap{overflow-x:auto;border:1px solid var(--rule);border-radius:var(--radius-card);
  background-color:var(--paper);
  background-image:linear-gradient(to right,var(--paper),rgba(0,0,0,0)),linear-gradient(to left,var(--paper),rgba(0,0,0,0)),radial-gradient(farthest-side at 0 50%,rgba(40,30,20,.16),rgba(0,0,0,0)),radial-gradient(farthest-side at 100% 50%,rgba(40,30,20,.16),rgba(0,0,0,0));
  background-position:left center,right center,left center,right center;
  background-repeat:no-repeat;
  background-size:36px 100%,36px 100%,14px 100%,14px 100%;
  background-attachment:local,local,scroll,scroll}
.pl-tbl{width:100%;border-collapse:collapse;font-size:13.5px}
.pl-tbl th{text-align:left;font-weight:700;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-3);padding:11px 14px;border-bottom:1px solid var(--rule-strong);white-space:nowrap;background:var(--paper)}
.pl-tbl td{padding:10px 14px;border-bottom:1px solid var(--rule);color:var(--ink-2);white-space:nowrap}
.pl-tbl td.num{font-family:var(--font-mono);font-feature-settings:'tnum' 1;color:var(--ink)}
.pl-tbl tbody tr:hover td{background:var(--paper-tint)}
.pl-tbl a{font-weight:500}
/* pin the Entity column so scrolling right to read stats never loses the name.
   opaque bg covers the columns sliding under it; a hairline marks the pinned edge. */
.pl-tbl th:first-child,.pl-tbl td:first-child{position:sticky;left:0;z-index:1;background:var(--paper-raised);box-shadow:1px 0 0 var(--rule)}
.pl-tbl th:first-child{background:var(--paper);z-index:2}
/* clear the sticky nav (desktop, 64px) on anchor jumps. At <=720 the nav is
   static (analytics.css), so a jump only needs a little breathing room. */
.pl-anchor{scroll-margin-top:80px}
@media(max-width:720px){.pl-anchor{scroll-margin-top:16px}}
`;

export default function EntitiesIndexPage() {
  const packs = PACKS.map((p) => ({ pack: p, manifest: readManifest(p), insights: readInsights(p.slug) }));
  const totalCards = packs.reduce((n, x) => n + (x.manifest?.entries.length || 0), 0);
  const marquee = packs.flatMap((x) => x.insights.map((ins) => ({ ins, sport: x.pack.sport, packLabel: x.pack.label })));

  return (
    <div className="wrap" style={{ paddingBottom: 8 }}>
      <style dangerouslySetInnerHTML={{ __html: STYLES }} />

      <header style={{ padding: "34px 0 20px", borderBottom: "1px solid var(--rule-strong)", marginBottom: 30 }}>
        <div className="overline">The atlas</div>
        <h1 className="serif" style={{ fontWeight: 500, fontSize: "clamp(2.4rem,5vw,3.4rem)", lineHeight: 1.05, letterSpacing: "-.02em", margin: "6px 0 10px" }}>Entities</h1>
        <p style={{ maxWidth: 680, color: "var(--ink-2)", fontSize: 18, lineHeight: 1.6 }}>
          {totalCards.toLocaleString()} descriptive cards across {new Set(PACKS.map((p) => p.sport)).size - 1} sports.
          Each card is measured history, held to conservative sample floors &mdash; per-36 rates, surface splits, pitch distributions &mdash;
          not a projection. {marquee.length} carry a precomputed Scout read; the rest are in the pack tables below.
        </p>
        <div style={{ display: "inline-flex", alignItems: "center", gap: 8, background: "var(--paper-tint)", border: "1px solid var(--rule-strong)", borderRadius: 8, padding: "8px 14px", fontSize: 13, color: "var(--ink-2)", marginTop: 16 }}>
          <span className="dot d-desc" style={{ width: 8, height: 8 }} /> Descriptive only &mdash; no edge claimed. edge_claimed: false.
        </div>
      </header>

      <input
        id="plsearch"
        type="search"
        className="pl-search"
        placeholder="Filter entities by name..."
        aria-label="Filter entities by name"
        autoComplete="off"
      />

      <nav aria-label="Jump to a pack" className="pl-jump">
        {packs.filter((x) => x.manifest && x.manifest.entries.length).map(({ pack, manifest }) => (
          <a key={pack.slug} href={`#${pack.slug}`}>
            {pack.label}<span className="n">{manifest!.entries.length.toLocaleString()}</span>
          </a>
        ))}
      </nav>

      <section aria-label="Insight-backed entities" className="pl-fsec" style={{ marginBottom: 8, marginTop: 20 }}>
        <h2 className="serif" style={{ fontWeight: 500, fontSize: 28, marginBottom: 4 }}>Insight-backed</h2>
        <p style={{ color: "var(--ink-3)", fontSize: 14, marginBottom: 18 }}>{marquee.length} entities Scout has already read and cited.</p>
        <div className="pl-marq">
          {marquee.map(({ ins, sport, packLabel }) => {
            const hero = heroStat(ins);
            return (
              <Link key={`${ins.pack}/${ins.slug}`} href={`/analytics/players/${ins.pack}/${ins.slug}`} className="pl-card" data-name={ins.display_name.toLowerCase()}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                  <span aria-hidden style={{ width: 7, height: 7, borderRadius: "50%", background: SPORT_COLOR[sport] }} />
                  <span className="overline" style={{ color: "var(--ink-3)" }}>{packLabel}</span>
                  <span className="dot d-desc" style={{ marginLeft: "auto" }} title="descriptive only" />
                </div>
                <div style={{ fontWeight: 600, fontSize: 18, color: "var(--ink)", lineHeight: 1.25 }}>{ins.display_name}</div>
                <p className="pl-clamp" style={{ color: "var(--ink-2)", fontSize: 14, lineHeight: 1.5, margin: "8px 0 14px" }}>{ins.one_liner}</p>
                {hero ? (
                  <div style={{ marginTop: "auto", display: "flex", alignItems: "baseline", gap: 8 }}>
                    <span className="serif tnum" style={{ fontWeight: 500, fontSize: "1.9rem", lineHeight: 1, color: "var(--ink)" }}>{hero.value}</span>
                    <span style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: ".06em", color: "var(--ink-3)", fontWeight: 600 }}>{hero.label}</span>
                  </div>
                ) : null}
              </Link>
            );
          })}
        </div>
      </section>

      {packs.map(({ pack, manifest }) => {
        if (!manifest || manifest.entries.length === 0) return null;
        const rows = withSlugs(manifest.entries);
        const cols = colKeys(manifest.entries);
        // Collapse machine timestamps (soccer/tennis/calibration carry ISO micros +
        // "+00:00") to a clean date, matching the entity detail page and DESIGN Sec.4;
        // descriptive corpus labels ("2025-26 regular season ...") pass through.
        const asOf = asOfDate(manifest.entries[0]?.as_of);
        return (
          <section key={pack.slug} id={pack.slug} className="pl-anchor pl-fsec" style={{ marginTop: 44 }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 14, flexWrap: "wrap" }}>
              <span aria-hidden style={{ width: 9, height: 9, borderRadius: "50%", background: SPORT_COLOR[pack.sport] }} />
              <h2 className="serif" style={{ fontWeight: 500, fontSize: 26 }}>{pack.label}</h2>
              <span style={{ color: "var(--ink-3)", fontSize: 13 }}>{manifest.entries.length.toLocaleString()} cards{asOf ? ` \u00B7 as of ${asOf}` : ""}</span>
            </div>
            <div className="pl-tblwrap">
              <table className="pl-tbl">
                <thead>
                  <tr>
                    <th scope="col">Entity</th>
                    {cols.map((c) => <th key={c} scope="col">{label(c)}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {rows.map(({ slug, entry }) => (
                    <tr key={slug} data-name={nameFor(entry).toLowerCase()}>
                      <td><Link href={`/analytics/players/${pack.slug}/${slug}`}>{nameFor(entry)}</Link></td>
                      {cols.map((c) => <td key={c} className="num">{fmtCell(c, entry.key_numbers[c])}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        );
      })}

      {/* eslint-disable-next-line react/no-danger */}
      <script dangerouslySetInnerHTML={{ __html: FILTER_JS }} />
    </div>
  );
}
