"use client";

import { useCallback, useEffect, useState } from "react";
import { BookOpen, History, LoaderCircle, RefreshCw, ShieldAlert, Sparkles, Wrench } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, type TechBrief, type TicketDetail } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { cn } from "@/lib/utils";

function Citation({ citation }: { citation: string | null }) {
  if (!citation) return <span className="ml-1 text-[11px] text-muted-foreground">(no SOP citation)</span>;
  const label = citation.replace(/^SOP:\s*/, "");
  return (
    <span className="ml-1 inline-flex items-center gap-1 rounded border px-1.5 py-px align-middle text-[11px] font-medium text-muted-foreground" title={citation}>
      <BookOpen className="size-3" aria-hidden="true" />
      {label}
    </span>
  );
}

const LIKELIHOOD: Record<string, string> = {
  high: "border-p1/40 text-p1",
  medium: "border-p2/40 text-p2",
  low: "border-p4/40 text-p4",
};

/** Technician brief: likely causes, tools, SOP-cited safety + steps, asset-history note. Generated on open. */
export function TechnicianBrief({ ticket, onGenerated }: { ticket: TicketDetail; onGenerated?: () => void }) {
  const [brief, setBrief] = useState<TechBrief | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (refresh = false) => {
      setLoading(true);
      setError(null);
      try {
        const hadBrief = Boolean(ticket.brief);
        setBrief(await api<TechBrief>(`/api/tickets/${ticket.id}/brief${refresh ? "?refresh=true" : ""}`));
        if (refresh || !hadBrief) onGenerated?.();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not generate the brief");
      } finally {
        setLoading(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [ticket.id],
  );

  useEffect(() => {
    load(false);
  }, [load]);

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0 pb-2">
        <div>
          <CardTitle className="flex items-center gap-2 text-base">
            <Sparkles className="size-4 text-primary" aria-hidden="true" /> Technician brief
          </CardTitle>
          <p className="text-sm text-muted-foreground">Written from SOPs and this asset&apos;s history. Steps cite their source.</p>
        </div>
        <Button variant="outline" size="sm" onClick={() => load(true)} disabled={loading}>
          {loading ? <LoaderCircle className="animate-spin" /> : <RefreshCw />} Regenerate
        </Button>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        {!brief && loading && (
          <div className="space-y-2" aria-label="Writing brief">
            <p className="flex items-center gap-2 text-sm text-primary">
              <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> Reading SOPs and asset history…
            </p>
            <Skeleton className="h-4 w-4/5" />
            <Skeleton className="h-4 w-3/5" />
            <Skeleton className="h-20 w-full" />
          </div>
        )}
        {brief && (
          <div className={cn("space-y-4 text-sm", loading && "opacity-60")}>
            <p className="font-medium">{brief.summary}</p>
            {brief.sop_coverage === "none" && (
              <p className="rounded-md border border-p2/40 px-3 py-2 text-p2">
                No matching SOP for this job. General diagnostic guidance only.
              </p>
            )}
            {brief.history_note && (
              <p className="flex gap-2 rounded-md bg-accent px-3 py-2 text-accent-foreground">
                <History className="mt-0.5 size-4 shrink-0" aria-hidden="true" /> {brief.history_note}
              </p>
            )}

            <section>
              <h4 className="mb-1.5 font-semibold">Likely causes</h4>
              <ol className="space-y-1.5">
                {brief.likely_causes.map((c, i) => (
                  <li key={i} className="flex gap-2">
                    <span className={cn("h-fit rounded border px-1.5 text-[11px] font-semibold uppercase", LIKELIHOOD[c.likelihood])}>
                      {c.likelihood}
                    </span>
                    <span>
                      <span className="font-medium">{c.cause}.</span> <span className="text-muted-foreground">{c.reasoning}</span>
                    </span>
                  </li>
                ))}
              </ol>
            </section>

            {brief.safety.length > 0 && (
              <section>
                <h4 className="mb-1.5 flex items-center gap-1.5 font-semibold">
                  <ShieldAlert className="size-4 text-hazard" aria-hidden="true" /> Safety first
                </h4>
                <ul className="ml-4 list-disc space-y-1">
                  {brief.safety.map((s, i) => (
                    <li key={i}>
                      {s.text}
                      <Citation citation={s.citation} />
                    </li>
                  ))}
                </ul>
              </section>
            )}

            {brief.tools_parts.length > 0 && (
              <section>
                <h4 className="mb-1.5 flex items-center gap-1.5 font-semibold">
                  <Wrench className="size-4 text-muted-foreground" aria-hidden="true" /> Tools &amp; parts
                </h4>
                <ul className="grid gap-1 sm:grid-cols-2">
                  {brief.tools_parts.map((t, i) => (
                    <li key={i}>
                      <label className="flex items-start gap-2">
                        <input type="checkbox" className="mt-0.5 size-4 accent-[hsl(var(--primary))]" /> {t}
                      </label>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <section>
              <h4 className="mb-1.5 font-semibold">Procedure</h4>
              <ol className="ml-5 list-decimal space-y-1.5">
                {brief.steps.map((s, i) => (
                  <li key={i}>
                    {s.text}
                    <Citation citation={s.citation} />
                  </li>
                ))}
              </ol>
            </section>

            <p className="border-t pt-2 text-xs text-muted-foreground">
              Sources: {brief.sources.length ? Array.from(new Set(brief.sources.map((s) => s.title))).join(", ") : "none"} ·
              written {timeAgo(brief.generated_at)} · {brief.llm_mode === "live" ? "Claude" : brief.llm_mode === "mock" ? "offline demo mode" : brief.llm_mode}
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
