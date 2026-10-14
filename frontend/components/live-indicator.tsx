import { Radio, WifiOff } from "lucide-react";
import { cn } from "@/lib/utils";

export function LiveIndicator({ state }: { state: "connecting" | "live" | "offline" }) {
  const label = state === "live" ? "Live" : state === "connecting" ? "Connecting…" : "Offline";
  return (
    <span
      role="status"
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium",
        state === "live" ? "border-success/40 text-success" : "text-muted-foreground",
      )}
    >
      {state === "offline" ? (
        <WifiOff className="size-3.5" aria-hidden="true" />
      ) : (
        <span className="relative flex size-2" aria-hidden="true">
          {state === "live" && <span className="absolute inline-flex size-full animate-ping rounded-full bg-success/60" />}
          <span className={cn("relative inline-flex size-2 rounded-full", state === "live" ? "bg-success" : "bg-muted-foreground")} />
        </span>
      )}
      <Radio className="sr-only" aria-hidden="true" />
      {label}
    </span>
  );
}
