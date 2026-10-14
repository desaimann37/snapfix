# Changelog

## Phase 1: Skeleton and data
- Docker Compose with PostgreSQL 16 + pgvector, FastAPI backend, Next.js frontend; `make dev/seed/test/demo-reset`.
- SQLAlchemy 2 models for buildings, locations, assets, teams, reports, tickets, ticket events (AI decision log),
  clusters, SOPs + SOP chunks (384-d embeddings), timing runs; Alembic initial migration.
- Taxonomy: 10 trades, 33 categories, severity definitions, priority/SLA matrix, hazard keyword rules.
- Local embeddings (BAAI/bge-small-en-v1.5) with a deterministic hashing fallback.
- Deterministic seed: 3 buildings, 63 locations, 175 assets, 10 teams, 12 SOPs, ~400 historical tickets over 60 days,
  and planted demo scenarios (ENGR floors 3–4 water-intrusion cluster, repeat-failure sink, today's hazard).
- API: tickets (queue, detail, patch with audit events), locations (QR lookup, search, floor plans), SSE stream,
  admin demo reset, health.
- Frontend shell: nav, light/dark mode, live dispatcher queue at `/tickets` (hazards pinned, SLA countdown,
  report-count badges, filters, SSE live updates).

## Phase 2: Intake and extraction
- `POST /api/reports` (multipart photo/text/audio, QR code, GPS) -> AI draft; `POST /api/reports/{id}/confirm`
  -> routed ticket with audit events. Confirm is idempotent (double taps return the same ticket).
- Extraction with Claude Sonnet 5.5 + structured outputs (schema = TicketDraft), cached system prompt
  (`prompts/extract_v1.md`: taxonomy, severity definitions, 8 few-shot examples), effort `low`.
  Prompt version, model mode, tokens and cost recorded on every report.
- Mock mode: deterministic keyword classifier over the same taxonomy (doubles as the eval baseline).
  Live failures degrade to a `needs_review` draft so a ticket can always be created.
- Image intake: type/size checks, EXIF GPS read, orientation fixed, EXIF stripped, 1568 px JPEG; optional face blur.
- Location resolution: QR -> room words in text ("room 210", "2nd floor men's room in the library", named rooms)
  -> sign in photo -> GPS (building only) -> ask the user, with candidate quick picks.
- Speech: Web Speech API live transcript; MediaRecorder + faster-whisper fallback; typing always works.
- `/report` and `/r/[code]` mobile flow: big Take photo button (`capture="environment"`), mic, one-tap
  confirmation card, edit form, result screen with photo -> ticket time and the reporter's total time.
- PWA: manifest, icons, conservative service worker (network-first pages, never caches API/media).
- Tests: extraction (mock + stubbed live request shape + refusal fallback), location parsing/resolution,
  report API (EXIF stripping, size/type limits, edits, idempotency); Playwright smoke test (QR report ->
  ticket in queue; hazards pinned).

## Phase 3: Hazards, dedupe, routing, realtime
- Hazard fast path: deterministic keyword rules create (or merge into) a P1 ticket and alert on-call before any
  LLM call (measured ~180 ms round trip for "I smell gas in room 210"); AI enrichment runs afterwards and can
  add details but never remove the hazard. Reporters see safety instructions; they can add the location later.
- Notifier: console (default), Slack webhook, Twilio SMS; sent off the request thread; outcome recorded as a
  `notified` event; failures fall back to console.
- Duplicate detection: bge-small + pgvector KNN over open tickets in the same building (72 h), score =
  0.55 text + 0.25 location + 0.20 category, Claude Haiku 5.5 confirmation in the 0.60–0.80 band (and for strong
  matches in other rooms). Merges attach the report, bump report_count, re-evaluate severity/priority upward only.
- Per-building advisory lock (Postgres) so simultaneous reports of the same issue can't create two tickets
  (verified: 4 concurrent identical reports -> 1 ticket with 4 reports).
- SSE: ticket.created / ticket.merged / ticket.updated / hazard.alert published after commit; one shared
  EventSource per tab; global red hazard bar on dispatcher/manager pages.
- Ticket detail page: photo gallery, reports, floor-plan location, asset history, status/assignee controls, and the
  AI decision log (classification, dedupe score table, routing rationale, escalation, notifications).
- Tests: dedupe scoring/thresholds, 3 reports -> 1 ticket, severity never decreases, hazard fast path with the LLM
  down, merge without re-alert, routing table, Slack/Twilio payloads; Playwright: live queue + hazard bar via SSE.

## Phase 4: Manager intelligence
- Root-cause clustering every 2 minutes (APScheduler) and on demand: text embedding + floor + time features,
  HDBSCAN when a building has enough open tickets, agglomerative fallback, cohesion check; Claude Haiku 5.5 names
  each cluster and writes a hypothesis + recommended action. Confirm -> one parent inspection ticket linking all
  members; Dismiss -> never resurrected. The planted ENGR floors 3–4 water-intrusion cluster is found exactly.
- Technician brief: RAG over SOP sections (similarity + trade/asset boost; the best SOP's safety, tools and
  procedure always included), asset ticket history, report texts and photos; Claude Sonnet 5.5 structured brief;
  citations validated against retrieved sections (invented ones removed); "no matching SOP" said plainly; cached,
  regenerated when new reports arrive.
- KPIs, live activity feed, reports-per-day-by-trade trend, building hotspots, agent chat on `/dashboard`.
- Dispatcher agent: Claude tool-use loop over read-only tools (search_tickets, get_ticket, get_clusters, get_kpis),
  max 6 tool calls / 30 s; deterministic mock intents offline.
- Tests: clustering, dismissal/confirmation, brief citations + history, KPIs, mock agent intents, live agent loop with
  a stubbed client and tool-call cap; Playwright: dashboard cluster + assistant, SOP-cited brief.

## Phase 5: Evaluation and polish
- Eval set (98 labelled items: every trade, 19 hazards, tricky non-hazards, QR/text/no location, 9 duplicate groups)
  and `run_eval.py`: real pipeline on an isolated DB; category/trade/severity (exact, ±1), hazard recall/precision,
  location (with and without QR), pairwise dedupe P/R/F1, latency p50/p95, cost/report, trade confusion matrix,
  keyword baseline; JSON + markdown; non-zero exit if hazard recall < 100%. Mock run: hazard recall 100%,
  dedupe F1 97.1%, keyword-baseline category accuracy 85.7%.
- `/eval` page for judges (mock runs clearly labelled), `/baseline` 14-field legacy form with timer, study mode
  so only volunteer runs count as time-to-report measurements, printable `/admin/qr` sticker sheet.
- Accessibility: axe-core checks on 8 pages in light and dark (no serious/critical violations); status filter as
  toggle buttons; 404 and error pages.
- Hazard rules extended for natural phrasings found while labelling ("people keep tripping", "covered in ice",
  "hole in the walkway", hissing near a gas line).
