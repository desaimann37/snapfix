import type { LucideIcon } from "lucide-react";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function compact(n: number): string {
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, "")}M`;
  if (Math.abs(n) >= 1_000) return `${(n / 1_000).toFixed(1).replace(/\.0$/, "")}K`;
  return n.toLocaleString();
}

/** Stat tile: label (sentence case) · value (semibold, proportional figures) · optional detail line. */
export function StatTile({
  label,
  value,
  detail,
  icon: Icon,
  tone = "default",
  className,
}: {
  label: string;
  value: string;
  detail?: React.ReactNode;
  icon?: LucideIcon;
  tone?: "default" | "critical";
  className?: string;
}) {
  return (
    <Card className={cn("p-4", tone === "critical" && "border-hazard/50 bg-hazard-soft", className)}>
      <p className={cn("flex items-center gap-1.5 text-sm text-muted-foreground", tone === "critical" && "text-hazard")}>
        {Icon && <Icon className="size-4" aria-hidden="true" />}
        {label}
      </p>
      <p className="mt-1 text-2xl font-semibold tracking-tight">{value}</p>
      {detail && <div className="mt-1 text-xs text-muted-foreground">{detail}</div>}
    </Card>
  );
}

/** The one hero figure a view leads with (>= 48px, same sans). */
export function HeroFigure({ label, value, detail }: { label: string; value: string; detail?: React.ReactNode }) {
  return (
    <Card className="flex flex-col justify-center p-5">
      <p className="text-sm font-medium text-muted-foreground">{label}</p>
      <p className="mt-1 text-5xl font-semibold leading-none tracking-tight">{value}</p>
      {detail && <div className="mt-2 text-sm text-muted-foreground">{detail}</div>}
    </Card>
  );
}
