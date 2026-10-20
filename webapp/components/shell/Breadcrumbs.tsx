"use client";
// components/shell/Breadcrumbs.tsx -- Home > Section > Page from the pathname
// (rules in nav.ts). Renders nothing on the home page and on a section root.
import Link from "next/link";
import { usePathname } from "next/navigation";
import { crumbsFor } from "./nav";
import s from "./shell.module.css";

export function Breadcrumbs({ path }: { path?: string }) {
  const pathname = usePathname();
  const crumbs = crumbsFor(path ?? pathname);
  if (!crumbs.length) return null;
  return (
    <nav aria-label="Breadcrumb" className={s.crumbs}>
      <ol>
        {crumbs.map((c, i) => {
          const last = i === crumbs.length - 1;
          return (
            <li key={`${i}-${c.label}`}>
              {c.href && !last ? (
                <Link href={c.href} prefetch={false}>{c.label}</Link>
              ) : (
                <span aria-current={last ? "page" : undefined}>{c.label}</span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

export default Breadcrumbs;
