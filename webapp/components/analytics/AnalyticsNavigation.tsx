"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

export function AnalyticsNavigation({ links }: { links: { href: string; label: string }[] }) {
  const raw = usePathname() || "";
  const path = raw.replace(/^\/court-vision(?=\/|$)/, "").replace(/\/+$/, "");
  const library = /^\/analytics\/(m|browse|research)(\/|$)/.test(path);
  return <div className="navlinks">{links.map(link => {
    const active = link.href === "/analytics/browse" ? library : link.href === "/analytics" ? path === link.href : path === link.href || path.startsWith(`${link.href}/`);
    return <Link key={link.href} href={link.href} prefetch={false} className={active ? "active" : undefined} aria-current={active ? "page" : undefined}>{link.label}</Link>;
  })}</div>;
}
