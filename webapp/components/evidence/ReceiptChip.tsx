// ReceiptChip.tsx -- THE receipt: source path + as-of date + verification status, one
// visual style on every page of both halves and in both themes (evidence.css). It is a
// link to the committed artifact on GitHub under master, so it is keyboard focusable by
// nature; the full source path, date and status are in its title and accessible name.
// Server-safe (no hooks), so server and client trees can both mount it.
import "./evidence.css";
import { basename, dayOf, normalizeRepoPath, receiptHref, type ReceiptStatus } from "./kit";

export type ReceiptDateKind = "source" | "snapshot" | "published";

export interface ReceiptChipProps {
  /** Repo-relative artifact path (a bare published artifact name also resolves). */
  source: string;
  /** ISO day or timestamp; null/absent renders validation_pending. */
  asOf?: string | null;
  /** How the date was produced: a source as-of (default), an artifact generation stamp, or a publish date. */
  kind?: ReceiptDateKind;
  /** The packet's verification vocabulary; defaults to descriptive_only, or validation_pending without a date. */
  status?: ReceiptStatus;
  /** Override the link target (a pinned commit, for example). */
  href?: string | null;
  /** Extra provenance for the title, e.g. how a count was derived. */
  note?: string;
  /** Glyph only (next to a FigureValue or an AsOfBadge); source, date and status stay in the title and accessible name. */
  compact?: boolean;
  className?: string;
}

const DATE_WORD: Record<ReceiptDateKind, string> = { source: "as of", snapshot: "generated", published: "published" };

export function receiptText(props: ReceiptChipProps) {
  const path = normalizeRepoPath(props.source);
  const day = dayOf(props.asOf);
  const status: ReceiptStatus = day ? props.status ?? "descriptive_only" : "validation_pending";
  const dateText = day ? `${DATE_WORD[props.kind ?? "source"]} ${day}` : "date not published";
  const href = receiptHref(props.source, props.href);
  const title = `Receipt. Source ${path}${props.note ? ` (${props.note})` : ""}. ${dateText}. ` +
    `Verification: ${status}.${href ? " Opens the committed artifact." : " Artifact not published on this site."}`;
  const label = `Receipt: ${path}, ${dateText}, ${status}`;
  return { path, day, status, dateText, href, title, label };
}

export function ReceiptChip(props: ReceiptChipProps) {
  const { path, status, dateText, href, title, label } = receiptText(props);
  const className = ["ev-chip", href ? "" : "ev-chip--nolink", props.className ?? ""].filter(Boolean).join(" ");
  const body = (
    <>
      <span className="ev-chip__glyph" aria-hidden="true">R</span>
      {props.compact ? null : (
        <>
          <span className="ev-chip__src">{href ? basename(path) : `${path} (not published)`}</span>
          <span className="ev-chip__asof">{dateText}</span>
          <span className="ev-chip__status">{status}</span>
        </>
      )}
    </>
  );
  if (!href) {
    return (
      <span className={className} data-status={status} title={title} aria-label={label} role="note">
        {body}
      </span>
    );
  }
  const external = /^https?:\/\//.test(href);
  return (
    <a
      className={className}
      data-status={status}
      href={href}
      title={title}
      aria-label={label}
      {...(external ? { target: "_blank", rel: "noreferrer" } : {})}
    >
      {body}
    </a>
  );
}

export default ReceiptChip;
