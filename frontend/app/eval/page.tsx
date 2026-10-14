"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CircleAlert, FlaskConical, ShieldCheck, Timer, Users } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { HeroFigure, StatTile } from "@/components/stat-tile";
import { api, type EvalResult, type TimingStats } from "@/lib/api";
import { cn } from "@/lib/utils";

function pct(v: number | null | undefined) {
  return v == null ? "-" : `${(v * 100).toFixed(1)}%`;
}

function mmss(s: number | null | undefined) {
  if (s == null) return "-";
  const m = Math.floor(s / 60);
  const sec = Math.round(s % 60);
  return m ? `${m}m ${String(sec).padStart(2, "0")}s` : `${sec}s`;
}

function ms(v: number | null | undefined) {
  if (v == null) return "-";
  return v < 1000 ? `${Math.round(v)} ms` : `${(v / 1000).toFixed(1)} s`;
}

function heatStep(count: number, max: number): number {
  if (count <= 0) return 0;
  return Math.min(5, Math.max(1, Math.ceil((count / max) * 5)));
}

const SHORT: Record<string, string> = {
  "Carpentry/Doors & Locks": "Carpentry",
  "Safety/Environmental": "Safety/EHS",
};

export default function EvalPage() {
  const [data, setData] = useState<{ result: EvalResult | null; timing: TimingStats } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<{ result: EvalResult | null; timing: TimingStats }>("/api/eval/latest")
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load results"));
  }, []);

  const r = data?.result;
  const m = r?.metrics;
  const t = data?.timing;
  const misses = r?.items.filter((i) => i.pred.category !== i.true.category) ?? [];
  const labels = r?.confusion_trade.labels ?? [];
  const matrix = r?.confusion_trade.matrix ?? [];
  const max = Math.max(1, ...matrix.flat());

  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
            <FlaskConical className="size-6 text-primary" aria-hidden="true" /> How accurate is SnapFix?
          </h1>
          <p className="text-sm text-muted-foreground">
            Every number on this page is measured by <code className="rounded bg-muted px-1">make eval</code> on a labelled
            set, or recorded from real reports. Nothing is hand-entered.
          </p>
        </div>
      </div>

      {error && <p role="alert" className="mt-4 text-destructive">{error}</p>}
      {!data && !error && <Skeleton className="mt-6 h-96" />}

      {data && !r && (
        <Card className="mt-6">
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            No evaluation run yet. Run <code className="rounded bg-muted px-1">make eval</code> (or <code>make eval-mock</code>).
          </CardContent>
        </Card>
      )}

      {r && m && (
        <>
          {r.mode !== "live" && (
            <p role="note" className="mt-4 flex gap-2 rounded-lg border border-p2/40 bg-card px-4 py-3 text-sm">
              <CircleAlert className="mt-0.5 size-4 shrink-0 text-p2" aria-hidden="true" />
              <span>
                <strong>Offline run.</strong> {r.note} Hazard rules, location resolution and duplicate detection are the real
                pipeline either way.
              </span>
            </p>
          )}
          <p className="mt-3 text-xs text-muted-foreground">
            Run {r.run_id} · {r.n_items} labelled reports ({r.n_with_photo} with photos) · prompt {r.prompt_version} · models{" "}
            {r.models.main} / {r.models.fast} · embeddings {r.embedder}
          </p>

          <section aria-label="Headline results" className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <HeroFigure
              label="Hazard recall"
              value={pct(m.hazard_recall)}
              detail={<>{m.hazard_counts.tp} of {m.hazard_counts.tp + m.hazard_counts.fn} hazards escalated · must stay 100%</>}
            />
            <StatTile label="Category accuracy" value={pct(m.category_accuracy)} icon={ShieldCheck} detail={`keyword baseline ${pct(r.baseline.category_accuracy)}`} />
            <StatTile label="Duplicate detection F1" value={pct(m.dedupe_f1)} icon={Users} detail={`precision ${pct(m.dedupe_precision)} · recall ${pct(m.dedupe_recall)}`} />
            <StatTile
              label="Photo → ticket (server)"
              value={ms(m.latency_ms.p50)}
              icon={Timer}
              detail={`p95 ${ms(m.latency_ms.p95)} · cost/report $${(m.cost_per_report_usd ?? 0).toFixed(4)}`}
            />
          </section>

          <div className="mt-6 grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Accuracy by field</CardTitle>
              </CardHeader>
              <CardContent>
                <table className="w-full text-sm">
                  <caption className="sr-only">Accuracy by field, SnapFix vs keyword baseline</caption>
                  <thead className="text-left text-xs uppercase tracking-wide text-muted-foreground">
                    <tr>
                      <th scope="col" className="py-2 font-medium">Field</th>
                      <th scope="col" className="py-2 text-right font-medium">SnapFix</th>
                      <th scope="col" className="py-2 text-right font-medium">Keyword baseline</th>
                    </tr>
                  </thead>
                  <tbody className="tabular-nums">
                    {[
                      ["Category", m.category_accuracy, r.baseline.category_accuracy],
                      ["Trade (routing)", m.trade_accuracy, r.baseline.trade_accuracy],
                      ["Severity (exact)", m.severity_exact, r.baseline.severity_exact],
                      ["Severity (within ±1)", m.severity_within_1, r.baseline.severity_within_1],
                      ["Hazard recall", m.hazard_recall, null],
                      ["Hazard precision", m.hazard_precision, null],
                      [`Location (${m.location_items} items)`, m.location_accuracy, null],
                      [`Location from text/photo only (${m.location_items_without_qr})`, m.location_accuracy_without_qr, null],
                    ].map(([label, a, b]) => (
                      <tr key={String(label)} className="border-t">
                        <th scope="row" className="py-2 text-left font-normal">{label}</th>
                        <td className="py-2 text-right font-semibold">{pct(a as number | null)}</td>
                        <td className="py-2 text-right text-muted-foreground">{b == null ? "" : pct(b as number)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">Time to report: legacy form vs SnapFix</CardTitle>
                <p className="text-sm text-muted-foreground">
                  Measured with volunteers: <Link className="text-primary underline" href="/baseline">legacy form</Link> vs{" "}
                  <Link className="text-primary underline" href="/report">SnapFix</Link>, page open to submitted.
                </p>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-3">
                  <StatTile label="Legacy form (median)" value={mmss(t?.baseline.median_s)} detail={`${t?.baseline.n ?? 0} runs`} />
                  <StatTile label="SnapFix (median)" value={mmss(t?.snapfix.median_s)} detail={`${t?.snapfix.n ?? 0} runs`} />
                </div>
                {t?.speedup ? (
                  <p className="text-lg">
                    <strong>{t.speedup}× faster</strong> to report a problem with SnapFix.
                  </p>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    Need measurements from both flows: have volunteers report the same issue with the legacy form and with
                    SnapFix. Each completed run is recorded automatically.
                  </p>
                )}
              </CardContent>
            </Card>
          </div>

          <Card className="mt-6">
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Trade confusion matrix</CardTitle>
              <p className="text-sm text-muted-foreground">Rows = correct trade, columns = predicted. Darker = more reports; the diagonal is correct routing.</p>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              <table className="text-xs">
                <caption className="sr-only">Trade confusion matrix: rows are true trades, columns are predicted trades</caption>
                <thead>
                  <tr>
                    <th scope="col" className="p-1 text-left font-medium text-muted-foreground">True ↓ / Predicted →</th>
                    {labels.map((l) => (
                      <th key={l} scope="col" className="h-24 w-11 p-1 align-bottom font-medium text-muted-foreground">
                        <span className="inline-block whitespace-nowrap [writing-mode:vertical-rl] rotate-180">{SHORT[l] ?? l}</span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {labels.map((row, i) => (
                    <tr key={row}>
                      <th scope="row" className="whitespace-nowrap p-1 pr-2 text-left font-medium text-muted-foreground">{SHORT[row] ?? row}</th>
                      {matrix[i].map((n, j) => {
                        const step = heatStep(n, max);
                        return (
                          <td
                            key={j}
                            className={cn("h-9 w-11 border border-card text-center tabular-nums", i === j && "outline outline-1 -outline-offset-2 outline-foreground/30")}
                            style={step ? { background: `var(--heat-${step})`, color: `var(--heat-ink-${step})` } : undefined}
                            title={`${row} → ${labels[j]}: ${n}`}
                          >
                            {n || ""}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>

          <Card className="mt-6">
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Where it gets it wrong ({misses.length})</CardTitle>
            </CardHeader>
            <CardContent>
              {misses.length === 0 ? (
                <p className="text-sm text-muted-foreground">No misclassified items.</p>
              ) : (
                <ul className="space-y-1.5 text-sm">
                  {misses.map((i) => (
                    <li key={i.i} className="border-b pb-1.5 last:border-0">
                      “{i.text}” → <span className="font-medium">{i.pred.category}</span>
                      <span className="text-muted-foreground"> (expected {i.true.category})</span>
                    </li>
                  ))}
                </ul>
              )}
              <p className="mt-3 text-xs text-muted-foreground">
                Reproduce: <code className="rounded bg-muted px-1">make eval</code>. Add real photos to eval/dataset/images and
                reference them in labels.csv.
              </p>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
