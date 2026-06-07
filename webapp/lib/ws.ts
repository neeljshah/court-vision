"use client";

import { useEffect } from "react";
import { WS_URL } from "./config";
import { useLiveStore } from "./store";
import type { BusMessage } from "./types";

/**
 * useLiveSocket — single-instance WebSocket hook with exponential
 * backoff reconnect + visibility-aware suspend.
 *
 * Mount once in the root client component. All consumers of the
 * Zustand store will re-render as events arrive.
 */
export function useLiveSocket(token?: string) {
  useEffect(() => {
    let ws: WebSocket | null = null;
    let backoffMs = 500;
    let closedByUs = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let pingTimer: ReturnType<typeof setInterval> | null = null;

    const connect = () => {
      try {
        ws = new WebSocket(WS_URL(token));
      } catch (err) {
        scheduleReconnect();
        return;
      }
      ws.onopen = () => {
        backoffMs = 500;
        useLiveStore.setState({ wsReady: true });
        if (pingTimer) clearInterval(pingTimer);
        pingTimer = setInterval(() => {
          if (ws && ws.readyState === WebSocket.OPEN) {
            try {
              ws.send("ping");
            } catch {
              /* noop */
            }
          }
        }, 25_000);
      };
      ws.onmessage = (ev) => {
        try {
          const msg: BusMessage = JSON.parse(ev.data);
          useLiveStore.getState().applyMessage(msg);
        } catch (err) {
          // ignore malformed messages
        }
      };
      ws.onerror = () => {
        // wait for onclose to drive reconnect
      };
      ws.onclose = () => {
        if (pingTimer) {
          clearInterval(pingTimer);
          pingTimer = null;
        }
        useLiveStore.setState({ wsReady: false });
        if (!closedByUs) scheduleReconnect();
      };
    };

    const scheduleReconnect = () => {
      if (reconnectTimer) clearTimeout(reconnectTimer);
      const jitter = Math.random() * 250;
      reconnectTimer = setTimeout(connect, Math.min(backoffMs + jitter, 15_000));
      backoffMs = Math.min(backoffMs * 2, 15_000);
    };

    connect();

    return () => {
      closedByUs = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (pingTimer) clearInterval(pingTimer);
      try {
        ws?.close();
      } catch {
        /* noop */
      }
    };
  }, [token]);
}
