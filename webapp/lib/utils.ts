import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function fmtPct(v: number, signed = true): string {
  const s = (v * 100).toFixed(1);
  return signed && v > 0 ? `+${s}%` : `${s}%`;
}

export function fmtOdds(o: number): string {
  return o > 0 ? `+${o}` : `${o}`;
}

export function tierClass(tier?: string): string {
  switch (tier) {
    case "S": return "bg-tier-s/20 text-tier-s border-tier-s/40";
    case "A": return "bg-tier-a/20 text-tier-a border-tier-a/40";
    case "B": return "bg-tier-b/20 text-tier-b border-tier-b/40";
    default:  return "bg-tier-c/20 text-tier-c border-tier-c/40";
  }
}

export function evClass(ev: number): string {
  if (ev >= 0.08) return "text-tier-s";
  if (ev >= 0.04) return "text-tier-a";
  if (ev >= 0.01) return "text-slate-200";
  return "text-slate-400";
}

export function timeAgo(ts: number): string {
  const secs = Math.max(0, Math.round(Date.now() / 1000 - ts));
  if (secs < 60) return `${secs}s`;
  const m = Math.floor(secs / 60);
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  return `${h}h`;
}
