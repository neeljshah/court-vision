// AsOfBadge.tsx -- the one way an as-of date is written: "as of YYYY-MM-DD" in the kit's
// mono style, a <time> element for machines, "date not published" (caution) when the
// source carries no date, and a visible STALE suffix when the caller's freshness rule
// says so. Server-safe.
import "./evidence.css";
import { describeDate, type DateKind, type ProvenanceDate } from "@/lib/analytics/artifactProvenance";
import { dayOf } from "./kit";

export interface AsOfBadgeProps {
  asOf?: ProvenanceDate;
  /** source (default): "as of"; snapshot: "generated"; published: "published"; window: "window". */
  kind?: DateKind;
  stale?: boolean;
  className?: string;
}

const WORD: Record<DateKind, string> = { source: "as of", snapshot: "generated", published: "published", window: "window" };

export function asOfText(asOf: ProvenanceDate, kind: DateKind = "source"): { text: string; day: string | null; missing: boolean } {
  if (kind === "window") {
    const long = describeDate(asOf, "window");
    const missing = long === "Date not published.";
    return { text: missing ? "date not published" : `window ${long.replace(/^Observation window /, "")}`, day: null, missing };
  }
  const day = dayOf(typeof asOf === "string" ? asOf : null);
  return day ? { text: `${WORD[kind]} ${day}`, day, missing: false } : { text: "date not published", day: null, missing: true };
}

export function AsOfBadge({ asOf, kind = "source", stale = false, className }: AsOfBadgeProps) {
  const { text, day, missing } = asOfText(asOf, kind);
  const classes = ["ev-asof", missing ? "ev-asof--missing" : "", stale ? "ev-asof--stale" : "", className ?? ""]
    .filter(Boolean).join(" ");
  const title = missing ? "The source artifact carries no as-of date." : describeDate(asOf, kind);
  return (
    <span className={classes} data-kind={kind} title={title}>
      {day ? <time dateTime={day}>{text}</time> : <span>{text}</span>}
      {stale ? <span className="ev-asof__stale">STALE</span> : null}
    </span>
  );
}

export default AsOfBadge;
