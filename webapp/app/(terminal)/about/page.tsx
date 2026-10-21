// app/(terminal)/about/page.tsx -- About: what CourtVision is, how it is built, what it
// is not, methods links, and the author with contact. Calibration language only (see
// .claude/rules/no-edge-claims.md). The commit figures are quoted from CONTRIBUTING.md
// with its measurement date. ASCII only.
import Link from "next/link";
import { CONTACT_EMAIL, GITHUB, PORTFOLIO, githubDoc } from "@/components/shell/nav";
import { Term } from "@/components/evidence";
import type { Metadata } from "next";
import { pageMeta } from "@/lib/seo/meta";

export const metadata: Metadata = pageMeta("/about/", {
  title: "About",
  description:
    "What CourtVision is, how it was built, what it is not, and how to contact its author.",
});

const NOT_THIS = [
  "It is not a betting product and has no order path. Every desk figure is in paper units.",
  "It does not price games better than the market. Pregame, the model trails the devigged closing price, or matches it only where the sample is too small to tell.",
  "The forward paper series has no calibration verdict yet. The receipts say why.",
  "Pages show a dated static snapshot, not live data.",
];

const H2 = "text-lg font-semibold text-foreground";
const P = "text-sm leading-relaxed text-muted-foreground";
const A = "text-foreground underline underline-offset-2";

export default function AboutPage() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-8 px-4 py-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">About CourtVision</h1>
        <p className={`mt-2 ${P}`}>
          A calibrated sports forecaster that publishes its own scorecard against the market,
          including losses, nulls and retractions. Its headline finding: the pregame model does not
          price games better than the market. It trails the{" "}
          <Term id="devigged-close">devigged closing price</Term> on MLB moneyline and soccer
          over/under 2.5, and matches it on NBA moneyline only where the sample is too small to tell.
          Each headline figure names its source artifact and as-of date, and the evidence packet is the truth source.
        </p>
      </header>

      <section aria-labelledby="what">
        <h2 id="what" className={H2}>What it is</h2>
        <p className={`mt-2 ${P}`}>
          CourtVision makes probability forecasts for NBA, MLB, soccer and tennis games, before
          and during play. It scores them out of sample with the{" "}
          <Term id="brier">Brier score</Term>: against the devigged closing price before a game,
          and against the live market during it. The goal is calibration: a 60% forecast should
          come true about 60% of the time. Every published number carries an as-of date, a
          source file and a verdict word taken from the{" "}
          <a href={githubDoc("docs/JOB_EVIDENCE_PACKET.md")} className={A}>evidence packet</a>.
        </p>
      </section>

      <section aria-labelledby="how">
        <h2 id="how" className={H2}>How it is built</h2>
        <p className={`mt-2 ${P}`}>
          One person directed coding agents to build it. The owner set the goals, the
          validation rules and the acceptance bars; agents wrote most of the code, tests and
          documentation. As measured on 2026-10-20, 24.8% of the 6,515 public commits carry an
          agent co-author trailer, and the true agent share is higher (
          <a href={githubDoc("CONTRIBUTING.md")} className={A}>CONTRIBUTING.md</a>). Results that
          failed later checks were withdrawn in public and are listed on the{" "}
          <Link href="/evidence/retractions/" prefetch={false} className={A}>retraction record</Link>.
        </p>
      </section>

      <section aria-labelledby="not" className="rounded-md border border-border bg-card p-4">
        <h2 id="not" className={H2}>What this is not</h2>
        <ul className={`mt-2 list-disc space-y-1 pl-5 ${P}`}>
          {NOT_THIS.map((t) => <li key={t}>{t}</li>)}
        </ul>
      </section>

      <section aria-labelledby="methods">
        <h2 id="methods" className={H2}>Methods</h2>
        <ul className={`mt-2 list-disc space-y-1 pl-5 ${P}`}>
          <li><Link href="/how-it-works/" prefetch={false} className={A}>How it works</Link>: from raw data to a calibrated forecast.</li>
          <li><Link href="/methodology/" prefetch={false} className={A}>Methodology</Link>: how each number is checked and labelled.</li>
          <li><a href={githubDoc("docs/GLOSSARY.md")} className={A}>Glossary</a>: the terms used on this site.</li>
          <li><a href={githubDoc("REPRODUCE.md")} className={A}>Reproduce</a>: commands to re-run the checks.</li>
        </ul>
      </section>

      <section aria-labelledby="author">
        <h2 id="author" className={H2}>Author and contact</h2>
        <p className={`mt-2 ${P}`}>
          Built by Neel Shah, who has three years of data-science coursework at the University of
          Iowa.
        </p>
        <ul className={`mt-2 space-y-1 ${P}`}>
          <li>Email: <a href={`mailto:${CONTACT_EMAIL}`} className={A}>{CONTACT_EMAIL}</a></li>
          <li>GitHub: <a href={GITHUB} className={A}>{GITHUB.replace("https://", "")}</a></li>
          <li>Portfolio: <a href={PORTFOLIO} className={A}>{PORTFOLIO.replace("https://", "").replace(/\/$/, "")}</a></li>
        </ul>
      </section>
    </div>
  );
}
