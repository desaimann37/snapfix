"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowRight,
  Camera,
  Check,
  CircleAlert,
  CircleCheck,
  ImageIcon,
  LoaderCircle,
  MapPin,
  Mic,
  Pencil,
  RotateCcw,
  Send,
  Siren,
  Sparkles,
  Square,
  Timer,
  Trash2,
  TriangleAlert,
  Users,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Input, Label, Select, Textarea } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { LocationPicker, locationName } from "@/components/location-picker";
import { PriorityBadge, SeverityMeter, TRADE_ICON } from "@/components/ticket-badges";
import {
  api,
  jsonBody,
  type ConfirmResponse,
  type IntakeResponse,
  type LocationRef,
  type Taxonomy,
} from "@/lib/api";
import { preparePhoto, type PreparedPhoto } from "@/lib/image";
import { useVoice } from "@/lib/speech";
import { cn } from "@/lib/utils";

type Phase = "compose" | "analyzing" | "review" | "editing" | "submitting" | "done";

const SEVERITY_LABEL: Record<number, string> = { 1: "Minor", 2: "Degraded", 3: "Blocks use", 4: "Danger" };
const ANALYZE_STEPS = ["Reading the photo…", "Classifying the issue…", "Finding the location…", "Checking for hazards…"];

function secs(ms: number | null | undefined) {
  if (ms === null || ms === undefined) return "-";
  return `${(ms / 1000).toFixed(1)} s`;
}

export function ReportFlow({ qrCode }: { qrCode?: string }) {
  const startedAt = useRef(0);
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [qrLocation, setQrLocation] = useState<LocationRef | null>(null);
  const [qrError, setQrError] = useState(false);
  const [photo, setPhoto] = useState<PreparedPhoto | null>(null);
  const [preparing, setPreparing] = useState(false);
  const [text, setText] = useState("");
  const [pickedLocation, setPickedLocation] = useState<LocationRef | null>(null);
  const [showPicker, setShowPicker] = useState(false);
  const [phase, setPhase] = useState<Phase>("compose");
  const [step, setStep] = useState(0);
  const [intake, setIntake] = useState<IntakeResponse | null>(null);
  const [location, setLocation] = useState<LocationRef | null>(null);
  const [title, setTitle] = useState("");
  const [category, setCategory] = useState("");
  const [severity, setSeverity] = useState<number>(2);
  const [taxonomy, setTaxonomy] = useState<Taxonomy | null>(null);
  const [result, setResult] = useState<ConfirmResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [study, setStudy] = useState<string | null>(null);
  const voice = useVoice((t) => setText((prev) => (prev ? `${prev} ${t}` : t)));

  useEffect(() => {
    startedAt.current = performance.now();
    api<Taxonomy>("/api/taxonomy").then(setTaxonomy).catch(() => undefined);
    // ?study=<label> marks a time-to-report study run (linked from the legacy-form page); only those are recorded.
    setStudy(new URLSearchParams(window.location.search).get("study"));
  }, []);

  useEffect(() => {
    if (!qrCode) return;
    api<LocationRef>(`/api/locations/${encodeURIComponent(qrCode)}`)
      .then(setQrLocation)
      .catch(() => setQrError(true));
  }, [qrCode]);

  useEffect(() => {
    headingRef.current?.focus();
  }, [phase]);

  useEffect(() => {
    if (phase !== "analyzing") return;
    setStep(0);
    const t = setInterval(() => setStep((s) => Math.min(s + 1, ANALYZE_STEPS.length - 1)), 1100);
    return () => clearInterval(t);
  }, [phase]);

  const ensureTaxonomy = useCallback(() => {
    if (!taxonomy) api<Taxonomy>("/api/taxonomy").then(setTaxonomy).catch(() => undefined);
  }, [taxonomy]);

  async function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setPreparing(true);
    try {
      setPhoto(await preparePhoto(file));
    } finally {
      setPreparing(false);
    }
  }

  const locationCode = qrCode || pickedLocation?.qr_code;
  const canSubmit = Boolean(photo || text.trim() || voice.audio) && !preparing && !voice.listening;

  async function submit() {
    setError(null);
    setPhase("analyzing");
    const fd = new FormData();
    if (photo) fd.append("image", photo.blob, "photo.jpg");
    if (text.trim()) fd.append("text", text.trim());
    if (voice.audio && !text.trim()) fd.append("audio", voice.audio, "voice.webm");
    if (locationCode) fd.append("location_code", locationCode);
    if (photo?.gps) {
      fd.append("lat", String(photo.gps.lat));
      fd.append("lng", String(photo.gps.lng));
    }
    const minShow = new Promise((r) => setTimeout(r, 700)); // avoid a skeleton flash; doesn't affect timing
    try {
      const res = await api<IntakeResponse>("/api/reports", { method: "POST", body: fd });
      await minShow;
      setIntake(res);
      setLocation(res.location);
      setTitle(res.draft.title);
      setCategory(res.draft.category);
      setSeverity(res.draft.severity);
      if (res.ticket) {
        // Hazard fast path: the ticket already exists and on-call has been alerted.
        setResult({
          ticket: res.ticket,
          merged: res.merged,
          message: res.message ?? `Ticket ${res.ticket.short_code} created.`,
          report_count: res.ticket.report_count,
          photo_to_ticket_ms: res.analysis_ms,
          client_elapsed_ms: Math.round(performance.now() - startedAt.current),
          hazard: res.hazard,
          dedupe: null,
        });
        setPhase("done");
      } else {
        setPhase("review");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong. Please try again.");
      setPhase("compose");
    }
  }

  async function confirm() {
    if (!intake) return;
    setError(null);
    setPhase("submitting");
    const edits: Record<string, unknown> = {};
    if (title.trim() && title !== intake.draft.title) edits.title = title.trim();
    if (category && category !== intake.draft.category) edits.category = category;
    if (severity !== intake.draft.severity) edits.severity = severity;
    try {
      const res = await api<ConfirmResponse>(
        `/api/reports/${intake.report_id}/confirm`,
        jsonBody({
          edits,
          location_id: location?.id ?? null,
          client_elapsed_ms: Math.round(performance.now() - startedAt.current),
          study: study !== null,
          participant: study || null,
        }),
      );
      setResult(res);
      setPhase("done");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't submit. Please try again.");
      setPhase("review");
    }
  }

  function reset() {
    setPhoto(null);
    setText("");
    setIntake(null);
    setResult(null);
    setLocation(null);
    setPickedLocation(null);
    setShowPicker(false);
    setError(null);
    voice.clearAudio();
    startedAt.current = performance.now();
    setPhase("compose");
  }

  const hazard = intake?.hazard?.is_hazard ? intake.hazard : null;
  const categoryLabel =
    taxonomy?.categories.find((c) => c.key === category)?.label ?? category.replace(/_/g, " ");

  return (
    <div className="mx-auto max-w-xl px-4 pb-16 pt-5">
      <div aria-live="polite" className="sr-only">
        {phase === "analyzing" ? "Analyzing your report" : phase === "done" ? "Report submitted" : ""}
      </div>

      {error && (
        <div role="alert" className="mb-4 flex gap-2 rounded-lg border border-destructive/40 px-4 py-3 text-sm text-destructive">
          <CircleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          {error}
        </div>
      )}

      {study !== null && phase !== "done" && (
        <p className="mb-4 flex items-center gap-2 rounded-lg border border-p3/40 bg-card px-3 py-2 text-sm">
          <Timer className="size-4 text-p3" aria-hidden="true" /> Timing study{study ? `: ${study}` : ""}. Your time is being measured.
        </p>
      )}

      {phase === "compose" && (
        <section aria-labelledby="report-heading" className="space-y-5">
          <div>
            <h1 id="report-heading" ref={headingRef} tabIndex={-1} className="text-2xl font-bold tracking-tight outline-none">
              Report a problem
            </h1>
            <p className="mt-1 text-muted-foreground">Snap a photo and say one sentence. We&apos;ll do the rest.</p>
          </div>

          {qrCode && (
            <div className="flex items-center gap-2 rounded-lg border bg-card px-3 py-2.5 text-sm">
              <MapPin className="size-4 shrink-0 text-primary" aria-hidden="true" />
              {qrLocation ? (
                <span>
                  <span className="font-medium">{locationName(qrLocation)}</span>
                  <span className="text-muted-foreground"> · {qrLocation.building_name}</span>
                </span>
              ) : qrError ? (
                <span className="text-muted-foreground">Unknown location code; we&apos;ll ask where it is.</span>
              ) : (
                <Skeleton className="h-4 w-48" />
              )}
            </div>
          )}

          {/* Photo */}
          {photo ? (
            <div className="relative overflow-hidden rounded-xl border bg-card">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={photo.previewUrl} alt="Your photo" className="max-h-72 w-full object-cover" />
              <div className="absolute bottom-2 right-2 flex gap-2">
                <Button asChild size="sm" variant="secondary">
                  <label htmlFor="photo-camera" className="cursor-pointer">
                    <RotateCcw /> Retake
                  </label>
                </Button>
                <Button size="sm" variant="secondary" onClick={() => setPhoto(null)} aria-label="Remove photo">
                  <Trash2 />
                </Button>
              </div>
            </div>
          ) : (
            <div className="grid gap-2">
              <label
                htmlFor="photo-camera"
                className="flex h-36 cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-primary/40 bg-accent/40 text-primary transition-colors hover:bg-accent focus-within:ring-2 focus-within:ring-ring"
              >
                {preparing ? <LoaderCircle className="size-8 animate-spin" aria-hidden="true" /> : <Camera className="size-9" aria-hidden="true" />}
                <span className="text-lg font-semibold">{preparing ? "Preparing photo…" : "Take photo"}</span>
              </label>
              <label htmlFor="photo-library" className="mx-auto flex cursor-pointer items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
                <ImageIcon className="size-4" aria-hidden="true" /> or choose from your library
              </label>
            </div>
          )}
          <input id="photo-camera" type="file" accept="image/*" capture="environment" className="sr-only" onChange={onFile} />
          <input id="photo-library" type="file" accept="image/*" className="sr-only" onChange={onFile} />

          {/* Voice + text */}
          <div className="space-y-2">
            <Label htmlFor="report-text">What&apos;s wrong?</Label>
            <div className="flex items-start gap-2">
              <Textarea
                id="report-text"
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="e.g. The sink in the men's room keeps dripping"
                rows={3}
                className="text-base"
                maxLength={2000}
              />
              {voice.mode !== "none" && (
                <Button
                  type="button"
                  size="icon"
                  variant={voice.listening ? "destructive" : "outline"}
                  className="size-12 shrink-0 rounded-full"
                  onClick={voice.listening ? voice.stop : voice.start}
                  aria-label={voice.listening ? "Stop recording" : "Speak your report"}
                  aria-pressed={voice.listening}
                >
                  {voice.listening ? <Square /> : <Mic />}
                </Button>
              )}
            </div>
            {voice.listening && (
              <p className="text-sm text-primary" aria-live="polite">
                <span className="font-medium">Listening…</span> {voice.interim && <em>“{voice.interim}”</em>}
              </p>
            )}
            {voice.audio && !voice.listening && (
              <p className="flex items-center gap-2 text-sm text-muted-foreground">
                <Mic className="size-4" aria-hidden="true" /> Voice note recorded; it will be transcribed.
                <button className="underline" onClick={voice.clearAudio}>Remove</button>
              </p>
            )}
            {voice.error && <p className="text-sm text-p2">{voice.error}</p>}
            {voice.mode === "none" && <p className="text-xs text-muted-foreground">Voice input isn&apos;t available in this browser. Typing works.</p>}
          </div>

          {/* Optional location when no QR code */}
          {!qrCode && (
            <div className="space-y-2">
              {pickedLocation && !showPicker ? (
                <button onClick={() => setShowPicker(true)} className="flex w-full items-center gap-2 rounded-lg border bg-card px-3 py-2.5 text-left text-sm">
                  <MapPin className="size-4 text-primary" aria-hidden="true" />
                  <span className="flex-1 font-medium">{locationName(pickedLocation)} · {pickedLocation.building_name}</span>
                  <span className="text-xs text-muted-foreground">Change</span>
                </button>
              ) : showPicker ? (
                <LocationPicker
                  value={pickedLocation}
                  onChange={(l) => {
                    setPickedLocation(l);
                    setShowPicker(false);
                  }}
                  autoFocus
                />
              ) : (
                <button onClick={() => setShowPicker(true)} className="flex items-center gap-1.5 text-sm font-medium text-primary hover:underline">
                  <MapPin className="size-4" aria-hidden="true" /> Add location (optional, we can usually tell)
                </button>
              )}
            </div>
          )}

          <Button size="xl" className="w-full" disabled={!canSubmit} onClick={submit}>
            <Send /> Send report
          </Button>
          <p className="text-center text-xs text-muted-foreground">
            Photos are stripped of location metadata. Please avoid photographing people.
          </p>
        </section>
      )}

      {phase === "analyzing" && (
        <section aria-labelledby="analyzing-heading" className="space-y-4">
          <h1 id="analyzing-heading" ref={headingRef} tabIndex={-1} className="flex items-center gap-2 text-2xl font-bold tracking-tight outline-none">
            <Sparkles className="size-6 text-primary" aria-hidden="true" /> Analyzing…
          </h1>
          <Card className="overflow-hidden">
            {photo && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={photo.previewUrl} alt="" className="h-40 w-full object-cover opacity-60" />
            )}
            <CardContent className="space-y-3 pt-5">
              <p className="flex items-center gap-2 text-sm font-medium text-primary">
                <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> {ANALYZE_STEPS[step]}
              </p>
              <Skeleton className="h-6 w-4/5" />
              <div className="flex gap-2">
                <Skeleton className="h-5 w-24" />
                <Skeleton className="h-5 w-16" />
              </div>
              <Skeleton className="h-4 w-3/5" />
            </CardContent>
          </Card>
        </section>
      )}

      {(phase === "review" || phase === "editing" || phase === "submitting") && intake && (
        <section aria-labelledby="review-heading" className="space-y-4">
          <h1 id="review-heading" ref={headingRef} tabIndex={-1} className="text-2xl font-bold tracking-tight outline-none">
            {phase === "editing" ? "Edit details" : "Does this look right?"}
          </h1>

          {hazard && <SafetyBanner text={hazard.safety_text} label={hazard.label} />}

          <Card className="overflow-hidden">
            {intake.photo_url && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={intake.photo_url} alt="Submitted photo" className="max-h-56 w-full object-cover" />
            )}
            <CardContent className="space-y-4 pt-5">
              {phase === "editing" ? (
                <EditForm
                  title={title}
                  setTitle={setTitle}
                  category={category}
                  setCategory={setCategory}
                  severity={severity}
                  setSeverity={setSeverity}
                  taxonomy={taxonomy}
                />
              ) : (
                <div className="space-y-2">
                  <p className="text-lg font-semibold leading-snug">{title}</p>
                  <div className="flex flex-wrap items-center gap-2">
                    <CategoryChip label={categoryLabel} trade={intake.draft.trade} />
                    <SeverityMeter severity={hazard ? 4 : severity} />
                    {hazard && (
                      <Badge variant="hazard">
                        <TriangleAlert aria-hidden="true" /> Hazard
                      </Badge>
                    )}
                  </div>
                  <p className="text-sm text-muted-foreground">{intake.draft.summary}</p>
                </div>
              )}

              <div className="space-y-2 border-t pt-4">
                <p className="text-sm font-medium">Location</p>
                {location && phase !== "editing" ? (
                  <div className="flex items-center gap-2 text-sm">
                    <MapPin className="size-4 shrink-0 text-primary" aria-hidden="true" />
                    <span className="flex-1">
                      <span className="font-medium">{locationName(location)}</span>
                      <span className="text-muted-foreground"> · {location.building_name}</span>
                    </span>
                    <button className="text-xs font-medium text-primary hover:underline" onClick={() => setLocation(null)}>
                      Change
                    </button>
                  </div>
                ) : (
                  <LocationPicker value={location} onChange={setLocation} candidates={intake.location_candidates} />
                )}
              </div>

              {intake.needs_confirmation && phase === "review" && intake.confirmation_reasons.length > 0 && (
                <ul className="space-y-1 rounded-md bg-muted px-3 py-2 text-sm">
                  {intake.confirmation_reasons.map((r) => (
                    <li key={r} className="flex gap-2">
                      <CircleAlert className="mt-0.5 size-4 shrink-0 text-p2" aria-hidden="true" /> {r}
                    </li>
                  ))}
                </ul>
              )}

              <p className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <Timer className="size-3.5" aria-hidden="true" /> AI analyzed this in {secs(intake.analysis_ms)}
                {intake.llm_mode !== "live" && (
                  <Badge variant="outline" className="font-normal">
                    {intake.llm_mode === "mock" ? "Offline demo mode" : "AI unavailable: please review"}
                  </Badge>
                )}
              </p>
            </CardContent>
          </Card>

          <div className="grid gap-2">
            <Button size="xl" onClick={confirm} disabled={phase === "submitting" || !location}>
              {phase === "submitting" ? <LoaderCircle className="animate-spin" /> : <Check />}
              {phase === "editing" ? "Save and send" : location ? "Looks right, send it" : "Pick a location to send"}
            </Button>
            {phase === "review" && (
              <Button
                variant="outline"
                size="lg"
                onClick={() => {
                  ensureTaxonomy();
                  setPhase("editing");
                }}
              >
                <Pencil /> Edit
              </Button>
            )}
            {phase === "editing" && (
              <Button variant="ghost" onClick={() => setPhase("review")}>
                Cancel edits
              </Button>
            )}
          </div>
        </section>
      )}

      {phase === "done" && result && (
        <section aria-labelledby="done-heading" className="space-y-5">
          <div className="flex flex-col items-center text-center">
            <span
              className={cn(
                "grid size-16 place-items-center rounded-full",
                result.hazard.is_hazard ? "bg-hazard-soft text-hazard" : result.merged ? "bg-p3/15 text-p3" : "bg-success/15 text-success",
              )}
            >
              {result.hazard.is_hazard ? (
                <Siren className="size-8" aria-hidden="true" />
              ) : result.merged ? (
                <Users className="size-8" aria-hidden="true" />
              ) : (
                <CircleCheck className="size-9" aria-hidden="true" />
              )}
            </span>
            <h1 id="done-heading" ref={headingRef} tabIndex={-1} className="mt-3 text-2xl font-bold tracking-tight outline-none">
              {result.merged ? "Already reported" : result.hazard.is_hazard ? "Emergency alert sent" : "Thanks, it's reported"}
            </h1>
            <p className="mt-1 text-muted-foreground">{result.message}</p>
          </div>

          {result.hazard.is_hazard && <SafetyBanner text={result.hazard.safety_text} label={result.hazard.label} alerted />}

          {!result.ticket.location && intake && (
            <Card>
              <CardContent className="space-y-2 pt-5">
                <p className="font-semibold">Help responders find it</p>
                <p className="text-sm text-muted-foreground">Only if it&apos;s safe: where is this?</p>
                <LocationPicker
                  value={null}
                  onChange={async (loc) => {
                    try {
                      const res = await api<ConfirmResponse>(
                        `/api/reports/${intake.report_id}/confirm`,
                        jsonBody({ location_id: loc.id }),
                      );
                      setResult((r) => (r ? { ...r, ticket: res.ticket } : r));
                    } catch {
                      setError("Couldn't save the location. Responders were still alerted.");
                    }
                  }}
                  candidates={intake.location_candidates}
                />
              </CardContent>
            </Card>
          )}

          <Card>
            <CardContent className="space-y-3 pt-5">
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-sm text-muted-foreground">{result.ticket.short_code}</span>
                <PriorityBadge priority={result.ticket.priority} />
              </div>
              <p className="font-semibold leading-snug">{result.ticket.title}</p>
              <p className="text-sm text-muted-foreground">
                Sent to <span className="font-medium text-foreground">{result.ticket.team?.name ?? result.ticket.trade}</span>
                {result.report_count > 1 && <> · {result.report_count} people have reported this</>}
              </p>
              <div className="grid grid-cols-2 gap-3 border-t pt-3 text-center">
                <Metric label={intake?.photo_url ? "Photo → ticket" : "Report → ticket"} value={secs(result.photo_to_ticket_ms)} />
                <Metric label="Your time" value={secs(result.client_elapsed_ms)} />
              </div>
            </CardContent>
          </Card>

          <div className="grid gap-2">
            <Button size="lg" onClick={reset}>
              <Camera /> Report something else
            </Button>
            <Button asChild variant="ghost">
              <Link href={`/tickets/${result.ticket.short_code}`}>
                View ticket <ArrowRight />
              </Link>
            </Button>
          </div>
        </section>
      )}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-2xl font-bold tabular-nums">{value}</div>
      <div className="text-xs text-muted-foreground">{label}</div>
    </div>
  );
}

function CategoryChip({ label, trade }: { label: string; trade: string }) {
  const Icon = TRADE_ICON[trade];
  return (
    <Badge variant="secondary" className="font-medium">
      {Icon && <Icon aria-hidden="true" />}
      {label}
      <span className="font-normal text-muted-foreground">· {trade}</span>
    </Badge>
  );
}

function SafetyBanner({ text, label, alerted = false }: { text: string | null; label: string | null; alerted?: boolean }) {
  return (
    <div role="alert" className="rounded-xl border-2 border-hazard bg-hazard-soft p-4 text-hazard">
      <p className="flex items-center gap-2 text-base font-bold">
        <Siren className="size-5" aria-hidden="true" /> {label ? `${label} hazard` : "Safety hazard"}
        {alerted && <span className="font-medium">· on-call notified</span>}
      </p>
      {text && <p className="mt-1.5 text-sm font-medium text-foreground">{text}</p>}
    </div>
  );
}

function EditForm({
  title,
  setTitle,
  category,
  setCategory,
  severity,
  setSeverity,
  taxonomy,
}: {
  title: string;
  setTitle: (v: string) => void;
  category: string;
  setCategory: (v: string) => void;
  severity: number;
  setSeverity: (v: number) => void;
  taxonomy: Taxonomy | null;
}) {
  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="edit-title">Title</Label>
        <Input id="edit-title" value={title} onChange={(e) => setTitle(e.target.value)} maxLength={120} className="h-10 text-base" />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="edit-category">Category</Label>
        <Select id="edit-category" value={category} onChange={(e) => setCategory(e.target.value)} className="h-10 text-base">
          {!taxonomy && <option value={category}>{category}</option>}
          {taxonomy?.trades.map((trade) => (
            <optgroup key={trade} label={trade}>
              {taxonomy.categories
                .filter((c) => c.trade === trade)
                .map((c) => (
                  <option key={c.key} value={c.key}>
                    {c.label}
                  </option>
                ))}
            </optgroup>
          ))}
        </Select>
      </div>
      <fieldset className="space-y-1.5">
        <legend className="text-sm font-medium">How bad is it?</legend>
        <div className="grid grid-cols-4 gap-1.5">
          {[1, 2, 3, 4].map((n) => (
            <button
              key={n}
              type="button"
              aria-pressed={severity === n}
              onClick={() => setSeverity(n)}
              className={cn(
                "rounded-md border px-1 py-2 text-xs font-medium transition-colors",
                severity === n ? "border-primary bg-primary text-primary-foreground" : "hover:bg-accent",
              )}
              title={taxonomy?.severities[String(n)]}
            >
              <span className="block text-base font-bold">{n}</span>
              {SEVERITY_LABEL[n]}
            </button>
          ))}
        </div>
      </fieldset>
    </div>
  );
}
