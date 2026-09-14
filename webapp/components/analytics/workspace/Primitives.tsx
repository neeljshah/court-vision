import type { ReactNode } from "react";
import { ArrowUpRight, FileJson } from "lucide-react";
import { sourceUrl } from "@/lib/analytics/dashboardTypes";

export function Panel({ title, eyebrow, children, source, className = "" }: { title: string; eyebrow?: string; children: ReactNode; source?: string; className?: string }) {
  return <section className={`cv-panel ${className}`}><header className="cv-panel-head"><div>{eyebrow && <p className="cv-eyebrow">{eyebrow}</p>}<h2>{title}</h2></div>{source && <a className="cv-source" href={sourceUrl(source)} target="_blank" rel="noreferrer" aria-label={`View ${title} source JSON`}><FileJson size={14} /> Source <ArrowUpRight size={13} /></a>}</header>{children}</section>;
}
export function Empty({ children }: { children: ReactNode }) { return <div className="cv-empty">{children}</div>; }
export function Pagination({ page, total, size = 12, onChange }: { page: number; total: number; size?: number; onChange: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(total / size));
  return <div className="cv-pagination"><span>{total ? `${page * size + 1}-${Math.min(total, (page + 1) * size)} of ${total}` : "0 results"}</span><div><button disabled={page === 0} onClick={() => onChange(page - 1)}>Previous</button><span>Page {page + 1} / {pages}</span><button disabled={page + 1 >= pages} onClick={() => onChange(page + 1)}>Next</button></div></div>;
}
