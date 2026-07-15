"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, isUnavailable, SPORTS, type ReportList } from "@/lib/p5api";
import { Panel, Unavailable, Badge } from "./Primitives";
import { Num } from "@/components/ui/terminal";

type SportSlate = { sport: string; list: ReportList | null; err?: string };

// SlateBrowser -- the browse view. Lists every sport's available games from
// /api/report/{sport}. Click a game -> /p6/{sport}/{game_id} detail view.
export function SlateBrowser() {
  const [slates, setSlates] = useState<SportSlate[]>(
    SPORTS.map((s) => ({ sport: s, list: null })),
  );

  useEffect(() => {
    const ac = new AbortController();
    SPORTS.forEach((sport) => {
      api.reportList(sport, ac.signal).then((d) => {
        setSlates((prev) =>
          prev.map((row) =>
            row.sport === sport
              ? isUnavailable(d)
                ? { ...row, err: d.reason }
                : { ...row, list: d as ReportList }
              : row,
          ),
        );
      });
    });
    return () => ac.abort();
  }, []);

  const total = slates.reduce(
    (n, s) => n + (s.list?.game_ids?.length ?? 0),
    0,
  );

  return (
    <Panel
      title="Today's slate (browse)"
      right={<Badge tone="slate"><Num>{total}</Num> games</Badge>}
    >
      <div className="space-y-4">
        {slates.map((s) => (
          <div key={s.sport}>
            <div className="mb-1 flex items-center gap-2">
              <span className="microlabel">{s.sport}</span>
              {s.list?.generated_at ? (
                <span className="font-mono text-[10px] text-faint">
                  {s.list.generated_at}
                </span>
              ) : null}
            </div>
            {s.err ? (
              <Unavailable reason={s.err} />
            ) : !s.list ? (
              <p className="text-xs text-faint">loading…</p>
            ) : s.list.status === "unavailable" ||
              s.list.game_ids.length === 0 ? (
              <p className="text-xs text-faint">
                {s.list.reason || "no games available"}
              </p>
            ) : (
              <ul className="grid grid-cols-2 gap-2 md:grid-cols-3">
                {s.list.game_ids.map((gid) => (
                  <li key={gid}>
                    <Link
                      href={`/p6/${s.sport}/${gid}`}
                      className="block border border-border bg-surface-1 px-3 py-2 font-mono text-xs text-foreground transition hover:border-slate-600 hover:bg-surface-2 hover:text-foreground"
                    >
                      {gid}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>
    </Panel>
  );
}
