import type { Status } from "./api";

export function timeAgo(iso: string, now: number = Date.now()): string {
  const diff = Math.max(0, now - new Date(iso).getTime());
  const s = Math.round(diff / 1000);
  if (s < 45) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} h ago`;
  const d = Math.round(h / 24);
  return `${d} d ago`;
}

export function formatDuration(ms: number): string {
  const abs = Math.abs(ms);
  const m = Math.floor(abs / 60000);
  if (m < 1) return "<1m";
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 48) return `${h}h ${m % 60}m`;
  return `${Math.floor(h / 24)}d ${h % 24}h`;
}

export function formatSeconds(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "-";
  return `${(ms / 1000).toFixed(1)} s`;
}

export type SlaState = "overdue" | "soon" | "ok" | "done";

export function slaState(dueIso: string | null, status: Status, now: number = Date.now()) {
  if (!dueIso) return { state: "ok" as SlaState, label: "-" };
  if (status === "resolved" || status === "closed") return { state: "done" as SlaState, label: "Met / closed" };
  const left = new Date(dueIso).getTime() - now;
  if (left < 0) return { state: "overdue" as SlaState, label: `Overdue ${formatDuration(left)}` };
  return { state: (left < 60 * 60 * 1000 ? "soon" : "ok") as SlaState, label: `${formatDuration(left)} left` };
}

export const STATUS_LABEL: Record<Status, string> = {
  new: "New",
  triaged: "Triaged",
  assigned: "Assigned",
  in_progress: "In progress",
  resolved: "Resolved",
  closed: "Closed",
};

export const PRIORITY_LABEL: Record<string, string> = {
  P1: "Urgent",
  P2: "High",
  P3: "Normal",
  P4: "Low",
};

export function titleCase(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

export function locationLine(loc: { building_name: string; label: string; room: string } | null, fallback?: string | null) {
  if (!loc) return fallback || "Location not set";
  const room = /^\d/.test(loc.room) ? ` (${loc.room})` : "";
  return `${loc.building_name} · ${loc.label}${room}`;
}

export const HAZARD_LABEL: Record<string, string> = {
  gas: "Gas",
  electrical: "Electrical",
  water_intrusion: "Water intrusion",
  fire_smoke: "Fire / smoke",
  structural: "Structural",
  slip_trip: "Slip / trip",
  biohazard: "Biohazard",
  chemical: "Chemical",
};
