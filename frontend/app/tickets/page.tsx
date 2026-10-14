"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Inbox, RefreshCw, Search, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { LiveIndicator } from "@/components/live-indicator";
import {
  HazardBadge,
  PriorityBadge,
  ReportCountBadge,
  SlaCountdown,
  StatusBadge,
  TradeLabel,
} from "@/components/ticket-badges";
import { api, qs, type Building, type Ticket, type TicketList } from "@/lib/api";
import { locationLine, timeAgo } from "@/lib/format";
import { useLiveEvents } from "@/lib/use-live";
import { cn } from "@/lib/utils";

const TRADES = [
  "Plumbing",
  "Electrical",
  "HVAC",
  "Carpentry/Doors & Locks",
  "Custodial",
  "Grounds",
  "Elevator",
  "IT/AV",
  "Safety/Environmental",
  "General",
];

type StatusTab = "open" | "resolved,closed" | "all";

export default function TicketQueuePage() {
  const [tab, setTab] = useState<StatusTab>("open");
  const [q, setQ] = useState("");
  const [trade, setTrade] = useState("");
  const [priority, setPriority] = useState("");
  const [building, setBuilding] = useState("");
  const [sort, setSort] = useState("queue");
  const [data, setData] = useState<TicketList | null>(null);
  const [buildings, setBuildings] = useState<Building[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [fresh, setFresh] = useState<Record<string, number>>({});
  const [now, setNow] = useState(() => Date.now());
  const refetchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async () => {
    try {
      const params = { status: tab === "all" ? undefined : tab, q, trade, priority, building, sort, limit: 200 };
      setData(await api<TicketList>(`/api/tickets${qs(params)}`));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load tickets");
    }
  }, [tab, q, trade, priority, building, sort]);

  useEffect(() => {
    const t = setTimeout(load, q ? 250 : 0);
    return () => clearTimeout(t);
  }, [load, q]);

  useEffect(() => {
    api<Building[]>("/api/buildings").then(setBuildings).catch(() => undefined);
    const tick = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(tick);
  }, []);

  const live = useLiveEvents((e) => {
    const id = (e.data as { id?: string; ticket?: { id?: string } }).id ?? (e.data as { ticket?: { id?: string } }).ticket?.id;
    if (id) setFresh((f) => ({ ...f, [id]: Date.now() }));
    if (refetchTimer.current) clearTimeout(refetchTimer.current);
    refetchTimer.current = setTimeout(load, 300);
  });

  const items = useMemo(() => data?.items ?? [], [data]);
  const hazardCount = useMemo(
    () => items.filter((t) => t.is_hazard && t.status !== "closed" && t.status !== "resolved").length,
    [items],
  );

  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Work order queue</h1>
          <p className="text-sm text-muted-foreground">
            {data ? `${data.total} ticket${data.total === 1 ? "" : "s"}` : "Loading…"} · hazards pinned to the top
          </p>
        </div>
        <div className="flex items-center gap-2">
          <LiveIndicator state={live} />
          <Button variant="outline" size="sm" onClick={load} aria-label="Refresh">
            <RefreshCw /> Refresh
          </Button>
        </div>
      </div>

      {hazardCount > 0 && tab !== "resolved,closed" && (
        <div role="alert" className="mt-4 flex items-center gap-2 rounded-lg border border-hazard/40 bg-hazard-soft px-4 py-3 text-sm font-medium text-hazard">
          <TriangleAlert className="size-5 shrink-0" aria-hidden="true" />
          {hazardCount} open hazard{hazardCount > 1 ? "s" : ""}: on-call notified, P1 response required.
        </div>
      )}

      <div className="mt-4 flex flex-col gap-3 lg:flex-row lg:items-center">
        <div role="group" aria-label="Status filter" className="inline-flex h-9 items-center rounded-lg bg-muted p-1 text-muted-foreground">
          {([["open", "Open"], ["resolved,closed", "Resolved"], ["all", "All"]] as const).map(([value, label]) => (
            <button
              key={value}
              type="button"
              aria-pressed={tab === value}
              onClick={() => setTab(value)}
              className={cn(
                "rounded-md px-3 py-1 text-sm font-medium transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                tab === value && "bg-card text-foreground shadow",
              )}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="relative flex-1">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" aria-hidden="true" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search title, summary, SF-code…"
            className="pl-8"
            aria-label="Search tickets"
          />
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:w-[620px]">
          <Select value={trade} onChange={(e) => setTrade(e.target.value)} aria-label="Filter by trade">
            <option value="">All trades</option>
            {TRADES.map((t) => (
              <option key={t} value={t}>{t}</option>
            ))}
          </Select>
          <Select value={priority} onChange={(e) => setPriority(e.target.value)} aria-label="Filter by priority">
            <option value="">All priorities</option>
            {["P1", "P2", "P3", "P4"].map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </Select>
          <Select value={building} onChange={(e) => setBuilding(e.target.value)} aria-label="Filter by building">
            <option value="">All buildings</option>
            {buildings.map((b) => (
              <option key={b.code} value={b.code}>{b.name}</option>
            ))}
          </Select>
          <Select value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sort order">
            <option value="queue">Queue order</option>
            <option value="newest">Newest first</option>
            <option value="sla">SLA due soonest</option>
            <option value="reports">Most reports</option>
          </Select>
        </div>
      </div>

      {error && (
        <p role="alert" className="mt-4 rounded-md border border-destructive/40 px-4 py-3 text-sm text-destructive">
          {error}. Is the backend running?
        </p>
      )}

      <Card className="mt-4 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[960px] text-sm">
            <caption className="sr-only">Work orders</caption>
            <thead className="border-b bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th scope="col" className="px-4 py-2.5 font-medium">Priority</th>
                <th scope="col" className="px-4 py-2.5 font-medium">Ticket</th>
                <th scope="col" className="px-4 py-2.5 font-medium">Location</th>
                <th scope="col" className="px-4 py-2.5 font-medium">Team</th>
                <th scope="col" className="px-4 py-2.5 font-medium">Status</th>
                <th scope="col" className="px-4 py-2.5 font-medium">Reports</th>
                <th scope="col" className="px-4 py-2.5 font-medium">SLA</th>
                <th scope="col" className="px-4 py-2.5 font-medium">Age</th>
              </tr>
            </thead>
            <tbody>
              {!data &&
                Array.from({ length: 8 }).map((_, i) => (
                  <tr key={i} className="border-b">
                    <td colSpan={8} className="px-4 py-3">
                      <Skeleton className="h-6 w-full" />
                    </td>
                  </tr>
                ))}
              {data && items.length === 0 && (
                <tr>
                  <td colSpan={8} className="px-4 py-12 text-center text-muted-foreground">
                    <Inbox className="mx-auto mb-2 size-6" aria-hidden="true" />
                    No tickets match these filters.
                  </td>
                </tr>
              )}
              {items.map((t) => (
                <TicketRow key={t.id} t={t} now={now} fresh={Boolean(fresh[t.id] && now - fresh[t.id] < 10_000)} />
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

function TicketRow({ t, now, fresh }: { t: Ticket; now: number; fresh: boolean }) {
  const openHazard = t.is_hazard && t.status !== "resolved" && t.status !== "closed";
  return (
    <tr
      className={cn(
        "border-b align-top transition-colors last:border-0 hover:bg-muted/40",
        openHazard && "bg-hazard-soft hover:bg-hazard-soft",
        fresh && "animate-row-in",
      )}
    >
      <td className={cn("px-4 py-3", openHazard && "border-l-4 border-l-hazard")}>
        <PriorityBadge priority={t.priority} />
      </td>
      <td className="max-w-[360px] px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-xs text-muted-foreground">{t.short_code}</span>
          {openHazard && <HazardBadge hazardType={t.hazard_type} />}
          {t.needs_review && (
            <span className="rounded border border-p2/40 px-1.5 text-[11px] font-medium text-p2">Needs review</span>
          )}
        </div>
        <Link href={`/tickets/${t.short_code}`} className="mt-0.5 block font-medium leading-snug hover:text-primary hover:underline">
          {t.title}
        </Link>
        <span className="text-xs text-muted-foreground">{t.category_label}</span>
      </td>
      <td className="max-w-[220px] px-4 py-3 text-muted-foreground">{locationLine(t.location, t.location_text)}</td>
      <td className="max-w-[180px] px-4 py-3">
        <TradeLabel trade={t.trade} team={t.team?.name} />
        {t.assignee && <div className="mt-0.5 truncate text-xs text-muted-foreground">{t.assignee}</div>}
      </td>
      <td className="px-4 py-3">
        <StatusBadge status={t.status} />
      </td>
      <td className="px-4 py-3">
        <ReportCountBadge count={t.report_count} />
      </td>
      <td className="px-4 py-3">
        <SlaCountdown due={t.sla_due_at} status={t.status} now={now} />
      </td>
      <td className="whitespace-nowrap px-4 py-3 text-xs text-muted-foreground">{timeAgo(t.created_at, now)}</td>
    </tr>
  );
}
