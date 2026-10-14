"use client";

import Link from "next/link";
import { useState } from "react";
import { Siren, X } from "lucide-react";
import { useLiveEvents } from "@/lib/use-live";

interface HazardAlert {
  id: string;
  short_code: string;
  title: string;
  label: string;
  location: string;
  receivedAt: number;
}

/** Red banner on every dispatcher/manager page the moment a hazard is reported (via SSE). */
export function HazardAlertBar() {
  const [alerts, setAlerts] = useState<HazardAlert[]>([]);

  useLiveEvents((e) => {
    if (e.event !== "hazard.alert") return;
    const d = e.data as Omit<HazardAlert, "receivedAt">;
    setAlerts((prev) => [{ ...d, receivedAt: e.receivedAt }, ...prev.filter((a) => a.id !== d.id)].slice(0, 3));
  });

  if (!alerts.length) return null;
  return (
    <div className="no-print sticky top-14 z-20 space-y-px" role="region" aria-label="Hazard alerts">
      {alerts.map((a) => (
        <div key={a.id} role="alert" className="bg-hazard text-hazard-foreground">
          <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-2.5 text-sm">
            <Siren className="size-5 shrink-0 animate-pulse" aria-hidden="true" />
            <p className="min-w-0 flex-1">
              <span className="font-bold uppercase tracking-wide">P1 hazard · {a.label}</span>{" "}
              <span className="font-mono">{a.short_code}</span> {a.title} <span className="opacity-90">@ {a.location}</span>
            </p>
            <Link href={`/tickets/${a.short_code}`} className="shrink-0 rounded-md bg-hazard-foreground/15 px-2.5 py-1 font-semibold hover:bg-hazard-foreground/25">
              View
            </Link>
            <button
              onClick={() => setAlerts((prev) => prev.filter((x) => x.id !== a.id))}
              className="shrink-0 rounded p-1 hover:bg-hazard-foreground/15"
              aria-label={`Dismiss alert ${a.short_code}`}
            >
              <X className="size-4" />
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
