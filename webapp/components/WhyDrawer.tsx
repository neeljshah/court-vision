"use client";

import { useEffect, useState } from "react";
import { X, Sparkles } from "lucide-react";
import { REST } from "@/lib/config";
import type { Bet, Explanation } from "@/lib/types";
import { cn, evClass, fmtOdds, fmtPct, tierClass } from "@/lib/utils";
import { Num } from "@/components/ui/terminal";

export function WhyDrawer({
  bet,
  onClose,
}: {
  bet: Bet | null;
  onClose: () => void;
}) {
  const [expl, setExpl] = useState<Explanation | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!bet) {
      setExpl(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setErr(null);
    fetch(REST("/api/explain"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ bet }),
    })
      .then(async (r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data) => !cancelled && setExpl(data))
      .catch((e) => !cancelled && setErr(String(e)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [bet]);

  if (!bet) return null;

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/50">
      <button
        type="button"
        aria-label="close"
        className="flex-1"
        onClick={onClose}
      />
      <aside className="relative h-full w-full max-w-md overflow-y-auto border-l border-border bg-card p-6">
        <header className="mb-4 flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2 microlabel">
              <Sparkles className="h-3.5 w-3.5" />
              why this bet
            </div>
            <h3 className="mt-2 text-lg font-semibold text-foreground">
              {bet.name} &middot; {bet.stat.toUpperCase()} {bet.side.toUpperCase()}{" "}
              {bet.line}
            </h3>
            <p className="mt-1 text-sm text-muted-foreground">
              {bet.book} {fmtOdds(bet.odds)} &middot;{" "}
              <Num className={evClass(bet.ev)}>{fmtPct(bet.ev)} EV</Num> &middot;{" "}
              <Num>K {(bet.kelly * 100).toFixed(1)}%</Num>
            </p>
            <span
              className={cn(
                "mt-2 inline-block border px-2 py-0.5 font-data text-xs",
                tierClass(bet.tier),
              )}
            >
              Tier {bet.tier}
            </span>
          </div>
          <button
            type="button"
            aria-label="close drawer"
            className="p-1 text-muted-foreground hover:bg-surface-2 hover:text-foreground"
            onClick={onClose}
          >
            <X className="h-5 w-5" />
          </button>
        </header>

        <section className="space-y-4">
          {loading && <div className="text-sm text-faint">loading...</div>}
          {err && (
            <div className="border border-danger/40 bg-danger/10 p-3 text-sm text-down">
              Couldn't load explanation: {err}
            </div>
          )}
          {expl?.sections.map((s) => (
            <SectionCard key={s.kind} title={s.title} body={s.body} />
          ))}
          {expl && !expl.sections.length && (
            <p className="text-sm text-faint">
              No structured reasoning available yet. The engine will fill in
              context as PBP + line ticks accumulate.
            </p>
          )}
        </section>
      </aside>
    </div>
  );
}

function SectionCard({ title, body }: { title: string; body: string }) {
  return (
    <article className="border border-border bg-surface-1 p-3">
      <h4 className="microlabel">
        {title}
      </h4>
      <pre className="mt-1 whitespace-pre-wrap break-words font-data text-xs leading-relaxed text-foreground">
        {body}
      </pre>
    </article>
  );
}
