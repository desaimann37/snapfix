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

type ConnState = "connecting" | "live" | "offline";

const EVENTS: LiveEventName[] = [
  "ticket.created",
  "ticket.merged",
  "ticket.updated",
  "hazard.alert",
  "cluster.updated",
  "brief.generated",
];

// One EventSource per tab, shared by every component that subscribes (browsers limit connections per host).
let source: EventSource | null = null;
let state: ConnState = "connecting";
const listeners = new Set<(e: LiveEvent) => void>();
const stateListeners = new Set<(s: ConnState) => void>();

function setState(s: ConnState) {
  state = s;
  stateListeners.forEach((fn) => fn(s));
}

function ensureSource() {
  if (source || typeof window === "undefined") return;
  const es = new EventSource(process.env.NEXT_PUBLIC_STREAM_URL || "/api/stream");
  source = es;
  es.addEventListener("hello", () => setState("live"));
  es.onopen = () => setState("live");
  es.onerror = () => setState(es.readyState === EventSource.CLOSED ? "offline" : "connecting");
  for (const name of EVENTS) {
    es.addEventListener(name, (msg) => {
      let data: Record<string, unknown>;
      try {
        data = JSON.parse((msg as MessageEvent).data);
      } catch {
        return;
      }
      const evt: LiveEvent = { event: name, data, receivedAt: Date.now() };
      listeners.forEach((fn) => fn(evt));
    });
  }
}

function releaseSource() {
  if (source && listeners.size === 0 && stateListeners.size === 0) {
    source.close();
    source = null;
    state = "connecting";
  }
}

/** Subscribe to the backend SSE stream. Reconnects automatically (EventSource retry). */
export function useLiveEvents(onEvent: (e: LiveEvent) => void): ConnState {
  const [conn, setConn] = useState<ConnState>(state);
  const handler = useRef(onEvent);
  handler.current = onEvent;

  useEffect(() => {
    const fn = (e: LiveEvent) => handler.current(e);
    listeners.add(fn);
    stateListeners.add(setConn);
    ensureSource();
    setConn(state);
    return () => {
      listeners.delete(fn);
      stateListeners.delete(setConn);
      releaseSource();
    };
  }, []);

  return conn;
}
