"use client";

import Link from "next/link";
import { useState } from "react";
import { CircleCheck, Lightbulb, LoaderCircle, Network, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { PriorityBadge } from "@/components/ticket-badges";
import { api, type ClusterInfo } from "@/lib/api";
import { timeAgo } from "@/lib/format";

/** A root-cause cluster: hypothesis + member tickets, with Confirm (-> parent inspection) / Dismiss. */
export function ClusterCard({ cluster, onChange }: { cluster: ClusterInfo; onChange: (c: ClusterInfo) => void }) {
  const [busy, setBusy] = useState<"confirm" | "dismiss" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function act(action: "confirm" | "dismiss") {
    setBusy(action);
    setError(null);
    try {
      onChange(await api<ClusterInfo>(`/api/clusters/${cluster.id}/${action}`, { method: "POST" }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Card className="overflow-hidden border-l-4 border-l-primary">
      <CardContent className="space-y-3 pt-5">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <div>
            <p className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-primary">
              <Network className="size-3.5" aria-hidden="true" /> Root-cause pattern · {cluster.building?.name}
            </p>
            <h3 className="mt-1 text-lg font-semibold leading-snug">{cluster.name}</h3>
          </div>
          <span className="rounded-full border px-2.5 py-0.5 text-xs font-medium text-muted-foreground">
            {Math.round(cluster.confidence * 100)}% confidence
          </span>
        </div>
        <p className="text-sm leading-relaxed">{cluster.hypothesis}</p>
        {cluster.recommended_action && (
          <p className="flex gap-2 rounded-md bg-accent px-3 py-2 text-sm text-accent-foreground">
            <Lightbulb className="mt-0.5 size-4 shrink-0" aria-hidden="true" /> {cluster.recommended_action}
          </p>
        )}
        <ul className="divide-y rounded-md border text-sm">
          {cluster.tickets.map((t) => (
            <li key={t.id} className="flex items-center gap-2 px-3 py-1.5">
              <PriorityBadge priority={t.priority} />
              <Link href={`/tickets/${t.short_code}`} className="min-w-0 flex-1 truncate hover:underline">
                <span className="font-mono text-xs text-muted-foreground">{t.short_code}</span> {t.title}
              </Link>
              <span className="hidden shrink-0 text-xs text-muted-foreground sm:inline">
                {t.location ? `${t.location.room}` : ""} · {timeAgo(t.created_at)}
              </span>
            </li>
          ))}
        </ul>
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        {cluster.status === "open" ? (
          <div className="flex flex-wrap gap-2">
            <Button onClick={() => act("confirm")} disabled={busy !== null}>
              {busy === "confirm" ? <LoaderCircle className="animate-spin" /> : <CircleCheck />}
              Confirm: create one inspection ticket
            </Button>
            <Button variant="ghost" onClick={() => act("dismiss")} disabled={busy !== null}>
              {busy === "dismiss" ? <LoaderCircle className="animate-spin" /> : <X />} Dismiss
            </Button>
          </div>
        ) : cluster.parent_ticket ? (
          <p className="text-sm text-success">
            Confirmed. Parent inspection{" "}
            <Link href={`/tickets/${cluster.parent_ticket.short_code}`} className="font-semibold underline">
              {cluster.parent_ticket.short_code}
            </Link>{" "}
            links all {cluster.tickets.length} tickets.
          </p>
        ) : (
          <p className="text-sm text-muted-foreground">Dismissed.</p>
        )}
      </CardContent>
    </Card>
  );
}
