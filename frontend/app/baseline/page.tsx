"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ArrowRight, Timer } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input, Label, Select, Textarea } from "@/components/ui/input";
import { api, jsonBody, type Building } from "@/lib/api";

// A deliberately typical legacy work-order portal (14 fields), used to measure time-to-report against SnapFix.
const PROBLEM_CODES = [
  "ACC-0101 Access Control - Card Reader - Malfunction", "ACC-0102 Access Control - Keypad", "AV-0201 AV - Projector - No Image",
  "AV-0202 AV - Projector - Lamp", "AV-0203 AV - Audio - Microphone", "CAR-0301 Carpentry - Door - Closer", "CAR-0302 Carpentry - Door - Hinge",
  "CAR-0303 Carpentry - Door - Lockset", "CAR-0304 Carpentry - Furniture - Chair", "CAR-0305 Carpentry - Furniture - Table",
  "CAR-0306 Carpentry - Window - Glass", "CUS-0401 Custodial - Spill", "CUS-0402 Custodial - Trash/Recycling", "CUS-0403 Custodial - Restroom Supplies",
  "CUS-0404 Custodial - Graffiti", "ELE-0501 Electrical - Lighting - Fixture Out", "ELE-0502 Electrical - Lighting - Flicker",
  "ELE-0503 Electrical - Receptacle - No Power", "ELE-0504 Electrical - Receptacle - GFCI", "ELE-0505 Electrical - Panel/Breaker",
  "ELV-0601 Elevator - Out of Service", "ELV-0602 Elevator - Door", "GEN-0701 General - Ceiling Tile", "GEN-0702 General - Signage",
  "GRD-0801 Grounds - Snow/Ice", "GRD-0802 Grounds - Tree/Limb", "HVA-0901 HVAC - Too Hot", "HVA-0902 HVAC - Too Cold",
  "HVA-0903 HVAC - Noise", "HVA-0904 HVAC - Thermostat", "PLM-1001 Plumbing - Faucet - Drip", "PLM-1002 Plumbing - Faucet - Leak at Base",
  "PLM-1003 Plumbing - Drain - Slow", "PLM-1004 Plumbing - Drain - Clogged", "PLM-1005 Plumbing - Toilet - Running",
  "PLM-1006 Plumbing - Toilet - Clogged", "PLM-1007 Plumbing - Urinal", "PLM-1008 Plumbing - Water Fountain", "PLM-1009 Plumbing - Pipe Leak",
  "SAF-1101 Safety - Odor", "SAF-1102 Safety - Mold", "SAF-1103 Safety - Chemical", "PST-1201 Pest - Insects", "PST-1202 Pest - Rodents",
];
const ASSET_TYPES = ["Air Handler", "Bottle Filler", "Card Reader", "Ceiling Tile", "Chair", "Door", "Door Closer", "Drain", "Elevator",
  "Faucet", "Fume Hood", "GFCI Receptacle", "Hand Dryer", "Light Fixture", "Lockset", "Projector", "Receptacle", "Sink", "Table",
  "Thermostat", "Toilet", "Urinal", "Water Heater", "Window", "Other / Unknown"];
const DEPARTMENTS = ["Academic Affairs", "Athletics", "Biology", "Chemistry", "Computer Science", "Engineering", "Facilities",
  "Housing", "Library Services", "Student Life", "Other"];

export default function BaselinePage() {
  const started = useRef(0);
  const [elapsed, setElapsed] = useState(0);
  const [done, setDone] = useState<number | null>(null);
  const [buildings, setBuildings] = useState<Building[]>([]);
  const [participant, setParticipant] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    started.current = performance.now();
    api<Building[]>("/api/buildings").then(setBuildings).catch(() => undefined);
    const t = setInterval(() => setElapsed(performance.now() - started.current), 250);
    return () => clearInterval(t);
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const seconds = (performance.now() - started.current) / 1000;
    setDone(seconds);
    try {
      await api("/api/eval/timing", jsonBody({ flow: "baseline", seconds, participant: participant || null, notes: "legacy form" }));
    } catch {
      setError("Couldn't save the timing, but you can note it manually.");
    }
  }

  const shown = (done ?? elapsed / 1000).toFixed(0);
  return (
    <div className="mx-auto max-w-3xl px-4 py-6">
      <div className="sticky top-16 z-10 flex items-center justify-between rounded-lg border bg-card px-4 py-2 shadow-sm">
        <p className="text-sm">
          <strong>Legacy work-order form</strong> <span className="text-muted-foreground">(for comparison; files no real ticket)</span>
        </p>
        <span className="inline-flex items-center gap-1.5 font-mono text-lg font-semibold tabular-nums" role="timer" aria-live="off">
          <Timer className="size-5 text-p2" aria-hidden="true" /> {Math.floor(Number(shown) / 60)}:{String(Number(shown) % 60).padStart(2, "0")}
        </span>
      </div>

      {done !== null ? (
        <Card className="mt-6">
          <CardContent className="space-y-3 pt-6 text-center">
            <p className="text-sm text-muted-foreground">You reported it with the legacy form in</p>
            <p className="text-5xl font-semibold">{Math.floor(done / 60)}m {String(Math.round(done % 60)).padStart(2, "0")}s</p>
            {error && <p className="text-sm text-destructive">{error}</p>}
            <p className="text-sm text-muted-foreground">Now report the same problem with SnapFix:</p>
            <Button asChild size="lg">
              <Link href={`/report?study=${encodeURIComponent(participant || "volunteer")}`}>
                Try SnapFix <ArrowRight />
              </Link>
            </Button>
          </CardContent>
        </Card>
      ) : (
        <form onSubmit={submit} className="mt-6 grid gap-4 rounded-lg border bg-card p-5 sm:grid-cols-2">
          <h1 className="text-xl font-semibold sm:col-span-2">Facilities Service Request (Form FM-12)</h1>
          <p className="text-sm text-muted-foreground sm:col-span-2">All fields marked * are required.</p>
          <Field label="1. Requester full name *"><Input required autoComplete="off" /></Field>
          <Field label="2. Requester email *"><Input type="email" required autoComplete="off" /></Field>
          <Field label="3. Phone number *"><Input type="tel" required autoComplete="off" /></Field>
          <Field label="4. Department *">
            <Select required defaultValue="">
              <option value="" disabled>Select…</option>
              {DEPARTMENTS.map((d) => <option key={d}>{d}</option>)}
            </Select>
          </Field>
          <Field label="5. Building *">
            <Select required defaultValue="">
              <option value="" disabled>Select…</option>
              {buildings.map((b) => <option key={b.code}>{b.code} - {b.name}</option>)}
            </Select>
          </Field>
          <Field label="6. Floor *"><Input required inputMode="numeric" /></Field>
          <Field label="7. Room number *"><Input required /></Field>
          <Field label="8. Asset type *">
            <Select required defaultValue="">
              <option value="" disabled>Select…</option>
              {ASSET_TYPES.map((a) => <option key={a}>{a}</option>)}
            </Select>
          </Field>
          <Field label="9. Problem code *" wide>
            <Select required defaultValue="">
              <option value="" disabled>Select the matching problem code…</option>
              {PROBLEM_CODES.map((c) => <option key={c}>{c}</option>)}
            </Select>
          </Field>
          <Field label="10. Priority requested *">
            <Select required defaultValue="">
              <option value="" disabled>Select…</option>
              <option>1 - Emergency (life safety)</option>
              <option>2 - Urgent (24 hours)</option>
              <option>3 - Routine (5 business days)</option>
              <option>4 - Scheduled</option>
            </Select>
          </Field>
          <Field label="11. Best time to contact *">
            <Select required defaultValue="">
              <option value="" disabled>Select…</option>
              <option>Morning</option>
              <option>Afternoon</option>
              <option>Any time</option>
            </Select>
          </Field>
          <Field label="12. Short description (max 60 characters) *" wide><Input required maxLength={60} /></Field>
          <Field label="13. Detailed description *" wide><Textarea required rows={3} /></Field>
          <Field label="14. Attachment (optional)" wide><Input type="file" /></Field>
          <label className="flex items-start gap-2 text-sm sm:col-span-2">
            <input type="checkbox" required className="mt-0.5 size-4" /> I confirm this is not an emergency and the information above is accurate. *
          </label>
          <div className="flex flex-wrap items-end gap-3 border-t pt-4 sm:col-span-2">
            <div className="space-y-1">
              <Label htmlFor="participant" className="text-xs text-muted-foreground">Study participant label (optional, not part of the form)</Label>
              <Input id="participant" value={participant} onChange={(e) => setParticipant(e.target.value)} placeholder="e.g. Volunteer 3" className="w-48" />
            </div>
            <Button type="submit" className="ml-auto">Submit request</Button>
          </div>
        </form>
      )}
    </div>
  );
}

function Field({ label, wide = false, children }: { label: string; wide?: boolean; children: React.ReactNode }) {
  return (
    <label className={wide ? "space-y-1.5 sm:col-span-2" : "space-y-1.5"}>
      <span className="text-sm font-medium">{label}</span>
      {children}
    </label>
  );
}
