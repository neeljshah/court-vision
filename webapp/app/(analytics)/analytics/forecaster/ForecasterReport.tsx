import type { CSSProperties } from "react";
import Link from "next/link";
import { VerdictDot } from "@/components/analytics/VerdictDot";
import type { ForecasterArm, ForecasterArms } from "./forecaster.server";

const sec: CSSProperties = { marginTop: 56 };
const eye: CSSProperties = { color: "var(--ink-3)", fontSize: 11, fontWeight: 700, letterSpacing: "0.13em", marginBottom: 10, textTransform: "uppercase" };
const h2: CSSProperties = { color: "var(--ink)", fontFamily: "var(--font-display)", fontSize: 32, fontWeight: 500, letterSpacing: "-0.01em" };
const lede: CSSProperties = { color: "var(--ink-2)", fontSize: 16, lineHeight: 1.62, marginTop: 12, maxWidth: "62ch" };
const th: CSSProperties = { borderBottom: "1px solid var(--rule-strong)", color: "var(--ink-3)", fontSize: 11, letterSpacing: "0.06em", padding: "8px 12px", textAlign: "left", textTransform: "uppercase", whiteSpace: "nowrap" };
const td: CSSProperties = { borderBottom: "1px solid var(--rule)", color: "var(--ink-2)", fontSize: 13.5, fontVariantNumeric: "tabular-nums", padding: "9px 12px", whiteSpace: "nowrap" };

function display(value: number | string | null | undefined, digits = 3): string {
  if (typeof value === "number") return value.toFixed(digits);
  if (typeof value === "string" && value.trim()) return value;
  return "not published";
}

function artifactHref(path: string): string {
  const base = (process.env.NEXT_PUBLIC_BASE_PATH || "").replace(/\/$/, "");
  return `${base}/data/forecaster/forecaster-arms.json#/${path}`;
}

function ReceiptLink({ path }: { path: string }) {
  return <a className="mono" href={artifactHref(path)} style={{ color: "var(--ink-3)", fontSize: 11.5 }}>Receipt: #{path}</a>;
}

function ArmComparison({ arm, index }: { arm: ForecasterArm; index: number }) {
  return (
    <article style={{ background: "var(--paper-raised)", border: "1px solid var(--rule)", borderRadius: 12, padding: "20px" }}>
      <div style={{ alignItems: "center", display: "flex", gap: 8 }}>
        <VerdictDot verdict="descriptive_only" />
        <strong style={{ color: "var(--ink)" }}>{arm.sport || "not published"}</strong>
      </div>
      <p style={{ ...lede, fontSize: 14, marginTop: 10 }}>
        Static Brier {display(arm.static_brier)}; score-only Brier {display(arm.score_only_brier)}; combined Brier {display(arm.combined_brier)}.
      </p>
      <p className="mono" style={{ color: "var(--ink-3)", fontSize: 11.5, marginTop: 10 }}>
        n={display(arm.n, 0)} / observed {display(arm.observed_on, 0)}
      </p>
      <ReceiptLink path={`arms/${index}`} />
    </article>
  );
}

export function ForecasterReport({ data }: { data: ForecasterArms }) {
  return (
    <div className="wrap" style={{ paddingBottom: 48, paddingTop: 56 }}>
      <header>
        <div style={eye}>The Forecaster</div>
        <h1 className="serif" style={{ color: "var(--ink)", fontSize: "clamp(2.6rem,5.5vw,4rem)", fontWeight: 500, letterSpacing: "-0.02em", lineHeight: 1.05 }}>
          A calibrated engine, measured against itself.
        </h1>
        <section aria-label="Reading trail" style={{ borderTop: "1px solid var(--rule)", color: "var(--ink-2)", fontSize: 14, margin: "18px 0 26px", paddingTop: 14 }}>
          <p className="overline">Reading trail</p>
          <p style={{ marginTop: 6 }}>Read first: <Link href="/analytics/calibration/">Calibration reliability</Link></p>
          <p style={{ marginTop: 4 }}>Next: <Link href="/analytics/state-reliability/">State reliability</Link></p>
        </section>
        <p style={{ ...lede, fontSize: 18 }}>
          Published calibration checks for pregame and in-game forecasts. The in-game comparison separates the recorded state contribution from the rating-prior contribution.
        </p>
      </header>

      <section style={sec}>
        <div style={eye}>Published in-game calibration comparison</div>
        <h2 style={h2}>{data.measurement?.identity || "not published"}</h2>
        <p style={lede}>Each result is read from one public artifact. Its original analysis paths are retained in that artifact as provenance text, not as reader links.</p>
        {data.arms.length ? (
          <div style={{ display: "grid", gap: 12, gridTemplateColumns: "repeat(auto-fit,minmax(260px,1fr))", marginTop: 24 }}>
            {data.arms.map((arm, index) => <ArmComparison arm={arm} index={index} key={arm.sport || index} />)}
          </div>
        ) : <p style={lede}>not published</p>}
      </section>

      <section style={sec}>
        <div style={eye}>Three-arm measurement</div>
        <h2 style={h2}>Published state-transition summary.</h2>
        <div aria-label="In-game conditioning measurements" data-scroll-region role="region" style={{ marginTop: 20, overflowX: "auto" }}>
          <table style={{ borderCollapse: "collapse", minWidth: 720, width: "100%" }}>
            <thead><tr><th scope="col" style={th}>Sport</th><th scope="col" style={th}>Static</th><th scope="col" style={th}>Score-only</th><th scope="col" style={th}>Combined</th><th scope="col" style={th}>Mechanical share</th><th scope="col" style={th}>Model-prior share</th><th scope="col" style={th}>Receipt</th></tr></thead>
            <tbody>{data.arms.map((arm, index) => <tr key={`${arm.sport}-${index}`}><th scope="row" style={{ ...td, color: "var(--ink)", fontWeight: 600 }}>{arm.sport || "not published"}</th><td style={td}>{display(arm.static_brier)}</td><td style={td}>{display(arm.score_only_brier)}</td><td style={td}>{display(arm.combined_brier)}</td><td style={td}>{display(arm.mechanical_share, 0)}</td><td style={td}>{display(arm.model_prior_share, 0)}</td><td style={td}><ReceiptLink path={`arms/${index}`} /></td></tr>)}</tbody>
          </table>
        </div>
        <p className="mono" style={{ color: "var(--ink-3)", fontSize: 11.5, marginTop: 12 }}>As of {display(data.as_of, 0)}. Each displayed field links to the public artifact and its JSON field path.</p>
      </section>
    </div>
  );
}
