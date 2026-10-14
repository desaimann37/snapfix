"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, ImageOff, MapPin, Siren, Timer, UserCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { DecisionLog } from "@/components/decision-log";
import { FloorPlan, useFloor } from "@/components/floor-plan";
import { TechnicianBrief } from "@/components/technician-brief";
import {
  HazardBadge,
  PriorityBadge,
  ReportCountBadge,
  SeverityMeter,
  SlaCountdown,
  StatusBadge,
  TradeLabel,
} from "@/components/ticket-badges";
import { api, jsonBody, qs, type Status, type Ticket, type TicketDetail, type TicketList } from "@/lib/api";
import { STATUS_LABEL, formatSeconds, locationLine, timeAgo } from "@/lib/format";
import { useLiveEvents } from "@/lib/use-live";

const FLOW: Status[] = ["triaged", "assigned", "in_progress", "resolved", "closed"];

export default function TicketDetailPage({ params }: { params: { id: string } }) {
  const [t, setT] = useState<TicketDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [assignee, setAssignee] = useState("");
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState<Ticket[]>([]);
  const [planKey, setPlanKey] = useState(0);

  const load = useCallback(async () => {
    try {
      const detail = await api<TicketDetail>(`/api/tickets/${encodeURIComponent(params.id)}`);
      setT(detail);
      setAssignee(detail.assignee ?? "");
      setError(null);
      if (detail.asset) {
        const h = await api<TicketList>(`/api/tickets${qs({ asset_id: detail.asset.id, sort: "newest", limit: 10 })}`);
        setHistory(h.items.filter((x) => x.id !== detail.id));
      } else {
        setHistory([]);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load ticket");
    }
  }, [params.id]);

  useEffect(() => {
    load();
  }, [load]);

  useLiveEvents((e) => {
    const id = (e.data as { id?: string }).id;
    if (t && id === t.id) {
      load();
      setPlanKey((k) => k + 1);
    }
  });

  const floor = useFloor(t?.location?.building_code, t?.location?.floor, planKey);

  async function update(body: Record<string, unknown>) {
    if (!t) return;
    setBusy(true);
    try {
      setT(await api<TicketDetail>(`/api/tickets/${t.id}`, jsonBody({ actor: "dispatcher", ...body }, "PATCH")));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Update failed");
    } finally {
      setBusy(false);
    }
  }

  if (error && !t) {
    return (
      <div className="mx-auto max-w-5xl px-4 py-10">
        <p role="alert" className="text-destructive">{error}</p>
        <Link href="/tickets" className="mt-4 inline-flex items-center gap-1 text-sm text-primary hover:underline">
          <ArrowLeft className="size-4" /> Back to queue
        </Link>
      </div>
    );
  }
  if (!t) {
    return (
      <div className="mx-auto max-w-6xl space-y-4 px-4 py-6">
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  const photos = t.reports.filter((r) => r.photo_url);
  const openHazard = t.is_hazard && t.status !== "resolved" && t.status !== "closed";
  const firstReport = t.reports[0];

  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <Link href="/tickets" className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" aria-hidden="true" /> Queue
      </Link>

      {openHazard && (
        <div role="alert" className="mt-3 flex items-center gap-2 rounded-lg border-2 border-hazard bg-hazard-soft px-4 py-3 font-semibold text-hazard">
          <Siren className="size-5" aria-hidden="true" /> P1 hazard: keep people away and follow the safety procedure.
        </div>
      )}

      <header className="mt-3 flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-sm text-muted-foreground">{t.short_code}</span>
            <PriorityBadge priority={t.priority} />
            {t.is_hazard && <HazardBadge hazardType={t.hazard_type} />}
            <StatusBadge status={t.status} />
            <ReportCountBadge count={t.report_count} />
            {t.source === "seed" && <span className="text-xs text-muted-foreground">(synthetic history)</span>}
          </div>
          <h1 className="mt-1.5 text-2xl font-bold tracking-tight">{t.title}</h1>
          <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
            <span className="inline-flex items-center gap-1">
              <MapPin className="size-4" aria-hidden="true" /> {locationLine(t.location, t.location_text)}
            </span>
            <span>{t.category_label}</span>
            <SeverityMeter severity={t.severity} />
            <span>Opened {timeAgo(t.created_at)}</span>
          </p>
        </div>
        <Card className="shrink-0 lg:w-80">
          <CardContent className="space-y-3 pt-5 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Team</span>
              <TradeLabel trade={t.trade} team={t.team?.name} />
            </div>
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">SLA</span>
              <SlaCountdown due={t.sla_due_at} status={t.status} />
            </div>
            {firstReport?.latency_ms != null && t.source !== "seed" && (
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Photo → ticket</span>
                <span className="inline-flex items-center gap-1 font-medium">
                  <Timer className="size-3.5" aria-hidden="true" /> {formatSeconds(firstReport.latency_ms)}
                </span>
              </div>
            )}
            <form
              className="flex gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                update({ assignee });
              }}
            >
              <Input value={assignee} onChange={(e) => setAssignee(e.target.value)} placeholder="Assign technician…" aria-label="Assignee" />
              <Button type="submit" size="sm" variant="outline" disabled={busy} aria-label="Assign">
                <UserCheck />
              </Button>
            </form>
            <div className="flex flex-wrap gap-1.5" role="group" aria-label="Change status">
              {FLOW.map((s) => (
                <Button
                  key={s}
                  size="sm"
                  variant={t.status === s ? "default" : "outline"}
                  disabled={busy || t.status === s}
                  onClick={() => update({ status: s })}
                  aria-pressed={t.status === s}
                >
                  {STATUS_LABEL[s]}
                </Button>
              ))}
            </div>
          </CardContent>
        </Card>
      </header>

      <div className="mt-6 grid gap-6 lg:grid-cols-[1fr_380px]">
        <div className="space-y-6">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Summary</CardTitle>
            </CardHeader>
            <CardContent className="text-sm leading-relaxed">{t.summary}</CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">
                Photos &amp; reports <span className="font-normal text-muted-foreground">({t.reports.length})</span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {photos.length > 0 ? (
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                  {photos.map((r) => (
                    <a key={r.id} href={r.photo_url!} target="_blank" rel="noreferrer" className="group block overflow-hidden rounded-lg border">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={r.photo_url!} alt={r.text ?? "Report photo"} className="aspect-[4/3] w-full object-cover transition-transform group-hover:scale-105" />
                    </a>
                  ))}
                </div>
              ) : (
                <p className="flex items-center gap-2 text-sm text-muted-foreground">
                  <ImageOff className="size-4" aria-hidden="true" /> No photos attached.
                </p>
              )}
              <ul className="space-y-2">
                {t.reports.map((r, i) => (
                  <li key={r.id} className="rounded-md border px-3 py-2 text-sm">
                    <div className="flex flex-wrap justify-between gap-2 text-xs text-muted-foreground">
                      <span>Report #{i + 1} · {timeAgo(r.created_at)}</span>
                      <span>
                        {r.llm_mode === "seed" ? "synthetic" : r.llm_mode}
                        {r.extraction_confidence != null && r.llm_mode !== "seed" && ` · confidence ${r.extraction_confidence.toFixed(2)}`}
                      </span>
                    </div>
                    <p className="mt-1">{r.text || r.transcript || <em className="text-muted-foreground">Photo only</em>}</p>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>

          <TechnicianBrief ticket={t} onGenerated={load} />

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">AI decision log</CardTitle>
              <p className="text-sm text-muted-foreground">Every automated decision and why it was made.</p>
            </CardHeader>
            <CardContent>
              <DecisionLog events={t.events} />
            </CardContent>
          </Card>
        </div>

        <aside className="space-y-6">
          {t.location && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Location</CardTitle>
              </CardHeader>
              <CardContent>
                <FloorPlan data={floor} highlight={t.location.id} labelScale={2.2} />
              </CardContent>
            </Card>
          )}
          {t.asset && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Asset</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <div>
                  <p className="font-medium">{t.asset.name}</p>
                  <p className="text-muted-foreground">
                    {t.asset.tag}
                    {t.asset.make && ` · ${t.asset.make} ${t.asset.model ?? ""}`}
                  </p>
                </div>
                <div>
                  <p className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">History</p>
                  {history.length === 0 ? (
                    <p className="text-muted-foreground">No other tickets on this asset.</p>
                  ) : (
                    <ul className="space-y-1.5">
                      {history.map((h) => (
                        <li key={h.id}>
                          <Link href={`/tickets/${h.short_code}`} className="hover:underline">
                            <span className="font-mono text-xs text-muted-foreground">{h.short_code}</span> {h.title}
                          </Link>
                          <span className="block text-xs text-muted-foreground">
                            {timeAgo(h.created_at)} · {STATUS_LABEL[h.status]}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </CardContent>
            </Card>
          )}
        </aside>
      </div>
    </div>
  );
}
