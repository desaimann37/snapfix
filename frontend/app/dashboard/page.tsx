"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  BellRing,
  BookOpen,
  Bot,
  CircleDot,
  Clock,
  Gauge,
  Inbox,
  LoaderCircle,
  MapPin,
  Network,
  Play,
  Route,
  Siren,
  Sparkles,
  Timer,
  Users,
  Wand2,
  type LucideIcon,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { AgentChat } from "@/components/agent-chat";
import { ClusterCard } from "@/components/cluster-card";
import { FloorPlan, useFloor } from "@/components/floor-plan";
import { LiveIndicator } from "@/components/live-indicator";
import { HeroFigure, StatTile, compact } from "@/components/stat-tile";
import { TrendChart } from "@/components/trend-chart";
import { api, type ActivityItem, type BuildingSummary, type ClusterInfo, type Kpis, type TrendData } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { useLiveEvents } from "@/lib/use-live";
import { cn } from "@/lib/utils";

const EVENT_ICON: Record<string, LucideIcon> = {
  created: Sparkles,
  merged: Users,
  escalated: Siren,
  assigned: Route,
  notified: BellRing,
  enriched: Wand2,
  brief_generated: BookOpen,
  location_set: MapPin,
  linked: Network,
};
const EVENT_LABEL: Record<string, string> = {
  created: "New ticket",
  merged: "Duplicate merged",
  escalated: "Hazard escalated",
  assigned: "Routed",
  notified: "On-call notified",
  enriched: "AI details added",
  brief_generated: "Brief written",
  status_changed: "Status changed",
  location_set: "Location confirmed",
  linked: "Linked to inspection",
};

function seconds(ms: number | null | undefined) {
  return ms == null ? "-" : `${(ms / 1000).toFixed(1)} s`;
}

function duration(s: number | null | undefined) {
  if (s == null) return "-";
  if (s < 90) return `${Math.round(s)} s`;
  if (s < 5400) return `${Math.round(s / 60)} min`;
  return `${(s / 3600).toFixed(1)} h`;
}

export default function DashboardPage() {
  const [kpis, setKpis] = useState<Kpis | null>(null);
  const [clusters, setClusters] = useState<ClusterInfo[] | null>(null);
  const [activity, setActivity] = useState<ActivityItem[] | null>(null);
  const [trend, setTrend] = useState<TrendData | null>(null);
  const [buildings, setBuildings] = useState<BuildingSummary[]>([]);
  const [building, setBuilding] = useState("ENGR");
  const [floor, setFloor] = useState<number | null>(null);
  const [planKey, setPlanKey] = useState(0);
  const [running, setRunning] = useState(false);
  const [freshIds, setFreshIds] = useState<Set<string>>(new Set());
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadAll = useCallback(async () => {
    const [k, c, a, t, b] = await Promise.allSettled([
      api<Kpis>("/api/dashboard/kpis"),
      api<ClusterInfo[]>("/api/clusters?status=all"),
      api<ActivityItem[]>("/api/dashboard/activity?limit=25"),
      api<TrendData>("/api/dashboard/trend?days=14"),
      api<BuildingSummary[]>("/api/dashboard/buildings"),
    ]);
    if (k.status === "fulfilled") setKpis(k.value);
    if (c.status === "fulfilled") setClusters(c.value.filter((x) => x.status !== "dismissed").slice(0, 4));
    if (a.status === "fulfilled") {
      setActivity((prev) => {
        if (prev) {
          const known = new Set(prev.map((x) => x.id));
          const fresh = a.value.filter((x) => !known.has(x.id)).map((x) => x.id);
          if (fresh.length) setFreshIds(new Set(fresh));
        }
        return a.value;
      });
    }
    if (t.status === "fulfilled") setTrend(t.value);
    if (b.status === "fulfilled") setBuildings(b.value);
    setPlanKey((n) => n + 1);
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const live = useLiveEvents(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(loadAll, 400);
  });

  const current = buildings.find((b) => b.code === building);
  const shownFloor = floor ?? current?.busiest_floor ?? 1;
  const plan = useFloor(building, shownFloor, planKey);

  async function runAnalysis() {
    setRunning(true);
    try {
      await api("/api/clusters/run", { method: "POST" });
      await loadAll();
    } finally {
      setRunning(false);
    }
  }

  const p = kpis?.open_by_priority;
  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Operations dashboard</h1>
          <p className="text-sm text-muted-foreground">
            Live view across the campus · {kpis?.llm_mode === "mock" ? "offline demo mode" : "AI live"}
          </p>
        </div>
        <LiveIndicator state={live} />
      </div>

      <section aria-label="Key metrics" className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-[1.3fr_repeat(3,1fr)]">
        {kpis ? (
          <>
            <HeroFigure
              label="Duplicate reports merged (30 days)"
              value={compact(kpis.duplicates_prevented_30d)}
              detail={<>work orders dispatch didn&apos;t have to triage twice · {kpis.duplicates_merged_live} merged live</>}
            />
            <StatTile
              label="Open work orders"
              value={compact(kpis.open_total)}
              icon={Inbox}
              detail={p && <>P1 {p.P1} · P2 {p.P2} · P3 {p.P3} · P4 {p.P4}</>}
            />
            <StatTile
              label="Open hazards"
              value={String(kpis.hazards_open)}
              icon={Siren}
              tone={kpis.hazards_open ? "critical" : "default"}
              detail={<>{kpis.hazards_24h} reported in the last 24 h</>}
            />
            <StatTile
              label="Photo → ticket (median)"
              value={seconds(kpis.photo_to_ticket_ms.p50)}
              icon={Timer}
              detail={
                kpis.photo_to_ticket_ms.count
                  ? <>p95 {seconds(kpis.photo_to_ticket_ms.p95)} · {kpis.photo_to_ticket_ms.count} live reports (7 d)</>
                  : <>no live reports yet this week</>
              }
            />
            <StatTile label="Past SLA" value={String(kpis.sla_breaches)} icon={Clock} detail="open tickets past their due time" />
            <StatTile label="Time to triage (median)" value={duration(kpis.median_time_to_triage_s)} icon={Gauge} detail="first report → routed, SnapFix tickets" />
            <StatTile label="Reports per day" value={String(kpis.reports_per_day_14d)} icon={Activity} detail={`${kpis.reports_24h} in the last 24 h`} />
            <StatTile label="Root-cause patterns" value={String(kpis.open_clusters)} icon={Network} detail="open clusters to review" />
          </>
        ) : (
          Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-28" />)
        )}
      </section>

      <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_380px]">
        <div className="min-w-0 space-y-6">
          <section aria-labelledby="clusters-h">
            <div className="mb-2 flex items-center justify-between">
              <h2 id="clusters-h" className="flex items-center gap-2 text-lg font-semibold">
                <Network className="size-5 text-primary" aria-hidden="true" /> Root-cause clusters
              </h2>
              <Button variant="outline" size="sm" onClick={runAnalysis} disabled={running}>
                {running ? <LoaderCircle className="animate-spin" /> : <Play />} Run analysis now
              </Button>
            </div>
            {!clusters ? (
              <Skeleton className="h-48" />
            ) : clusters.length === 0 ? (
              <Card>
                <CardContent className="py-8 text-center text-sm text-muted-foreground">
                  No root-cause patterns right now. Clustering runs every 2 minutes over open tickets.
                </CardContent>
              </Card>
            ) : (
              <div className="space-y-4">
                {clusters.map((c) => (
                  <ClusterCard
                    key={c.id}
                    cluster={c}
                    onChange={(updated) => {
                      setClusters((prev) => (prev ?? []).map((x) => (x.id === updated.id ? updated : x)));
                      loadAll();
                    }}
                  />
                ))}
              </div>
            )}
          </section>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Reports per day by trade</CardTitle>
              <p className="text-sm text-muted-foreground">Last 14 days · top four trades, the rest grouped as Other</p>
            </CardHeader>
            <CardContent>
              <TrendChart data={trend} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Building hotspots</CardTitle>
              <p className="text-sm text-muted-foreground">Open tickets by room. Bigger circle = more open tickets.</p>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <div role="tablist" aria-label="Building" className="flex flex-wrap gap-1.5">
                  {buildings.map((b) => (
                    <button
                      key={b.code}
                      role="tab"
                      aria-selected={b.code === building}
                      onClick={() => {
                        setBuilding(b.code);
                        setFloor(null);
                      }}
                      className={cn(
                        "rounded-md border px-3 py-1 text-sm font-medium",
                        b.code === building ? "border-primary bg-primary text-primary-foreground" : "hover:bg-accent",
                      )}
                    >
                      {b.name} <span>({b.open_total}{b.hazards ? `, ${b.hazards} hazard` : ""})</span>
                    </button>
                  ))}
                </div>
                {current && (
                  <div role="tablist" aria-label="Floor" className="ml-auto flex gap-1">
                    {Array.from({ length: current.floors }, (_, i) => i + 1).map((f) => (
                      <button
                        key={f}
                        role="tab"
                        aria-selected={f === shownFloor}
                        onClick={() => setFloor(f)}
                        className={cn(
                          "min-w-12 rounded-md border px-2 py-1 text-sm",
                          f === shownFloor ? "border-foreground font-semibold" : "text-muted-foreground hover:bg-accent",
                        )}
                      >
                        F{f} · {current.open_by_floor[String(f)] ?? 0}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              <FloorPlan data={plan} showCounts labelScale={1.15} />
            </CardContent>
          </Card>
        </div>

        <aside className="space-y-6">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-base">
                <Activity className="size-4 text-primary" aria-hidden="true" /> Live activity
              </CardTitle>
            </CardHeader>
            <CardContent>
              {!activity ? (
                <Skeleton className="h-64" />
              ) : (
                <ol className="max-h-[420px] space-y-2.5 overflow-y-auto pr-1" aria-live="polite">
                  {activity.map((e) => {
                    const Icon = EVENT_ICON[e.type] ?? CircleDot;
                    return (
                      <li key={e.id} className={cn("flex gap-2.5 rounded-md p-1 text-sm", freshIds.has(e.id) && "animate-row-in")}>
                        <span
                          className={cn(
                            "mt-0.5 grid size-6 shrink-0 place-items-center rounded-full border",
                            e.type === "escalated" ? "border-hazard bg-hazard text-hazard-foreground" : "text-primary",
                          )}
                          aria-hidden="true"
                        >
                          <Icon className="size-3.5" />
                        </span>
                        <div className="min-w-0">
                          <p className="truncate">
                            <span className="font-medium">{EVENT_LABEL[e.type] ?? e.type}</span>{" "}
                            <Link href={`/tickets/${e.ticket.short_code}`} className="font-mono text-xs text-muted-foreground hover:underline">
                              {e.ticket.short_code}
                            </Link>
                          </p>
                          <p className="truncate text-xs text-muted-foreground">{e.ticket.title}</p>
                          <p className="text-[11px] text-muted-foreground">{timeAgo(e.created_at)}</p>
                        </div>
                      </li>
                    );
                  })}
                </ol>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-base">
                <Bot className="size-4 text-primary" aria-hidden="true" /> Dispatcher assistant
              </CardTitle>
            </CardHeader>
            <CardContent>
              <AgentChat />
            </CardContent>
          </Card>
        </aside>
      </div>
    </div>
  );
}
