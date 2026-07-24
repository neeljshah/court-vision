// LoopDiagram -- the self-improving system as a living pipeline (NIGHT_PLAN
// elevated goal: /analytics/the-loop). Propose -> leak-free gate -> verdict ->
// graveyard-or-verified. CSS-ONLY motion (no new deps beyond three-on-home): the
// rails "flow" and a few tokens ride them; the diagram is fully legible frozen, so
// the global reduced-motion rule in analytics.css safely stills it. Server
// component -- the numbers are passed in from committed artifacts by the page.
import type { CSSProperties } from "react";

export interface LoopStats {
  families: number; // fwd_claim_scoreboard: n_families
  verified: number; // verified families (confirmed)
  graveyard: number; // nulls + not-testable + retracted (nulls_or_worse)
  provisional: number; // still under test
  flips: number; // families that changed their own verdict
}

const CSS = `
.lp{position:relative;margin:8px 0 0}
.lp-row{display:flex;align-items:stretch;gap:0}
.lp-node{flex:1 1 0;min-width:0;background:var(--paper-raised);border:1px solid var(--rule);
  border-radius:var(--radius-card);box-shadow:var(--shadow-card);padding:16px 16px 18px;
  display:flex;flex-direction:column}
.lp-k{font-weight:700;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--ink-3)}
.lp-h{font-family:var(--font-display);font-weight:500;font-size:19px;letter-spacing:-.01em;
  color:var(--ink);margin:3px 0 3px}
.lp-sub{font-size:12px;color:var(--ink-3);line-height:1.4}
.lp-stat{font-family:var(--font-display);font-weight:500;font-size:1.65rem;margin-top:12px;
  color:var(--ink);font-feature-settings:'tnum' 1;line-height:1}
.lp-stat u{font-style:normal;text-decoration:none;font-size:.8rem;color:var(--ink-3);margin-left:4px}
.lp-rail{flex:0 0 clamp(20px,3.5vw,52px);align-self:center;position:relative;height:2px;
  background:repeating-linear-gradient(90deg,var(--rule-strong) 0 5px,transparent 5px 11px);
  animation:lp-flow .9s linear infinite}
.lp-token{position:absolute;top:50%;width:7px;height:7px;border-radius:50%;margin-top:-3.5px;
  background:var(--ink-3);box-shadow:0 0 0 3px var(--paper);animation:lp-ride 2.6s var(--ease-soft) infinite}
.lp-emit{position:absolute;left:0;top:50%;width:9px;height:9px;margin:-4.5px 0 0 -4.5px;border-radius:50%;
  background:var(--signal);animation:lp-pulse 1.9s ease-out infinite}
.lp-brace{flex:0 0 clamp(30px,4.5vw,60px);position:relative;align-self:stretch}
.lp-brace i{position:absolute;display:block}
.lp-stem{top:50%;left:0;width:44%;height:2px;margin-top:-1px;
  background:repeating-linear-gradient(90deg,var(--rule-strong) 0 5px,transparent 5px 11px);animation:lp-flow .9s linear infinite}
.lp-vbar{left:44%;top:24%;bottom:24%;width:2px;
  background:repeating-linear-gradient(0deg,var(--rule-strong) 0 5px,transparent 5px 11px)}
.lp-arm{left:44%;right:0;height:2px;overflow:visible}
.lp-up{top:24%;background:repeating-linear-gradient(90deg,var(--confirmed) 0 5px,transparent 5px 11px);
  animation:lp-flow .9s linear infinite}
.lp-dn{bottom:24%;background:repeating-linear-gradient(90deg,var(--null) 0 5px,transparent 5px 11px);
  animation:lp-flow .9s linear infinite}
.lp-up .lp-token{background:var(--confirmed);animation-duration:2.9s}
.lp-dn .lp-token{background:var(--null);animation-duration:3.2s;animation-delay:.6s}
.lp-out{flex:1.05 1 0;display:flex;flex-direction:column;justify-content:space-between;gap:16px}
.lp-outbox{background:var(--paper-raised);border:1px solid var(--rule);border-left-width:3px;
  border-radius:var(--radius-card);box-shadow:var(--shadow-card);padding:13px 16px}
.lp-outbox.v{border-left-color:var(--confirmed)}
.lp-outbox.g{border-left-color:var(--null)}
.lp-outlbl{font-weight:700;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--ink-3)}
.lp-outnum{font-family:var(--font-display);font-weight:500;font-size:1.9rem;font-feature-settings:'tnum' 1;
  line-height:1;margin:4px 0 2px;color:var(--ink)}
.lp-outsub{font-size:11.5px;color:var(--ink-3);line-height:1.35}
.lp-legend{margin-top:16px;font-size:13px;color:var(--ink-2);display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.lp-legend b{color:var(--ink);font-weight:600;font-feature-settings:'tnum' 1}
@keyframes lp-flow{from{background-position:0 0}to{background-position:11px 0}}
@keyframes lp-ride{0%{left:-4px;opacity:0}12%{opacity:1}86%{opacity:1}100%{left:calc(100% - 3px);opacity:0}}
@keyframes lp-pulse{0%{transform:scale(.5);opacity:.6}100%{transform:scale(2.2);opacity:0}}
@media(max-width:820px){
  .lp-row{flex-direction:column;align-items:stretch;gap:10px}
  .lp-rail{flex:0 0 22px;width:2px;height:22px;align-self:center;
    background:repeating-linear-gradient(0deg,var(--rule-strong) 0 5px,transparent 5px 11px);animation:lp-flowv .9s linear infinite}
  .lp-token,.lp-emit,.lp-brace{display:none}
  .lp-out{flex:none}
  @keyframes lp-flowv{from{background-position:0 0}to{background-position:0 11px}}
}`;

function Node({ k, h, sub, stat, unit }: { k: string; h: string; sub: string; stat: string; unit?: string }) {
  return (
    <div className="lp-node">
      <span className="lp-k">{k}</span>
      <span className="lp-h">{h}</span>
      <span className="lp-sub">{sub}</span>
      <span className="lp-stat">
        {stat}
        {unit ? <u>{unit}</u> : null}
      </span>
    </div>
  );
}

export function LoopDiagram({ stats }: { stats: LoopStats }) {
  const n = (v: number) => v.toLocaleString("en-US");
  return (
    <div className="lp" role="img" aria-label={`Self-grading pipeline: ${stats.families} candidate families proposed, run through a leak-free gate, ${stats.verified} verified and ${stats.graveyard} kept in the graveyard`}>
      <div className="lp-row">
        <Node k="01 / Propose" h="Discovery" sub="candidate signals, no LLM" stat={n(stats.families)} unit="families" />
        <span className="lp-rail" aria-hidden>
          <span className="lp-emit" />
          <span className="lp-token" />
        </span>
        <Node k="02 / Leak-free gate" h="Walk-forward" sub="2+ corpora, truncation-invariant" stat="" />
        <span className="lp-rail" aria-hidden>
          <span className="lp-token" style={{ animationDelay: "1.1s" } as CSSProperties} />
        </span>
        <Node k="03 / Verdict" h="Self-graded" sub="kept in the ledger, counted" stat="" />
        <div className="lp-brace" aria-hidden>
          <i className="lp-stem" />
          <i className="lp-vbar" />
          <i className="lp-arm lp-up">
            <span className="lp-token" />
          </i>
          <i className="lp-arm lp-dn">
            <span className="lp-token" />
          </i>
        </div>
        <div className="lp-out">
          <div className="lp-outbox v">
            <span className="lp-outlbl">Verified</span>
            <div className="lp-outnum">{n(stats.verified)}</div>
            <span className="lp-outsub">confirmed families</span>
          </div>
          <div className="lp-outbox g">
            <span className="lp-outlbl">Graveyard</span>
            <div className="lp-outnum">{n(stats.graveyard)}</div>
            <span className="lp-outsub">null, not-testable, retracted &mdash; kept, not hidden</span>
          </div>
        </div>
      </div>
      <p className="lp-legend">
        <span className="dot d-prov" aria-hidden />
        <span>
          <b>{stats.flips}</b> families changed their own verdict on new evidence; <b>{stats.provisional}</b> are still provisional.
        </span>
      </p>
      {/* eslint-disable-next-line react/no-danger */}
      <style dangerouslySetInnerHTML={{ __html: CSS }} />
    </div>
  );
}

export default LoopDiagram;
