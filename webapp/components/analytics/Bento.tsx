// Bento -- importance-weighted flagship grid for the analytics home (DESIGN Sec. 9,
// stolen from Direction B, rendered in the Reading Room system). Data-driven spans
// (2x2 flagship / 2x1 featured / 1x1 standard) keep a growing catalog scannable.
// Server component: composes the client Receipt island + the presentational
// VerdictDot. Whole cell is a link via a stretched-link overlay so the independent
// Receipt button stays clickable above it (no invalid <button>-inside-<a> nesting).
// Null cells are at EQUAL prominence -- never dimmed or reddened; the graveyard is
// the brand. Its own scoped <style> gives hover-lift + responsive spans that inline
// styles cannot. ASCII only.
import { VerdictDot, type Verdict } from "./VerdictDot";
import { Receipt, type ReceiptData } from "./Receipt";

export type BentoWeight = "2x2" | "2x1" | "1x1";

export interface BentoCell {
  href: string;
  category: string; // overline, e.g. "NBA . Fatigue"
  title: string;
  summary?: string;
  stat: string; // headline number, verbatim from its artifact
  statUnit?: string; // e.g. "pts"
  verdict: Verdict;
  receipt: ReceiptData;
  weight: BentoWeight;
  motif?: boolean; // draw the amber rising-line brand mark (2x2 flagship)
}

const CSS = `
.a-bento{display:grid;grid-template-columns:repeat(4,1fr);grid-auto-rows:158px;gap:16px}
.a-cell{position:relative;display:flex;flex-direction:column;padding:18px 18px 16px;
  background:var(--paper-raised);border:1px solid var(--rule);border-radius:var(--radius-card);
  box-shadow:var(--shadow-card);overflow:hidden;
  transition:box-shadow var(--dur-base) var(--ease-ui),border-color var(--dur-base) var(--ease-ui),transform var(--dur-base) var(--ease-ui)}
.a-cell:hover,.a-cell:focus-within{box-shadow:var(--shadow-raise);border-color:var(--accent);transform:translateY(-2px)}
.a-cell.w-2x2{grid-column:span 2;grid-row:span 2}
.a-cell.w-2x1{grid-column:span 2}
.a-vd{position:absolute;right:16px;top:16px;z-index:2}
.a-cat{margin-bottom:auto}
.a-title{display:block;margin-top:6px;font-family:var(--font-sans);font-weight:600;
  font-size:16px;line-height:1.28;color:var(--ink);letter-spacing:0;max-width:calc(100% - 18px)}
.a-cell.w-2x2 .a-title{font-size:21px;line-height:1.22;margin-top:8px}
.a-title:hover{text-decoration:none;color:var(--ink)}
.a-title::after{content:"";position:absolute;inset:0;z-index:1}
.a-sum{margin-top:5px;font-size:13px;line-height:1.42;color:var(--ink-2);max-width:44ch}
.a-cell.w-2x2 .a-sum{font-size:14.5px;margin-top:7px}
.a-spacer{flex:1 1 auto;min-height:8px}
.a-motif{margin:10px 0 2px;width:100%;max-width:220px;height:44px;opacity:.9}
.a-statrow{display:flex;align-items:flex-end;justify-content:space-between;gap:12px;margin-top:12px}
.a-stat{font-family:var(--font-display);font-weight:500;font-size:2rem;line-height:1;
  color:var(--ink);font-feature-settings:'tnum' 1;letter-spacing:-.01em}
.a-cell.w-2x2 .a-stat{font-size:3rem}
.a-stat .u{font-family:var(--font-sans);font-weight:500;font-size:.9rem;color:var(--ink-3);margin-left:5px}
.a-rcpt{position:relative;z-index:2;flex:0 0 auto}
@media(max-width:900px){.a-bento{grid-template-columns:repeat(2,1fr)}.a-cell.w-2x2,.a-cell.w-2x1{grid-column:span 2}}
@media(max-width:560px){.a-bento{grid-template-columns:1fr;grid-auto-rows:auto}
  .a-cell,.a-cell.w-2x2,.a-cell.w-2x1{grid-column:span 1;grid-row:auto;min-height:150px}}
`;

// The amber rising-line -- the logo motif, decorative (brand mark, NOT a data
// series). Same arc the Glass Court hero draws, quieted for a card corner.
function Motif() {
  return (
    <svg className="a-motif" viewBox="0 0 220 44" fill="none" aria-hidden="true">
      <path
        d="M4 40 C60 40 118 30 150 16 C176 5 202 5 216 5"
        stroke="var(--signal)"
        strokeWidth={2.4}
        strokeLinecap="round"
      />
      <circle cx={216} cy={5} r={3.4} fill="var(--signal)" />
    </svg>
  );
}

export function Bento({ cells }: { cells: BentoCell[] }) {
  return (
    <>
      <style>{CSS}</style>
      <div className="a-bento">
        {cells.map((c) => (
          <div key={c.href + c.title} className={`a-cell w-${c.weight}`}>
            <span className="a-vd">
              <VerdictDot verdict={c.verdict} size={c.weight === "2x2" ? 9 : 7} />
            </span>
            <span className="a-cat overline">{c.category}</span>
            <a className="a-title" href={c.href}>
              {c.title}
            </a>
            {c.summary ? <span className="a-sum">{c.summary}</span> : null}
            {c.motif ? <Motif /> : <span className="a-spacer" />}
            <div className="a-statrow">
              <span className="a-stat">
                {c.stat}
                {c.statUnit ? <span className="u">{c.statUnit}</span> : null}
              </span>
              <span className="a-rcpt">
                <Receipt {...c.receipt} />
              </span>
            </div>
          </div>
        ))}
      </div>
    </>
  );
}

export default Bento;
