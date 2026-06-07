"use client";

import { useLiveSocket } from "@/lib/ws";
import { GameHeader } from "@/components/GameHeader";
import { TopBets } from "@/components/TopBets";
import { PBPFeed } from "@/components/PBPFeed";
import { Lineups } from "@/components/Lineups";
import { AlertsFeed } from "@/components/AlertsFeed";
import { StatusBar } from "@/components/StatusBar";

export default function Home() {
  useLiveSocket();

  return (
    <main className="mx-auto flex max-w-7xl flex-col gap-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold tracking-tight">
          CourtVision <span className="text-slate-500 font-mono">live</span>
        </h1>
        <StatusBar />
      </div>

      <GameHeader />

      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-12 lg:col-span-3">
          <Lineups />
        </div>
        <div className="col-span-12 lg:col-span-5">
          <TopBets />
        </div>
        <div className="col-span-12 lg:col-span-4">
          <PBPFeed />
        </div>
      </div>

      <AlertsFeed />

      <footer className="mt-6 text-center text-xs text-slate-600">
        CourtVision Live · sub-30s in-play intelligence ·
        click any bet for full reasoning
      </footer>
    </main>
  );
}
