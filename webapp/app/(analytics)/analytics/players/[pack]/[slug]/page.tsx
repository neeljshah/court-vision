// app/(analytics)/analytics/players/[pack]/[slug]/page.tsx -- one entity's card.
//
// Reading-Room entity experience (mockups/entity.html): descriptive banner, the
// HTML card numbers (each wearing a Receipt and, when ranked, a PercentileBar),
// the Scout note (one_liner + chips), "what stands out" (three_things), the
// reading note (context_note), a floors box, and cross-links. Server component,
// static export: reads the staged atlas manifest + the precomputed insight
// envelope at build (data-free at runtime). generateStaticParams enumerates
// ALL 1,549 entities across 7 packs (see players/page.tsx report).
import { readFileSync } from "node:fs";
import { join } from "node:path";
import Link from "next/link";
import { notFound } from "next/navigation";
import { PercentileBar } from "@/components/analytics/PercentileBar";
import { Receipt, type ReceiptData } from "@/components/analytics/Receipt";
import { ScoutNote, type ScoutEnvelope } from "@/components/analytics/ScoutNote";
import { ScoutQuestions } from "@/components/analytics/ScoutQuestions";
import { asOfDate } from "@/lib/analytics/format";

type KN = Record<string, unknown>;
type Entry = { entity: string; card_path: string; key_numbers: KN; floors?: string; as_of?: string };
type Manifest = { descriptive_only?: boolean; entries: Entry[] };
type Insight = {
  slug: string; display_name: string; one_liner: string;
  three_things?: string[]; context_note?: string;
  cited?: Array<{ path: string; field?: string; value: unknown }>; as_of?: string;
};

type Pack = { slug: string; manifest: string; label: string; sport: string; noun: string; related: string[] };
const PACKS: Pack[] = [
  { slug: "nba_players", manifest: "atlas_nba_manifest.json", label: "NBA players", sport: "NBA", noun: "career per-36 rates", related: ["player_metric_landscape", "nba_consistency_profiles", "aging_curve_lite"] },
  { slug: "nba_teams", manifest: "atlas_nba_teams_manifest.json", label: "NBA teams", sport: "NBA", noun: "measured team rates", related: ["home_away_anatomy", "blowout_dynamics", "on_off_showcase"] },
  { slug: "mlb_batters", manifest: "atlas_mlb_batters_manifest.json", label: "MLB batters", sport: "MLB", noun: "measured plate-discipline and contact rates", related: ["statcast_showcase", "mlb_velo_bands"] },
  { slug: "mlb_pitch", manifest: "atlas_mlb_pitch_manifest.json", label: "MLB pitch types", sport: "MLB", noun: "measured pitch-level distributions", related: ["pitch_sequencing", "mlb_count_leverage"] },
  { slug: "soccer", manifest: "atlas_soccer_manifest.json", label: "Soccer teams", sport: "Soccer", noun: "measured recent-form rates", related: ["soccer_form_stability", "soccer_calibration_pack"] },
  { slug: "tennis", manifest: "atlas_tennis_manifest.json", label: "Tennis players", sport: "Tennis", noun: "measured surface win rates", related: ["tennis_surface_transfer", "tennis_showcase"] },
  { slug: "calibration", manifest: "atlas_calibration_manifest.json", label: "Calibration checkpoints", sport: "Cross-sport", noun: "measured calibration checkpoints", related: ["state_conditioned_calibration", "calibration_over_time"] },
];

const SHOWCASE = join(process.cwd(), "public", "data", "showcase");
const INSIGHTS = join(process.cwd(), "public", "data", "insights", "entities");

function base(p: string): string {
  return (p.split(/[\\/]/).pop() || p).replace(/\.[a-z0-9]+$/i, "");
}
function slugify(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
}
// Deterministic (slug, entry) pairs. Slug = card_path basename (matches the 60
// insight slugs 1:1); the one dup in 1,549 (mlb_pitch KC) falls back to slugify.
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
function readInsight(pack: string, slug: string): Insight | null {
  try { return JSON.parse(readFileSync(join(INSIGHTS, pack, `${slug}.json`), "utf-8")) as Insight; }
  catch { return null; }
}
// "Where this appears" links render module titles from the SAME manifest Browse
// uses, so they read as titles ("Player Metric Landscape") not raw lowercased slugs
// ("player metric landscape", which looked like leftover debug text). Built once per
// build; Title-Case fallback if an id is ever missing from the manifest.
let _modTitles: Record<string, string> | null = null;
function moduleTitle(id: string): string {
  if (!_modTitles) {
    try {
      const man = JSON.parse(readFileSync(join(SHOWCASE, "site_manifest.json"), "utf-8")) as { modules?: Array<{ id: string; title: string }> };
      _modTitles = Object.fromEntries((man.modules || []).map((m) => [m.id, m.title]));
    } catch { _modTitles = {}; }
  }
  return _modTitles[id] || id.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
type PctPack = { n_in_pack: number; entities: Record<string, Record<string, number>> };
// Parsed once per build, like _modTitles above; calibration (26 entities, under the artifact's min_n_ranked=30 floor) ships an empty entities map, so no bar renders there.
let _percentiles: Record<string, PctPack> | null = null;
function packPercentiles(pack: string): PctPack | null {
  if (!_percentiles) { try { _percentiles = (JSON.parse(readFileSync(join(SHOWCASE, "entity_percentiles.json"), "utf-8")) as { packs?: Record<string, PctPack> }).packs || {}; } catch { _percentiles = {}; } }
  return _percentiles[pack] || null;
}
// Only surface Scout pills whose answer actually lives in the committed corpus.
// The corpus entry's source_artifact IS this entity's insight file, so match on
// it, keep the answerable (status ok) ones, and use their VERBATIM question -- so
// each pill phrase-resolves in the router instead of dead-ending in "No verified
// answer". Mirrors m/[id]/page.tsx corpusQuestions; the old name-templated pills
// ("How does {name} profile in {sport}?") matched no phrasing and fell to the
// closest-cite fallback. No hit (the ~1,489 thin cards) -> no pills (honest).
function corpusQuestions(pack: string, slug: string): string[] {
  let entries: Array<{ q: string; a?: { source_artifact?: string; status?: string } }> = [];
  try {
    entries = (JSON.parse(readFileSync(join(process.cwd(), "public", "data", "ask", "corpus.json"), "utf-8")) as { entries?: typeof entries }).entries || [];
  } catch { return []; }
  const needle = `/entities/${pack}/${slug}.`;
  const hits = entries.filter(
    (e) => e.a?.status === "ok" && (e.a?.source_artifact || "").replace(/\\/g, "/").includes(needle)
  );
  return Array.from(new Set(hits.map((e) => e.q))).slice(0, 3);
}

function fmt(v: unknown): string {
  if (v === null || v === undefined) return "--";
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (typeof v === "number") return Number.isInteger(v) ? String(v) : String(parseFloat(v.toFixed(3)));
  return String(v);
}
// Rate/percent cells read as a set (fg% next to 3p% next to ft%), so a whole
// number stripped to "31" looks like a typo beside "42.5". Pad integer-valued
// pct/per36 cells to one decimal -- lossless (never rounds; fractional values
// keep their own precision, e.g. mlb 10.28 stays "10.28").
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
// scalar key_numbers only (skip ids + nested dicts) -> stat cells. team_full_name
// is excluded to match the atlas index's colKeys: it is the entity's own name
// (already the <h1>), not a measured figure to typeset in the numeric style.
function statCells(kn: KN): Array<[string, unknown]> {
  return Object.entries(kn).filter(([k, v]) =>
    !/_id$/.test(k) && k !== "team_full_name" && (typeof v === "number" || typeof v === "string" || typeof v === "boolean"));
}
function nameFor(entry: Entry): string {
  const full = entry.key_numbers.team_full_name;
  if (typeof full === "string" && full) return full;
  return entry.entity.replace(/^(pitch_type|team):/, "$1 ").replace(/_/g, " ");
}

export function generateStaticParams() {
  const out: Array<{ pack: string; slug: string }> = [];
  for (const p of PACKS) {
    const m = readManifest(p);
    if (!m) continue;
    for (const { slug } of withSlugs(m.entries)) out.push({ pack: p.slug, slug });
  }
  return out;
}

export function generateMetadata({ params }: { params: { pack: string; slug: string } }) {
  const pack = PACKS.find((p) => p.slug === params.pack);
  const m = pack && readManifest(pack);
  const hit = m && withSlugs(m.entries).find((x) => x.slug === params.slug);
  const name = readInsight(params.pack, params.slug)?.display_name || (hit && nameFor(hit.entry)) || "Entity";
  return {
    title: pack ? `${name} -- ${pack.label}` : "Entity",
    description: `Descriptive reference card for ${name}: measured historical rates, not a prediction. edge_claimed: false.`,
  };
}

const REPO = "webapp/public/data/showcase";
const box = { background: "var(--paper-raised)", border: "1px solid var(--rule)", borderRadius: 10, padding: 18, boxShadow: "var(--shadow-card)", marginBottom: 20 } as const;

export default function EntityPage({ params }: { params: { pack: string; slug: string } }) {
  const pack = PACKS.find((p) => p.slug === params.pack);
  if (!pack) notFound();
  const manifest = readManifest(pack);
  const hit = manifest && withSlugs(manifest.entries).find((x) => x.slug === params.slug);
  if (!manifest || !hit) notFound();
  const entry = hit.entry;
  const insight = readInsight(params.pack, params.slug);
  const name = insight?.display_name || nameFor(entry);
  // Machine timestamps (tennis cards carry ISO "2026-07-19T03:41:37...+00:00")
  // collapse to a clean date; descriptive labels pass through.
  const asOf = asOfDate(insight?.as_of || entry.as_of) || null;
  const cells = statCells(entry.key_numbers);
  const pctPack = packPercentiles(params.pack);
  const entityPcts = pctPack?.entities[params.slug];

  // The receipt popover header names WHAT this number cites (the field path), like
  // m/[id]/page.tsx does -- not the verdict token, which the dot + verdict already
  // encode. Verdict stays descriptive_only (the dot color). c.field is optional; the
  // Receipt omits the header cleanly when it is absent.
  const chips: ReceiptData[] = (insight?.cited || []).slice(0, 4).map((c) => ({
    value: fmt(c.value), label: c.field, sourceArtifact: c.path,
    asOf: asOf || undefined, verdict: "descriptive_only",
  }));
  // Written Scout notes cover 182 marquee cards of 1,549. For the rest, say what
  // this card DOES have (its own measured cells, its receipts, the pack's sample
  // floors) instead of the bare "no verified read" negative. Status stays no_data
  // -- the neutral glyph is the honest signal that no note was written here.
  const uncovered =
    `No written Scout note on this card yet -- those cover 182 marquee entities of 1,549. ` +
    `What is here is measured: ${cells.length} ${pack.noun}, each wearing its own receipt` +
    (entry.floors ? ", with the sample floors for this pack in the sidebar." : ".");
  const envelope: ScoutEnvelope = insight
    ? { status: "descriptive_only", prose: insight.one_liner, chips }
    : { status: "no_data", prose: uncovered };

  // Draw the Scout pills from real corpus hits for this entity (verbatim questions
  // that phrase-resolve), never templated strings that dead-end. Empty for the thin
  // cards -> ScoutQuestions renders nothing.
  const questions = corpusQuestions(params.pack, params.slug);

  return (
    <div className="wrap" style={{ paddingBottom: 8 }}>
      <nav aria-label="Breadcrumb" style={{ fontSize: 13, color: "var(--ink-3)", padding: "22px 0 6px" }}>
        <Link href="/analytics/players" style={{ color: "var(--ink-3)" }}>Entities</Link>
        {" \u203A "}
        <Link href={`/analytics/players#${pack.slug}`} style={{ color: "var(--ink-3)" }}>{pack.label}</Link>
        {" \u203A "}<span style={{ color: "var(--ink-2)" }}>{name}</span>
      </nav>

      <div style={{ display: "inline-flex", alignItems: "center", gap: 8, background: "var(--paper-tint)", border: "1px solid var(--rule-strong)", borderRadius: 8, padding: "8px 14px", fontSize: 13, color: "var(--ink-2)", margin: "8px 0 26px" }}>
        <span className="dot d-desc" style={{ width: 8, height: 8 }} />
        Descriptive only &mdash; no edge claimed. These are {pack.noun}, not projections.
      </div>

      <header style={{ borderBottom: "1px solid var(--rule-strong)", paddingBottom: 22, marginBottom: 30 }}>
        <div className="overline">{pack.label} &middot; {pack.sport}{asOf ? ` \u00B7 as of ${asOf}` : ""}</div>
        <h1 className="serif" style={{ fontWeight: 500, fontSize: "clamp(2.4rem,5vw,3.4rem)", lineHeight: 1.05, letterSpacing: "-.02em", marginTop: 4 }}>{name}</h1>
        <div style={{ color: "var(--ink-2)", marginTop: 6, fontSize: 15 }}>Descriptive card &middot; conservative measured rates.</div>
      </header>

      <div style={{ display: "flex", flexWrap: "wrap", gap: 40, alignItems: "flex-start" }}>
        <div style={{ flex: "3 1 440px", minWidth: 0 }}>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit,minmax(150px,1fr))", gap: 1, background: "var(--rule)", border: "1px solid var(--rule)", borderRadius: 12 }}>
            {cells.map(([k, v]) => {
              // The big serif tabular-figure tile is a NUMERAL slot; a categorical
              // string (e.g. an NBA team's top_contributor player name) typeset that
              // way reads as a category error and rags/overflows. Render non-numeric
              // values as normal text instead, reserving the numeral style for numbers.
              const isNum = typeof v === "number";
              return (
              <div key={k} style={{ background: "var(--paper-raised)", padding: "18px 16px" }}>
                <div style={{ fontSize: 12, color: "var(--ink-3)", textTransform: "uppercase", letterSpacing: ".06em", fontWeight: 600 }}>{label(k)}</div>
                <div className={isNum ? "serif tnum" : undefined} style={isNum ? { fontWeight: 500, fontSize: "2.1rem", lineHeight: 1, margin: "8px 0 10px" } : { fontWeight: 600, fontSize: "1.05rem", lineHeight: 1.3, margin: "8px 0 10px", color: "var(--ink)" }}>{fmtCell(k, v)}</div>
                {isNum && pctPack && typeof entityPcts?.[k] === "number" ? <PercentileBar pct={entityPcts[k]} nInPack={pctPack.n_in_pack} /> : null}
                <Receipt sourceArtifact={`${REPO}/${pack.manifest}`} asOf={asOf || undefined} verdict="descriptive_only" label="descriptive_only" value={fmtCell(k, v)} />
              </div>
              );
            })}
          </div>

          {pctPack && cells.some(([k, v]) => typeof v === "number" && typeof entityPcts?.[k] === "number") ? (
            // Shown only when >=1 bar rendered above; direction-free by design (no good/bad).
            <div style={{ marginTop: 10, fontSize: 13, color: "var(--ink-3)" }}>
              Bars show where this card sits within its own pack ({pctPack.n_in_pack} {pack.label.toLowerCase()}), by simple rank of the measured value. Higher is only higher -- no quality judgement is implied.{" "}
              <Receipt sourceArtifact={`${REPO}/entity_percentiles.json`} asOf={asOf || undefined} verdict="descriptive_only" label="descriptive_only" />
            </div>
          ) : null}

          <ScoutNote envelope={envelope} />

          {insight?.three_things?.length ? (
            <section style={{ marginTop: 28 }}>
              <h2 className="serif" style={{ fontWeight: 500, fontSize: 20, marginBottom: 10 }}>What stands out</h2>
              <ul style={{ margin: 0, paddingLeft: 20, color: "var(--ink-2)", fontSize: 16, lineHeight: 1.6 }}>
                {insight.three_things.map((t, i) => <li key={i} style={{ marginBottom: 6 }}>{t}</li>)}
              </ul>
            </section>
          ) : null}

          {insight?.context_note ? (
            <section style={{ marginTop: 24, background: "var(--paper-tint)", borderRadius: 10, padding: "16px 18px" }}>
              <div className="overline" style={{ marginBottom: 6 }}>Reading note</div>
              <p style={{ margin: 0, color: "var(--ink-2)", fontSize: 14.5, lineHeight: 1.6 }}>{insight.context_note}</p>
            </section>
          ) : null}
        </div>

        <aside style={{ flex: "1 1 240px" }}>
          {entry.floors ? (
            <div style={box}>
              <h3 className="serif" style={{ fontWeight: 500, fontSize: 20, marginBottom: 10 }}>Floors</h3>
              <div className="mono" style={{ fontSize: 12, color: "var(--ink-3)", lineHeight: 1.55, wordBreak: "break-word" }}>{entry.floors}</div>
            </div>
          ) : null}
          <div style={box}>
            {/* Pack-scoped, not entity-specific: pack.related is a fixed list shared
                by every entity in the pack. "Related analytics" reads honestly;
                "Where this appears" over-promised per-entity placement. */}
            <h3 className="serif" style={{ fontWeight: 500, fontSize: 20, marginBottom: 8 }}>Related analytics</h3>
            {pack.related.map((id) => (
              <Link key={id} href={`/analytics/m/${id}`} style={{ display: "block", padding: "9px 0", borderBottom: "1px solid var(--rule)", fontSize: 14 }}>
                {moduleTitle(id)}
              </Link>
            ))}
            <Link href={`/analytics/players#${pack.slug}`} style={{ display: "block", padding: "9px 0", fontSize: 14 }}>
              All {pack.label} &rarr;
            </Link>
          </div>
        </aside>
      </div>

      <ScoutQuestions questions={questions} heading={`Ask Scout about ${name}`} />
    </div>
  );
}
