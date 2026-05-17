"use client";

import { useState, useRef, useEffect } from "react";
import { useMutation } from "@tanstack/react-query";
import { chat } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";

interface Message {
  role: "user" | "assistant";
  content: string;
  ts: number;
}

const SUGGESTED = [
  "Best bets tonight?",
  "Who's due for regression?",
  "Optimal $500 allocation?",
  "Which props have the highest edge?",
  "Show me back-to-back fatigue plays",
];

export default function AIResearch() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  const { mutate: sendMessage, isPending } = useMutation({
    mutationFn: (msg: string) => chat(msg),
    onSuccess: (data) => {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: data.response, ts: Date.now() },
      ]);
    },
    onError: (err) => {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Error: ${(err as Error).message}`, ts: Date.now() },
      ]);
    },
  });

  function submit(msg: string) {
    if (!msg.trim() || isPending) return;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: msg.trim(), ts: Date.now() }]);
    sendMessage(msg.trim());
  }

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="flex flex-col gap-4 h-full max-h-[calc(100vh-11rem)]">
      <h1 className="text-sm font-mono font-bold text-[#e5e7eb] shrink-0">AI Research</h1>

      {/* Suggested prompts */}
      {messages.length === 0 && (
        <div className="flex flex-wrap gap-2 shrink-0">
          {SUGGESTED.map((s) => (
            <button
              key={s}
              onClick={() => submit(s)}
              className="text-xs px-3 py-1.5 rounded border border-[#1e2028] text-[#9ca3af] hover:text-[#e5e7eb] hover:border-[#f97316]/30 transition-colors font-mono"
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Message thread */}
      <div className="flex-1 overflow-auto space-y-3">
        {messages.length === 0 && (
          <div className="text-center py-16 text-[#4b5563] text-xs font-mono">
            Ask anything about tonight&apos;s slate, prop edges, or portfolio allocation
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
            <div
              className={`max-w-[75%] rounded px-4 py-2 text-sm ${
                m.role === "user"
                  ? "bg-[#f97316]/20 text-[#e5e7eb] border border-[#f97316]/20"
                  : "bg-[#12141a] text-[#e5e7eb] border border-[#1e2028]"
              }`}
            >
              {m.role === "assistant" && (
                <div className="text-[10px] font-mono text-[#f97316] mb-1">CourtVision AI</div>
              )}
              <div className="whitespace-pre-wrap">{m.content}</div>
            </div>
          </div>
        ))}
        {isPending && (
          <div className="flex justify-start">
            <Card className="bg-[#12141a] border-[#1e2028] max-w-xs">
              <CardContent className="p-3">
                <div className="text-[10px] font-mono text-[#f97316] mb-2">CourtVision AI</div>
                <div className="space-y-1">
                  <Skeleton className="h-3 w-48 bg-[#1e2028]" />
                  <Skeleton className="h-3 w-36 bg-[#1e2028]" />
                </div>
              </CardContent>
            </Card>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="flex gap-2 shrink-0">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(input); } }}
          placeholder="Ask about edges, props, lineup..."
          disabled={isPending}
          className="flex-1 bg-[#12141a] border-[#1e2028] font-mono text-sm text-[#e5e7eb] placeholder:text-[#4b5563]"
        />
        <button
          onClick={() => submit(input)}
          disabled={!input.trim() || isPending}
          className="px-4 py-2 rounded bg-[#f97316] text-black text-sm font-medium disabled:opacity-40 disabled:cursor-not-allowed hover:bg-[#ea6c0a] transition-colors"
        >
          Send
        </button>
      </div>
    </div>
  );
}
