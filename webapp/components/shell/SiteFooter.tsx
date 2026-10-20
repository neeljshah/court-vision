// components/shell/SiteFooter.tsx -- the ONE site footer: evidence links, contact, and
// the snapshot as-of line. Server-safe (no hooks); the layouts pass the dates in.
import Link from "next/link";
import { CONTACT_EMAIL, GITHUB, PORTFOLIO, githubDoc } from "./nav";
import { snapshotLine, type SnapshotDates } from "./snapshot.server";
import s from "./shell.module.css";

const EVIDENCE_LINKS: Array<{ label: string; href: string; external?: boolean }> = [
  { label: "Evidence packet", href: githubDoc("docs/JOB_EVIDENCE_PACKET.md"), external: true },
  { label: "Receipts", href: "/receipts/" },
  { label: "Reproduce", href: githubDoc("REPRODUCE.md"), external: true },
  { label: "Retraction record", href: "/evidence/retractions/" },
  { label: "Model cards", href: githubDoc("docs/evidence/model_cards/INDEX.json"), external: true },
  { label: "About", href: "/about/" },
];

export function SiteFooter({ dates }: { dates: SnapshotDates }) {
  const asOf = snapshotLine(dates);
  return (
    <footer className={s.footer}>
      <div className={s.footInner}>
        <p>
          CourtVision is a calibrated sports forecaster that publishes its own scorecard against the
          market. Paper units only; it is not a betting product.
        </p>
        <nav aria-label="Footer">
          <ul>
            {EVIDENCE_LINKS.map((l) => (
              <li key={l.label}>
                {l.external ? <a href={l.href}>{l.label}</a> : <Link href={l.href} prefetch={false}>{l.label}</Link>}
              </li>
            ))}
          </ul>
        </nav>
        <ul aria-label="Contact">
          <li>Neel Shah</li>
          <li><a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a></li>
          <li><a href={GITHUB}>GitHub</a></li>
          <li><a href={PORTFOLIO}>Portfolio</a></li>
        </ul>
        <p>{asOf ? `Static snapshot: ${asOf}.` : "Static snapshot; no live data."}</p>
      </div>
    </footer>
  );
}

export default SiteFooter;
