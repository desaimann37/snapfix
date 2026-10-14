"use client";

import { useEffect, useState } from "react";
import { api, type Building, type LocationRef } from "@/lib/api";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

export interface FloorRoom extends LocationRef {
  open_count: number;
  hazard: boolean;
}

export interface FloorData {
  building: Building;
  floor: number;
  rooms: FloorRoom[];
}

function truncate(text: string, max: number) {
  return text.length > max ? `${text.slice(0, Math.max(1, max - 1))}…` : text;
}

export function useFloor(buildingCode?: string, floor?: number, refreshKey = 0) {
  const [data, setData] = useState<FloorData | null>(null);
  useEffect(() => {
    if (!buildingCode || !floor) return;
    api<FloorData>(`/api/buildings/${buildingCode}/floors/${floor}`).then(setData).catch(() => setData(null));
  }, [buildingCode, floor, refreshKey]);
  return data;
}

/**
 * Plain-SVG floor plan (viewBox 1000x400). `highlight` marks one room; `showCounts` draws pins sized by the
 * number of open tickets (hotspot view). Status is never color-only: hazard rooms also get a "!" glyph.
 */
export function FloorPlan({
  data,
  highlight,
  showCounts = false,
  onRoomClick,
  className,
  labelScale = 1,
}: {
  data: FloorData | null;
  highlight?: string | null;
  showCounts?: boolean;
  onRoomClick?: (room: FloorRoom) => void;
  className?: string;
  /** Enlarge text when the plan is rendered small (e.g. a sidebar). */
  labelScale?: number;
}) {
  if (!data) return <Skeleton className={cn("aspect-[5/2] w-full", className)} />;
  const max = Math.max(1, ...data.rooms.map((r) => r.open_count));
  return (
    <figure className={cn("w-full", className)}>
      <svg
        viewBox="0 0 1000 400"
        role="img"
        aria-label={`${data.building.name} floor ${data.floor} plan`}
        className="w-full rounded-lg border bg-muted/30"
      >
        <rect x="18" y="18" width="964" height="364" rx="10" className="fill-none stroke-border" strokeWidth="2" />
        {data.rooms.map((room) => {
          const active = highlight === room.id;
          const corridor = room.room_type === "corridor";
          const r = showCounts && room.open_count > 0 ? 10 + 18 * Math.sqrt(room.open_count / max) : 0;
          const cx = room.x + room.w / 2;
          const cy = room.y + room.h / 2;
          return (
            <g
              key={room.id}
              onClick={onRoomClick ? () => onRoomClick(room) : undefined}
              className={onRoomClick ? "cursor-pointer" : undefined}
            >
              <title>
                {room.label}
                {room.open_count ? `: ${room.open_count} open ticket${room.open_count > 1 ? "s" : ""}` : ""}
              </title>
              <rect
                x={room.x}
                y={room.y}
                width={room.w}
                height={room.h}
                rx="6"
                className={cn(
                  "stroke-border transition-colors",
                  corridor ? "fill-muted" : "fill-card",
                  room.hazard && "fill-hazard-soft stroke-hazard",
                  active && "fill-primary/15 stroke-primary",
                )}
                strokeWidth={active ? 4 : 1.5}
              />
              {!corridor && (
                <>
                  <text x={room.x + 10} y={room.y + 8 + 15 * labelScale} fontSize={15 * labelScale} className="fill-foreground font-semibold">
                    {/^\d/.test(room.room) ? room.room : ""}
                  </text>
                  <text x={room.x + 10} y={room.y + 14 + 32 * labelScale} fontSize={12 * labelScale} className="fill-muted-foreground">
                    {truncate(room.label, Math.floor(room.w / (7 * labelScale)))}
                  </text>
                </>
              )}
              {corridor && (
                <text x={room.x + 12} y={room.y + room.h / 2 + 4 * labelScale} fontSize={12 * Math.min(labelScale, 2)} className="fill-muted-foreground">
                  {room.label}
                </text>
              )}
              {r > 0 && (
                <g>
                  <circle
                    cx={cx}
                    cy={corridor ? room.y + room.h / 2 : cy + 12}
                    r={corridor ? Math.min(r, 16) : r}
                    className={room.hazard ? "fill-hazard/80" : "fill-primary/70"}
                  />
                  <text
                    x={cx}
                    y={(corridor ? room.y + room.h / 2 : cy + 12) + 5}
                    textAnchor="middle"
                    className="fill-white text-[13px] font-bold"
                  >
                    {room.hazard ? "!" : room.open_count}
                  </text>
                </g>
              )}
              {active && !showCounts && (
                <circle cx={room.x + room.w - 18} cy={corridor ? room.y + room.h / 2 : room.y + room.h - 18} r="10" className="animate-pulse fill-primary" />
              )}
            </g>
          );
        })}
      </svg>
      <figcaption className="mt-1.5 text-xs text-muted-foreground">
        {data.building.name} · floor {data.floor}
        {showCounts && " · circle size = open tickets, ! = hazard"}
      </figcaption>
    </figure>
  );
}
