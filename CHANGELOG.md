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
