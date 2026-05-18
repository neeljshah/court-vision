const WS_BASE =
  (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")
    .replace(/^http/, "ws");

type MessageHandler<T> = (data: T) => void;

export class WinProbSocket {
  private ws: WebSocket | null = null;
  private handler: MessageHandler<{ win_prob_home: number; source: string; confidence: number }> | null = null;

  connect(
    gameId: string,
    onMessage: MessageHandler<{ win_prob_home: number; source: string; confidence: number }>,
    onError?: (e: Event) => void
  ) {
    this.handler = onMessage;
    this.ws = new WebSocket(`${WS_BASE}/ws/win-prob/${gameId}`);

    this.ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        this.handler?.(data);
      } catch {}
    };

    if (onError) this.ws.onerror = onError;
  }

  send(possessionIdx: number, gameDict: Record<string, unknown>) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ possession_idx: possessionIdx, game_dict: gameDict }));
    }
  }

  disconnect() {
    this.ws?.close();
    this.ws = null;
  }
}

export class RealtimeSocket {
  private ws: WebSocket | null = null;

  connect(
    onMessage: MessageHandler<{ type: string; data: unknown }>,
    onError?: (e: Event) => void
  ) {
    this.ws = new WebSocket(`${WS_BASE}/stitch/ws/realtime`);

    this.ws.onopen = () => {
      this.ws?.send(JSON.stringify({ type: "subscribe" }));
    };

    this.ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        onMessage(data);
      } catch {}
    };

    if (onError) this.ws.onerror = onError;
  }

  ping() {
    this.ws?.send(JSON.stringify({ type: "ping" }));
  }

  disconnect() {
    this.ws?.close();
    this.ws = null;
  }
}
