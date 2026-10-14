"use client";

import { useEffect, useMemo, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { Printer } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input, Label, Select } from "@/components/ui/input";
import { api, type Building, type LocationRef } from "@/lib/api";

const BASE_KEY = "snapfix.qrBase";

/** Printable QR stickers for every seeded location. Each points to <public base URL>/r/<location code>. */
export default function QrSheetPage() {
  const [locations, setLocations] = useState<LocationRef[]>([]);
  const [buildings, setBuildings] = useState<Building[]>([]);
  const [building, setBuilding] = useState("");
  const [base, setBase] = useState("");

  useEffect(() => {
    api<LocationRef[]>("/api/locations/search?limit=200").then(setLocations).catch(() => undefined);
    api<Building[]>("/api/buildings").then(setBuildings).catch(() => undefined);
    let saved: string | null = null;
    try {
      saved = window.localStorage.getItem(BASE_KEY);
    } catch {
      /* storage unavailable */
    }
    setBase(saved || window.location.origin);
  }, []);

  function updateBase(value: string) {
    setBase(value);
    try {
      window.localStorage.setItem(BASE_KEY, value);
    } catch {
      /* ignore */
    }
  }

  const shown = useMemo(() => locations.filter((l) => !building || l.building_code === building), [locations, building]);
  const cleanBase = base.replace(/\/+$/, "");

  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <div className="no-print space-y-3">
        <h1 className="text-2xl font-bold tracking-tight">QR stickers</h1>
        <p className="text-sm text-muted-foreground">
          Print and stick one in each room. Scanning opens the report page with the location already filled in. Use your public
          HTTPS address (tunnel or deployment) so phones can reach it and use the camera.
        </p>
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-72 flex-1 space-y-1">
            <Label htmlFor="qr-base">Public base URL</Label>
            <Input id="qr-base" value={base} onChange={(e) => updateBase(e.target.value)} placeholder="https://snapfix.example.trycloudflare.com" />
          </div>
          <div className="space-y-1">
            <Label htmlFor="qr-building">Building</Label>
            <Select id="qr-building" value={building} onChange={(e) => setBuilding(e.target.value)} className="w-56">
              <option value="">All buildings ({locations.length})</option>
              {buildings.map((b) => (
                <option key={b.code} value={b.code}>{b.name}</option>
              ))}
            </Select>
          </div>
          <Button onClick={() => window.print()}>
            <Printer /> Print
          </Button>
        </div>
      </div>

      <div className="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-3 print:mt-0 print:grid-cols-3 print:gap-3">
        {shown.map((loc) => {
          const url = `${cleanBase}/r/${loc.qr_code}`;
          return (
            <div key={loc.id} className="flex break-inside-avoid flex-col items-center rounded-xl border-2 border-dashed p-4 text-center print:border-gray-400">
              <p className="text-sm font-bold uppercase tracking-wide">See a problem? Snap it.</p>
              <div className="my-3 rounded-md bg-white p-2">
                <QRCodeSVG value={url} size={132} level="M" marginSize={0} title={`QR code for ${loc.label}`} />
              </div>
              <p className="font-semibold leading-tight">{loc.label}</p>
              <p className="text-xs text-muted-foreground print:text-gray-600">
                {loc.building_name}
                {/^\d/.test(loc.room) ? ` · Room ${loc.room}` : ""}
              </p>
              <p className="mt-1 break-all font-mono text-[10px] text-muted-foreground print:text-gray-600">{url.replace(/^https?:\/\//, "")}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
