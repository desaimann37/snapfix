"use client";

import { useEffect, useRef, useState } from "react";

export type LiveEventName =
  | "ticket.created"
  | "ticket.merged"
  | "ticket.updated"
  | "hazard.alert"
  | "cluster.updated"
  | "brief.generated";

export interface LiveEvent<T = Record<string, unknown>> {
  event: LiveEventName;
  data: T;
  receivedAt: number;
}

const EVENTS: LiveEventName[] = [
  "ticket.created",
  "ticket.merged",
  "ticket.updated",
  "hazard.alert",
  "cluster.updated",
  "brief.generated",
];

/** Subscribe to the backend SSE stream. Reconnects automatically (EventSource retry). */
export function useLiveEvents(onEvent: (e: LiveEvent) => void): "connecting" | "live" | "offline" {
  const [state, setState] = useState<"connecting" | "live" | "offline">("connecting");
  const handler = useRef(onEvent);
  handler.current = onEvent;

  useEffect(() => {
    const url = process.env.NEXT_PUBLIC_STREAM_URL || "/api/stream";
    const es = new EventSource(url);
    es.addEventListener("hello", () => setState("live"));
    es.onopen = () => setState("live");
    es.onerror = () => setState(es.readyState === EventSource.CLOSED ? "offline" : "connecting");
    const listeners = EVENTS.map((name) => {
      const fn = (msg: MessageEvent) => {
        try {
          handler.current({ event: name, data: JSON.parse(msg.data), receivedAt: Date.now() });
        } catch {
          /* ignore malformed */
        }
      };
      es.addEventListener(name, fn as EventListener);
      return [name, fn] as const;
    });
    return () => {
      listeners.forEach(([name, fn]) => es.removeEventListener(name, fn as EventListener));
      es.close();
    };
  }, []);

  return state;
}
