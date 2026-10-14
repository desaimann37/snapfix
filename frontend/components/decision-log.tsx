"use client";

import {
  BellRing,
  CircleDot,
  MapPin,
  Route,
  Siren,
  Sparkles,
  BookOpen,
  UserCheck,
  Users,
  Wand2,
  type LucideIcon,
} from "lucide-react";
import type { TicketEvent } from "@/lib/api";
import { titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";

const ICONS: Record<string, LucideIcon> = {
  created: Sparkles,
  merged: Users,
  escalated: Siren,
  assigned: Route,
  notified: BellRing,
  enriched: Wand2,
  status_changed: CircleDot,
  location_set: MapPin,
  brief_generated: BookOpen,
};

const LABELS: Record<string, string> = {
  created: "Classified",
  merged: "Duplicate merged",
  escalated: "Escalated as hazard",
  assigned: "Routed",
  notified: "On-call notified",
  enriched: "AI added details",
  status_changed: "Status changed",
  location_set: "Location confirmed",
  brief_generated: "Technician brief",
};

function actorLabel(actor: string) {
  if (actor === "ai") return "SnapFix AI";
  if (actor === "system") return "System";
  if (actor === "reporter") return "Reporter";
  return actor.replace(/^user:/, "");
}

type Breakdown = { ticket: string; score: number; text_sim: number; location_score: number; category_match: number };

function DedupeTable({ payload }: { payload: Record<string, unknown> }) {
  const cands = (payload.candidates as Breakdown[] | undefined) ?? [];
  if (!cands.length) return null;
  return (
    <table className="mt-2 w-full text-xs">
      <caption className="sr-only">Duplicate candidates and scores</caption>
      <thead className="text-left text-muted-foreground">
        <tr>
          <th className="py-1 font-medium">Candidate</th>
          <th className="py-1 font-medium">Score</th>
          <th className="py-1 font-medium">Text</th>
          <th className="py-1 font-medium">Location</th>
          <th className="py-1 font-medium">Category</th>
        </tr>
      </thead>
      <tbody className="font-mono">
        {cands.map((c) => (
          <tr key={c.ticket} className="border-t">
            <td className="py-1">{c.ticket}</td>
            <td className="py-1 font-semibold">{c.score.toFixed(2)}</td>
            <td className="py-1">{c.text_sim.toFixed(2)}</td>
            <td className="py-1">{c.location_score}</td>
            <td className="py-1">{c.category_match}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** The AI decision log: every automated decision with its rationale, so a dispatcher can trust (or override) it. */
export function DecisionLog({ events }: { events: TicketEvent[] }) {
  return (
    <ol className="relative space-y-4 border-l pl-6" aria-label="AI decision log">
      {events.map((e) => {
        const Icon = ICONS[e.type] ?? CircleDot;
        const payload = e.payload ?? {};
        const dedupe = (payload.dedupe as Record<string, unknown> | undefined) ?? (e.type === "merged" ? payload : undefined);
        const isAi = e.actor === "ai";
        return (
          <li key={e.id} className="relative">
            <span
              className={cn(
                "absolute -left-[37px] grid size-7 place-items-center rounded-full border bg-card",
                e.type === "escalated" && "border-hazard bg-hazard text-hazard-foreground",
                isAi && e.type !== "escalated" && "border-primary/40 text-primary",
              )}
              aria-hidden="true"
            >
              <Icon className="size-3.5" />
            </span>
            <div className="flex flex-wrap items-baseline gap-x-2">
              <span className="text-sm font-semibold">{LABELS[e.type] ?? titleCase(e.type)}</span>
              <span className="text-xs text-muted-foreground">
                {actorLabel(e.actor)} · {new Date(e.created_at).toLocaleString()}
              </span>
            </div>
            {e.rationale && <p className="mt-0.5 text-sm text-muted-foreground">{e.rationale}</p>}
            {e.type === "status_changed" && !e.rationale && payload.to ? (
              <p className="mt-0.5 text-sm text-muted-foreground">
                {titleCase(String(payload.from))} → {titleCase(String(payload.to))}
              </p>
            ) : null}
            {dedupe && <DedupeTable payload={dedupe} />}
            {Object.keys(payload).length > 0 && (
              <details className="mt-1">
                <summary className="cursor-pointer text-xs text-muted-foreground hover:text-foreground">Details</summary>
                <pre className="mt-1 max-h-56 overflow-auto rounded-md bg-muted p-2 text-[11px] leading-relaxed">
                  {JSON.stringify(payload, null, 2)}
                </pre>
              </details>
            )}
          </li>
        );
      })}
    </ol>
  );
}
