"use client";

import { useEffect, useState } from "react";
import { Check, MapPin, Search } from "lucide-react";
import { Input } from "@/components/ui/input";
import { api, qs, type LocationRef } from "@/lib/api";
import { cn } from "@/lib/utils";

export function locationName(loc: LocationRef) {
  const room = /^\d/.test(loc.room) ? ` · ${loc.room}` : "";
  return `${loc.label}${room}`;
}

/** Quick picks (AI candidates) + a searchable list of all campus locations. */
export function LocationPicker({
  value,
  onChange,
  candidates = [],
  autoFocus = false,
}: {
  value: LocationRef | null;
  onChange: (loc: LocationRef) => void;
  candidates?: LocationRef[];
  autoFocus?: boolean;
}) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<LocationRef[]>([]);

  useEffect(() => {
    if (!q.trim()) {
      setResults([]);
      return;
    }
    const t = setTimeout(() => {
      api<LocationRef[]>(`/api/locations/search${qs({ q, limit: 8 })}`).then(setResults).catch(() => setResults([]));
    }, 150);
    return () => clearTimeout(t);
  }, [q]);

  const list = q.trim() ? results : candidates;
  return (
    <div className="space-y-2">
      <div className="relative">
        <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" aria-hidden="true" />
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search room number, building or place…"
          className="h-10 pl-8"
          aria-label="Search locations"
          autoFocus={autoFocus}
        />
      </div>
      {list.length > 0 && (
        <ul className="max-h-64 space-y-1 overflow-y-auto" role="listbox" aria-label="Locations">
          {list.map((loc) => {
            const selected = value?.id === loc.id;
            return (
              <li key={loc.id}>
                <button
                  type="button"
                  role="option"
                  aria-selected={selected}
                  onClick={() => onChange(loc)}
                  className={cn(
                    "flex w-full items-center gap-2 rounded-md border px-3 py-2 text-left text-sm transition-colors hover:bg-accent",
                    selected && "border-primary bg-accent",
                  )}
                >
                  <MapPin className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium">{locationName(loc)}</span>
                    <span className="block truncate text-xs text-muted-foreground">
                      {loc.building_name} · floor {loc.floor}
                    </span>
                  </span>
                  {selected && <Check className="size-4 text-primary" aria-hidden="true" />}
                </button>
              </li>
            );
          })}
        </ul>
      )}
      {q.trim() && results.length === 0 && <p className="text-sm text-muted-foreground">No matching locations.</p>}
    </div>
  );
}
