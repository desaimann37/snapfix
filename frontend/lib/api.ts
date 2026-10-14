// Typed client for the SnapFix API. All calls are same-origin (/api/*), proxied to FastAPI by Next.js.

export type Priority = "P1" | "P2" | "P3" | "P4";
export type Status = "new" | "triaged" | "assigned" | "in_progress" | "resolved" | "closed";

export interface LocationRef {
  id: string;
  building_id: string;
  building_code: string;
  building_name: string;
  floor: number;
  room: string;
  label: string;
  room_type: string;
  qr_code: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface TeamRef {
  id: string;
  name: string;
  trade: string;
}

export interface AssetRef {
  id: string;
  tag: string;
  name: string;
  type: string;
  make?: string | null;
  model?: string | null;
}

export interface Ticket {
  id: string;
  short_code: string;
  title: string;
  summary: string;
  category: string;
  category_label: string;
  trade: string;
  severity: number;
  priority: Priority;
  is_hazard: boolean;
  hazard_type: string | null;
  status: Status;
  needs_review: boolean;
  report_count: number;
  created_at: string;
  updated_at: string;
  sla_due_at: string | null;
  resolved_at: string | null;
  assignee: string | null;
  source: string;
  team: TeamRef | null;
  location: LocationRef | null;
  location_text: string | null;
  asset: AssetRef | null;
  cluster_id: string | null;
  parent_id: string | null;
  thumbnail_url: string | null;
}

export interface ReportRef {
  id: string;
  created_at: string;
  text: string | null;
  transcript: string | null;
  photo_url: string | null;
  status: string;
  llm_mode: string | null;
  extraction_confidence: number | null;
  latency_ms: number | null;
  prompt_version: string | null;
}

export interface TicketEvent {
  id: string;
  type: string;
  actor: string;
  rationale: string | null;
  payload: Record<string, unknown> | null;
  created_at: string;
}

export interface TicketDetail extends Ticket {
  reports: ReportRef[];
  events: TicketEvent[];
  brief: Record<string, unknown> | null;
  brief_generated_at: string | null;
  children: Ticket[];
}

export interface TicketList {
  items: Ticket[];
  total: number;
}

export interface Building {
  id: string;
  code: string;
  name: string;
  floors: number;
  lat: number;
  lng: number;
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { cache: "no-store", ...init });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {
      /* not json */
    }
    throw new ApiError(res.status, detail || `Request failed (${res.status})`);
  }
  return res.json() as Promise<T>;
}

export function jsonBody(body: unknown, method = "POST"): RequestInit {
  return { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
}

export function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== "") sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

// ---- intake ---------------------------------------------------------------------------------------
export interface TicketDraft {
  title: string;
  summary: string;
  category: string;
  trade: string;
  severity: 1 | 2 | 3 | 4;
  severity_reason: string;
  is_hazard: boolean;
  hazard_type: string | null;
  asset_type: string | null;
  location_text_from_image: string | null;
  location_text_from_user: string | null;
  visible_evidence: string[];
  needs_clarification: boolean;
  clarifying_question: string | null;
  confidence: number;
  image_relevant: boolean;
}

export interface HazardInfo {
  is_hazard: boolean;
  hazard_type: string | null;
  label: string | null;
  rule_hits: string[];
  sources: string[];
  rationale: string;
  safety_text: string | null;
}

export interface IntakeResponse {
  report_id: string;
  draft: TicketDraft;
  location: LocationRef | null;
  location_method: string;
  location_explanation: string;
  location_candidates: LocationRef[];
  needs_confirmation: boolean;
  confirmation_reasons: string[];
  hazard: HazardInfo;
  llm_mode: string;
  extraction_error: string | null;
  photo_url: string | null;
  transcript: string | null;
  stt_error: string | null;
  timings: Record<string, number>;
  analysis_ms: number;
  ticket: Ticket | null;
  merged: boolean;
  message: string | null;
}

export interface ConfirmResponse {
  ticket: Ticket;
  merged: boolean;
  message: string;
  report_count: number;
  photo_to_ticket_ms: number;
  client_elapsed_ms: number | null;
  hazard: HazardInfo;
  dedupe: Record<string, unknown> | null;
}

export interface TaxonomyCategory {
  key: string;
  label: string;
  trade: string;
  description: string;
  default_severity: number;
}

export interface Taxonomy {
  trades: string[];
  categories: TaxonomyCategory[];
  severities: Record<string, string>;
  hazard_types: { key: string; label: string }[];
}
