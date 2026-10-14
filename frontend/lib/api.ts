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

// ---- dashboard / intelligence ---------------------------------------------------------------------
export interface Kpis {
  open_total: number;
  open_by_priority: Record<Priority, number>;
  hazards_open: number;
  hazards_24h: number;
  sla_breaches: number;
  duplicates_prevented_30d: number;
  duplicates_merged_live: number;
  reports_24h: number;
  reports_per_day_14d: number;
  photo_to_ticket_ms: { count: number; avg: number | null; p50: number | null; p95: number | null };
  median_time_to_triage_s: number | null;
  open_clusters: number;
  avg_cost_per_report_usd: number | null;
  llm_mode: string;
}

export interface ClusterInfo {
  id: string;
  name: string;
  hypothesis: string;
  recommended_action: string | null;
  confidence: number;
  status: "open" | "confirmed" | "dismissed";
  building: { code: string; name: string } | null;
  llm_mode: string | null;
  created_at: string;
  tickets: Ticket[];
  parent_ticket: Ticket | null;
}

export interface ActivityItem {
  id: string;
  type: string;
  actor: string;
  rationale: string | null;
  created_at: string;
  ticket: { id: string; short_code: string; title: string; priority: Priority; is_hazard: boolean };
}

export interface TrendData {
  trades: string[];
  days: Array<{ date: string } & Record<string, number | string>>;
}

export interface BuildingSummary {
  code: string;
  name: string;
  floors: number;
  open_by_floor: Record<string, number>;
  open_total: number;
  hazards: number;
  busiest_floor: number;
}

export interface CitedLine {
  text: string;
  citation: string | null;
}

export interface TechBrief {
  summary: string;
  likely_causes: { cause: string; reasoning: string; likelihood: "high" | "medium" | "low" }[];
  tools_parts: string[];
  safety: CitedLine[];
  steps: CitedLine[];
  history_note: string | null;
  sop_coverage: "matched" | "partial" | "none";
  sources: { citation: string; title: string; section: string }[];
  history: { short_code: string; title: string; days_ago: number; status: string; resolution: string | null }[];
  llm_mode: string;
  generated_at: string;
}

export interface AgentReply {
  answer: string;
  tool_calls: { name: string; input: Record<string, unknown>; summary: string }[];
  mode: string;
  latency_ms: number;
}

// ---- evaluation -----------------------------------------------------------------------------------
export interface EvalItem {
  i: number;
  text: string;
  true: { category: string; trade: string; severity: number; is_hazard: boolean; room: string | null; group: string | null };
  pred: { category: string; trade: string; severity: number; is_hazard: boolean; room: string | null; confidence: number };
  merged: boolean;
  notes: string;
}

export interface EvalResult {
  run_id: string;
  timestamp: string;
  mode: string;
  note: string;
  models: { main: string; fast: string };
  prompt_version: string;
  embedder: string;
  n_items: number;
  n_with_photo: number;
  metrics: {
    category_accuracy: number | null;
    trade_accuracy: number | null;
    severity_exact: number | null;
    severity_within_1: number | null;
    hazard_recall: number | null;
    hazard_precision: number | null;
    hazard_counts: { tp: number; fn: number; fp: number };
    location_accuracy: number | null;
    location_items: number;
    location_accuracy_without_qr: number | null;
    location_items_without_qr: number;
    dedupe_precision: number | null;
    dedupe_recall: number | null;
    dedupe_f1: number | null;
    latency_ms: { p50: number | null; p95: number | null; mean: number | null };
    cost_per_report_usd: number | null;
  };
  baseline: { name: string; category_accuracy: number | null; trade_accuracy: number | null; severity_exact: number | null; severity_within_1: number | null };
  confusion_trade: { labels: string[]; matrix: number[][] };
  items: EvalItem[];
}

export interface TimingStats {
  baseline: { n: number; median_s: number | null; min_s: number | null; max_s: number | null };
  snapfix: { n: number; median_s: number | null; min_s: number | null; max_s: number | null };
  speedup: number | null;
}
