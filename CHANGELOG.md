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
