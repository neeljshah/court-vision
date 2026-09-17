// NovelStatPanel -- renders one novel_*.json artifact as a short paper: headline,
// what it measures, the formula, a real results table, prior art, declared
// confounds, exclusions, and the receipt. Server component, no client JS.
// The six artifacts do NOT share a results schema (list of sports / list of
// team-seasons / dict of sports each holding a checkpoints array, with nested
// objects and nested arrays inside rows), so the table derives its columns from
// the row keys, flattens one level of nested object, and stringifies nested
// arrays -- never "[object Object]". ASCII source only.
import { asOfDate } from "@/lib/analytics/format";
import { NOVEL_STAT_PANEL_CSS } from "./novelStatPanelStyles";

type Row = Record<string, unknown>;
export interface NovelStat {
  stat_name?: string;
  abbrev?: string;
  headline?: string;
  metric_definition?: string;
  formula?: string;
  prior_art_verdict?: string;
  prior_art_citation?: string;
  declared_confounds?: unknown;
  results?: unknown;
  excluded?: unknown;
  not_buildable?: unknown;
  source_artifacts?: unknown;
  as_of?: unknown;
  is_honest_null?: boolean;
  [k: string]: unknown;
}

const DASH = "—";
const isObj = (v: unknown): v is Row => !!v && typeof v === "object" && !Array.isArray(v);
const label = (k: string) =>
  k
    .split(".")
    .map((p) => p.replace(/_/g, " "))
    .join(" / ");

function fmtNum(n: number): string {
  if (!Number.isFinite(n)) return String(n);
  if (Number.isInteger(n)) return Math.abs(n) >= 10000 ? n.toLocaleString("en-US") : String(n);
  return String(parseFloat(n.toFixed(4)));
}

// Scalar cell text. Nested arrays collapse to a compact "k=v k=v; ..." line
// (e.g. the overreaction bucket lists) so the row stays one table row.
function fmt(v: unknown): string {
  if (v == null) return DASH;
  if (typeof v === "number") return fmtNum(v);
  if (typeof v === "boolean") return v ? "yes" : "no";
  if (Array.isArray(v)) {
    if (!v.length) return DASH;
    return v
      .map((it) =>
        isObj(it)
          ? Object.entries(it)
              .map(([k, x]) => `${k}=${fmt(x)}`)
              .join(" ")
          : fmt(it)
      )
      .join("; ");
  }
  if (isObj(v)) {
    return Object.entries(v)
      .map(([k, x]) => `${k}=${fmt(x)}`)
      .join(" ");
  }
  return String(v);
}

// The observation window an artifact was measured over. Three committed shapes
// (start/end/days/files, first_captured_at/last_captured_at/span_days, and bare
// first/last ISO timestamps), so read all three rather than special-casing a
// module. Returns "" when the artifact carries no window -- nothing is invented.
export function windowText(w: unknown): string {
  if (!isObj(w)) return "";
  const d10 = (v: unknown) => (v == null ? "" : String(v).slice(0, 10));
  const start = d10(w.start ?? w.first_captured_at ?? w.first);
  const end = d10(w.end ?? w.last_captured_at ?? w.last);
  if (!start || !end) return "";
  const days = w.days ?? w.span_days;
  const bits = [
    days == null ? "" : `${fmtNum(Number(days))} days`,
    w.files == null ? "" : `${fmtNum(Number(w.files))} daily files`,
  ].filter(Boolean);
  return `observed ${start} to ${end}${bits.length ? ` (${bits.join(", ")})` : ""}`;
}

// One level of object flattening: {estimator_a: {player_name, delta}} becomes
// two real columns, which is what makes the LBI / half-life tables legible.
// observation_window is the exception -- it collapses to ONE "observed" column
// sitting beside the row's n, so a large count is never read as a long history.
function flatten(row: Row): Row {
  const out: Row = {};
  for (const [k, v] of Object.entries(row)) {
    if (k === "observation_window") out.observed = windowText(v) || fmt(v);
    else if (isObj(v)) for (const [k2, v2] of Object.entries(v)) out[`${k}.${k2}`] = v2;
    else out[k] = v;
  }
  return out;
}

interface Group {
  name?: string;
  meta?: Array<[string, unknown]>;
  rows: Row[];
}

// results is either a list of rows, or a dict keyed by sport whose values each
// hold one array of rows plus scalar summary fields (Market Foresight Premium).
function toGroups(results: unknown): Group[] {
  if (Array.isArray(results)) return results.length ? [{ rows: results.filter(isObj) }] : [];
  if (!isObj(results)) return [];
  const groups: Group[] = [];
  for (const [name, v] of Object.entries(results)) {
    if (!isObj(v)) {
      continue;
    }
    const arrEntry = Object.entries(v).find(([, x]) => Array.isArray(x) && x.length && isObj(x[0]));
    if (arrEntry) {
      groups.push({
        name,
        meta: Object.entries(v).filter(([k, x]) => k !== arrEntry[0] && !Array.isArray(x) && !isObj(x)),
        rows: (arrEntry[1] as unknown[]).filter(isObj),
      });
    } else {
      groups.push({ rows: [{ key: name, ...v }] });
    }
  }
  return groups;
}

function Table({ rows, label: tableLabel }: { rows: Row[]; label: string }) {
  const flat = rows.map(flatten);
  const cols: string[] = [];
  for (const r of flat) for (const k of Object.keys(r)) if (!cols.includes(k)) cols.push(k);
  const numeric = new Set(
    cols.filter((c) => flat.some((r) => typeof r[c] === "number") && !flat.some((r) => typeof r[c] === "string"))
  );
  return (
    <div className="np-scroll" tabIndex={0} role="region" aria-label={`${tableLabel} (scrollable table)`} data-scroll-region>
      <table className="np-table">
        <thead>
          <tr>
            {cols.map((c) => (
              <th key={c} className={numeric.has(c) ? "np-num" : undefined}>
                {label(c)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {flat.map((r, i) => (
            <tr key={i}>
              {cols.map((c) => (
                <td key={c} className={numeric.has(c) ? "np-num tnum" : undefined}>
                  {fmt(r[c])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="np-scroll-hint">Scroll horizontally for all columns</p>
    </div>
  );
}

function ReasonList({ title, items }: { title: string; items: unknown }) {
  const rows = Array.isArray(items) ? items.filter(isObj) : [];
  if (!rows.length) return null;
  return (
    <div style={{ marginTop: 14 }}>
      <div className="overline" style={{ marginBottom: 6 }}>
        {title}
      </div>
      <ul className="np-reasons">
        {rows.map((r, i) => (
          <li key={i}>
            <span className="mono">{fmt(r.sport ?? r.key ?? r.name)}</span> {DASH} {fmt(r.reason)}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function NovelStatPanel({ stat }: { stat: NovelStat }) {
  const groups = toGroups(stat.results);
  const confounds = Array.isArray(stat.declared_confounds)
    ? (stat.declared_confounds as unknown[]).map((c) => String(c))
    : stat.declared_confounds
      ? [String(stat.declared_confounds)]
      : [];
  const sources = Array.isArray(stat.source_artifacts) ? (stat.source_artifacts as unknown[]).map(String) : [];
  const asOfPairs = isObj(stat.as_of) ? Object.entries(stat.as_of) : [];
  const asOfStr = typeof stat.as_of === "string" ? asOfDate(stat.as_of) || stat.as_of : "";
  const win = windowText(stat.observation_window);

  return (
    <section className="np">
      <div className="np-top">
        <h2 className="serif">
          {stat.stat_name || "Novel stat"}
          {stat.abbrev ? <span className="np-abbrev mono">{stat.abbrev}</span> : null}
        </h2>
        {stat.is_honest_null ? <span className="np-null mono">HONEST NULL</span> : null}
      </div>
      {stat.headline ? <p className="np-headline">{stat.headline}</p> : null}
      {win ? (
        <p className="np-window mono">
          {typeof stat.window_caption === "string" && stat.window_caption
            ? stat.window_caption
            : `Measured over a single capture window -- ${win}. Every count below is dense sampling inside that window, not a long history.`}
        </p>
      ) : null}

      {stat.metric_definition ? (
        <div className="np-sec">
          <div className="overline">What it measures</div>
          <p>{stat.metric_definition}</p>
        </div>
      ) : null}

      {stat.formula ? (
        <div className="np-sec">
          <div className="overline">The formula</div>
          <pre className="np-formula mono">{stat.formula}</pre>
        </div>
      ) : null}

      {groups.length ? (
        <div className="np-sec">
          <div className="overline">The results</div>
          {groups.map((g, i) => (
            <div key={i} style={{ marginTop: i ? 18 : 10 }}>
              {g.name ? <div className="np-gname mono">{g.name}</div> : null}
              {g.meta?.length ? (
                <div className="np-meta mono">
                  {g.meta.map(([k, v]) => (
                    <span key={k}>
                      {label(k)} <b>{fmt(v)}</b>
                    </span>
                  ))}
                </div>
              ) : null}
              <Table rows={g.rows} label={g.name ? `${g.name} results` : `Published results ${i + 1}`} />
            </div>
          ))}
        </div>
      ) : null}

      {stat.prior_art_verdict || stat.prior_art_citation ? (
        <div className="np-sec">
          <div className="np-pa-top">
            <div className="overline">Prior art</div>
            {stat.prior_art_verdict ? <span className="np-verdict mono">{String(stat.prior_art_verdict)}</span> : null}
          </div>
          <p className="np-pa-lede">We searched for prior work before claiming anything. Here is what exists:</p>
          {stat.prior_art_citation ? <p>{String(stat.prior_art_citation)}</p> : null}
        </div>
      ) : null}

      {confounds.length ? (
        <div className="np-confounds">
          <div className="overline" style={{ color: "var(--signal-ink)" }}>
            Declared confounds
          </div>
          <ul>
            {confounds.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <ReasonList title="Excluded" items={stat.excluded} />
      <ReasonList title="Not buildable" items={stat.not_buildable} />

      <div className="np-receipt mono">
        {sources.map((s) => (
          <div key={s}>{s}</div>
        ))}
        {asOfStr ? <div>as_of {asOfStr}</div> : null}
        {win ? <div>observation window: {win}</div> : null}
        {asOfPairs.map(([k, v]) => (
          <div key={k}>
            as_of {label(k)}: {fmt(v)}
          </div>
        ))}
        <div>descriptive_only</div>
      </div>

      <style dangerouslySetInnerHTML={{ __html: NOVEL_STAT_PANEL_CSS }} />
    </section>
  );
}

export default NovelStatPanel;
