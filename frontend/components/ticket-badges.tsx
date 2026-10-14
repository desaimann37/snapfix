"use client";

import {
  Archive,
  ArrowUpDown,
  CircleCheck,
  CircleDashed,
  Clock,
  DoorOpen,
  Droplets,
  ListChecks,
  LoaderCircle,
  MonitorSpeaker,
  ShieldAlert,
  SprayCan,
  Thermometer,
  Trees,
  TriangleAlert,
  UserCheck,
  Users,
  Wrench,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { Priority, Status } from "@/lib/api";
import { PRIORITY_LABEL, STATUS_LABEL, slaState, titleCase } from "@/lib/format";
import { cn } from "@/lib/utils";

const PRIORITY_STYLE: Record<Priority, string> = {
  P1: "border-p1/40 bg-p1/10 text-p1",
  P2: "border-p2/40 bg-p2/10 text-p2",
  P3: "border-p3/40 bg-p3/10 text-p3",
  P4: "border-p4/40 bg-p4/10 text-p4",
};

export function PriorityBadge({ priority, className }: { priority: Priority; className?: string }) {
  return (
    <Badge variant="outline" className={cn(PRIORITY_STYLE[priority], className)} title={`Priority ${priority}`}>
      <span className="font-bold">{priority}</span>
      <span className="font-medium">{PRIORITY_LABEL[priority]}</span>
    </Badge>
  );
}

const STATUS_ICON: Record<Status, LucideIcon> = {
  new: CircleDashed,
  triaged: ListChecks,
  assigned: UserCheck,
  in_progress: LoaderCircle,
  resolved: CircleCheck,
  closed: Archive,
};

export function StatusBadge({ status }: { status: Status }) {
  const Icon = STATUS_ICON[status] ?? CircleDashed;
  const done = status === "resolved" || status === "closed";
  return (
    <Badge variant="outline" className={cn("font-medium", done ? "text-success" : "text-foreground")}>
      <Icon aria-hidden="true" />
      {STATUS_LABEL[status] ?? status}
    </Badge>
  );
}

export function HazardBadge({ hazardType, className }: { hazardType?: string | null; className?: string }) {
  return (
    <Badge variant="hazard" className={cn("uppercase tracking-wide", className)}>
      <TriangleAlert aria-hidden="true" />
      Hazard{hazardType ? ` · ${titleCase(hazardType)}` : ""}
    </Badge>
  );
}

export function ReportCountBadge({ count }: { count: number }) {
  if (count <= 1) return <span className="text-xs text-muted-foreground">1 report</span>;
  return (
    <Badge variant="secondary" title={`${count} people reported this`}>
      <Users aria-hidden="true" />
      {count} reports
    </Badge>
  );
}

export function SlaCountdown({ due, status, now }: { due: string | null; status: Status; now?: number }) {
  const { state, label } = slaState(due, status, now);
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 text-xs font-medium",
        state === "overdue" && "text-p1",
        state === "soon" && "text-p2",
        state === "ok" && "text-muted-foreground",
        state === "done" && "text-success",
      )}
    >
      <Clock className="size-3.5" aria-hidden="true" />
      {label}
    </span>
  );
}

export const TRADE_ICON: Record<string, LucideIcon> = {
  Plumbing: Droplets,
  Electrical: Zap,
  HVAC: Thermometer,
  "Carpentry/Doors & Locks": DoorOpen,
  Custodial: SprayCan,
  Grounds: Trees,
  Elevator: ArrowUpDown,
  "IT/AV": MonitorSpeaker,
  "Safety/Environmental": ShieldAlert,
  General: Wrench,
};

export function TradeLabel({ trade, team }: { trade: string; team?: string | null }) {
  const Icon = TRADE_ICON[trade] ?? Wrench;
  return (
    <span className="flex min-w-0 max-w-[200px] items-center gap-1.5 text-sm" title={team ?? trade}>
      <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
      <span className="min-w-0 truncate">{team ?? trade}</span>
    </span>
  );
}

export function SeverityMeter({ severity }: { severity: number }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground" title={`Severity ${severity} of 4`}>
      <span className="flex gap-0.5" aria-hidden="true">
        {[1, 2, 3, 4].map((n) => (
          <span key={n} className={cn("h-3 w-1.5 rounded-sm", n <= severity ? "bg-foreground/70" : "bg-muted")} />
        ))}
      </span>
      Sev {severity}
    </span>
  );
}
