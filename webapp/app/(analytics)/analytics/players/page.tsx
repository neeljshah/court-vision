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
// table columns: first entry's scalar key_numbers, minus ids and the name field.
function colKeys(entries: Entry[]): string[] {
  const kn = entries[0]?.key_numbers || {};
  return Object.entries(kn)
    .filter(([k, v]) => !/_id$/.test(k) && k !== "team_full_name" && (typeof v === "number" || typeof v === "string" || typeof v === "boolean"))
    .map(([k]) => k).slice(0, 6);
}
function heroStat(ins: Insight): { value: string; label: string } | null {
  const c = ins.cited && ins.cited[0];
  if (!c) return null;
  const seg = (c.field || "").split(".").pop() || "";
  return { value: fmt(c.value), label: label(seg) };
}

export const metadata = {
  title: "Entities",
  description: "1,549 descriptive cards across basketball, baseball, soccer, and tennis. Measured historical rates, floors-gated. No edge is claimed.",
};

const STYLES = `
.pl-marq{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px}
.pl-card{display:flex;flex-direction:column;background:var(--paper-raised);border:1px solid var(--rule);border-radius:var(--radius-card);box-shadow:var(--shadow-card);padding:18px;transition:box-shadow var(--dur-base) var(--ease-ui),border-color var(--dur-base) var(--ease-ui),transform var(--dur-base) var(--ease-ui)}
.pl-card:hover{box-shadow:var(--shadow-raise);border-color:var(--accent);transform:translateY(-2px);text-decoration:none}
.pl-clamp{display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.pl-tblwrap{overflow-x:auto;border:1px solid var(--rule);border-radius:var(--radius-card)}
.pl-tbl{width:100%;border-collapse:collapse;font-size:13.5px}
.pl-tbl th{text-align:left;font-weight:700;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink-3);padding:11px 14px;border-bottom:1px solid var(--rule-strong);white-space:nowrap;background:var(--paper)}
.pl-tbl td{padding:10px 14px;border-bottom:1px solid var(--rule);color:var(--ink-2);white-space:nowrap}
.pl-tbl td.num{font-family:var(--font-mono);font-feature-settings:'tnum' 1;color:var(--ink)}
.pl-tbl tbody tr:hover td{background:var(--paper-tint)}
.pl-tbl a{font-weight:500}
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
          Each card is floors-gated measured history -- per-36 rates, surface splits, pitch distributions --
          not a projection. {marquee.length} carry a precomputed Scout read; the rest are in the pack tables below.
        </p>
        <div style={{ display: "inline-flex", alignItems: "center", gap: 8, background: "var(--paper-tint)", border: "1px solid var(--rule-strong)", borderRadius: 8, padding: "8px 14px", fontSize: 13, color: "var(--ink-2)", marginTop: 16 }}>
          <span className="dot d-desc" style={{ width: 8, height: 8 }} /> Descriptive only -- no edge claimed. edge_claimed: false.
        </div>
      </header>

      <section aria-label="Insight-backed entities" style={{ marginBottom: 8 }}>
        <h2 className="serif" style={{ fontWeight: 500, fontSize: 28, marginBottom: 4 }}>Insight-backed</h2>
        <p style={{ color: "var(--ink-3)", fontSize: 14, marginBottom: 18 }}>{marquee.length} entities Scout has already read and cited.</p>
        <div className="pl-marq">
          {marquee.map(({ ins, sport, packLabel }) => {
            const hero = heroStat(ins);
            return (
              <Link key={`${ins.pack}/${ins.slug}`} href={`/analytics/players/${ins.pack}/${ins.slug}`} className="pl-card">
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
        const asOf = manifest.entries[0]?.as_of;
        return (
          <section key={pack.slug} id={pack.slug} style={{ marginTop: 44, scrollMarginTop: 80 }}>
            <div style={{ display: "flex", alignItems: "baseline", gap: 12, marginBottom: 14, flexWrap: "wrap" }}>
              <span aria-hidden style={{ width: 9, height: 9, borderRadius: "50%", background: SPORT_COLOR[pack.sport] }} />
              <h2 className="serif" style={{ fontWeight: 500, fontSize: 26 }}>{pack.label}</h2>
              <span style={{ color: "var(--ink-3)", fontSize: 13 }}>{manifest.entries.length.toLocaleString()} cards{asOf ? ` \u00B7 as of ${asOf}` : ""}</span>
            </div>
            <div className="pl-tblwrap">
              <table className="pl-tbl">
                <thead>
                  <tr>
                    <th>Entity</th>
                    {cols.map((c) => <th key={c}>{label(c)}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {rows.map(({ slug, entry }) => (
                    <tr key={slug}>
                      <td><Link href={`/analytics/players/${pack.slug}/${slug}`}>{nameFor(entry)}</Link></td>
                      {cols.map((c) => <td key={c} className="num">{fmt(entry.key_numbers[c])}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        );
      })}
    </div>
  );
}
