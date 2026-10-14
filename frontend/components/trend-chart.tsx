"use client";

import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { TrendData } from "@/lib/api";

const MAX_SERIES = 4; // categorical slots 1-4 (validated); the tail folds into "Other"
const SERIES_VARS = ["var(--series-1)", "var(--series-2)", "var(--series-3)", "var(--series-4)"];
const OTHER = "Other";

type Row = { date: string; label: string } & Record<string, number | string>;

function shortDate(iso: string) {
  const d = new Date(`${iso}T12:00:00`);
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function useTrendSeries(data: TrendData | null) {
  return useMemo(() => {
    if (!data) return { series: [] as string[], rows: [] as Row[], colors: {} as Record<string, string> };
    const top = data.trades.slice(0, MAX_SERIES);
    const tail = data.trades.slice(MAX_SERIES);
    const series = tail.length ? [...top, OTHER] : top;
    // Color follows the entity (trade), assigned by overall volume order - stable across days.
    const colors: Record<string, string> = Object.fromEntries(top.map((t, i) => [t, SERIES_VARS[i]]));
    colors[OTHER] = "var(--series-other)";
    const rows: Row[] = data.days.map((d) => {
      const row: Row = { date: d.date, label: shortDate(d.date) };
      top.forEach((t) => (row[t] = Number(d[t] ?? 0)));
      if (tail.length) row[OTHER] = tail.reduce((sum, t) => sum + Number(d[t] ?? 0), 0);
      return row;
    });
    return { series, rows, colors };
  }, [data]);
}

function ChartTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: { dataKey: string; value: number; color: string }[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  const total = payload.reduce((s, p) => s + (Number(p.value) || 0), 0);
  return (
    <div className="min-w-[180px] rounded-md border bg-card px-3 py-2 text-xs shadow-md">
      <p className="mb-1 font-medium text-muted-foreground">{label}</p>
      <ul className="space-y-0.5">
        {[...payload].reverse().map((p) => (
          <li key={p.dataKey} className="flex items-center gap-2">
            <span className="h-0.5 w-3 rounded-full" style={{ background: p.color }} aria-hidden="true" />
            <span className="font-semibold tabular-nums text-foreground">{p.value}</span>
            <span className="text-muted-foreground">{p.dataKey}</span>
          </li>
        ))}
      </ul>
      <p className="mt-1 border-t pt-1 text-muted-foreground">
        <span className="font-semibold text-foreground">{total}</span> reports
      </p>
    </div>
  );
}

/** Reports per day by trade: stacked columns, 2px surface gap, 24px max width, legend + table view. */
export function TrendChart({ data }: { data: TrendData | null }) {
  const { series, rows, colors } = useTrendSeries(data);
  const [table, setTable] = useState(false);
  if (!data) return <div className="h-[280px] animate-pulse rounded-md bg-muted" aria-hidden="true" />;

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground" aria-label="Legend">
          {series.map((s) => (
            <li key={s} className="flex items-center gap-1.5">
              <span className="size-2.5 rounded-sm" style={{ background: colors[s] }} aria-hidden="true" />
              {s}
            </li>
          ))}
        </ul>
        <button onClick={() => setTable((t) => !t)} className="text-xs font-medium text-primary hover:underline" aria-pressed={table}>
          {table ? "View as chart" : "View as table"}
        </button>
      </div>
      {table ? (
        <div className="max-h-[280px] overflow-auto">
          <table className="w-full text-xs">
            <caption className="sr-only">Reports per day by trade</caption>
            <thead className="sticky top-0 bg-card text-left text-muted-foreground">
              <tr>
                <th scope="col" className="py-1 pr-3 font-medium">Day</th>
                {series.map((s) => (
                  <th key={s} scope="col" className="py-1 pr-3 text-right font-medium">{s}</th>
                ))}
              </tr>
            </thead>
            <tbody className="tabular-nums">
              {rows.map((r) => (
                <tr key={r.date} className="border-t">
                  <th scope="row" className="py-1 pr-3 text-left font-normal">{r.label}</th>
                  {series.map((s) => (
                    <td key={s} className="py-1 pr-3 text-right">{r[s]}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="h-[280px]" role="img" aria-label="Stacked column chart of reports per day by trade for the last 14 days">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={rows} margin={{ top: 4, right: 4, bottom: 0, left: -18 }} barCategoryGap="22%">
              <CartesianGrid vertical={false} stroke="var(--chart-grid)" strokeWidth={1} />
              <XAxis
                dataKey="label"
                tickLine={false}
                axisLine={{ stroke: "var(--chart-grid)" }}
                tick={{ fill: "var(--chart-axis)", fontSize: 11 }}
                interval="preserveStartEnd"
                minTickGap={16}
              />
              <YAxis allowDecimals={false} tickLine={false} axisLine={false} tick={{ fill: "var(--chart-axis)", fontSize: 11 }} />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: "var(--chart-grid)", opacity: 0.5 }} />
              {series.map((s, i) => (
                <Bar
                  key={s}
                  dataKey={s}
                  stackId="reports"
                  fill={colors[s]}
                  stroke="var(--chart-surface)"
                  strokeWidth={2}
                  maxBarSize={24}
                  radius={i === series.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]}
                  isAnimationActive={false}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
