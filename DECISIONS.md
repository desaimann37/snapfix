# Decisions

Defaults chosen where the brief was silent or where the brief conflicted with the platform. Newest last.

| # | Decision | Why |
|---|---|---|
| 1 | Repo root is `Technomile/` (the project folder), with `backend/`, `frontend/`, `eval/` and `docs/` directly inside. | The brief's `snapfix/` layout is the project root; the hackathon folder is named Technomile. |
| 2 | **Structured outputs (`output_config.format` / `client.messages.parse`) instead of a forced `tool_choice`** for the photo → ticket extraction. The JSON schema is the brief's `create_ticket_draft` schema. | Claude Sonnet 5.5 returns HTTP 400 for forced `tool_choice` (`{"type":"tool"}` / `{"type":"any"}`). Structured outputs give the same guarantee that the response is valid JSON matching the schema. |
| 3 | No `temperature` parameter on any call. Extraction uses `output_config.effort="low"` for speed. | Sonnet 5.5 and Haiku 5.5 reject non-default sampling parameters. `effort` is the supported lever for latency vs depth. |
| 4 | Clustering uses **scikit-learn's `HDBSCAN`** (same algorithm as the `hdbscan` package). | Avoids a native build of `hdbscan` on Windows/Python 3.12; one less dependency. |
| 5 | Tests run on **in-memory SQLite + a deterministic hashing embedder**; the app runs on PostgreSQL 16 + pgvector with bge-small. Models are written to be portable (pgvector columns become JSON on SQLite; similarity falls back to numpy). | `make test` needs no Docker, API key, model download or internet, so tests are fast and run anywhere. |
| 6 | If `LLM_MODE=live` but `ANTHROPIC_API_KEY` is empty, the app **automatically runs in mock mode** (logged once). | The app, tests and demo always start; nothing breaks on stage because of a missing key. |
| 7 | **10 teams, one per trade** (brief said about 8). | Routing becomes a 1:1, explainable mapping (trade → team). |
| 8 | Seeded room numbers are **unique across campus** (ENGR x01–x18, LIB x20–x33, STUC x40–x52). | "I smell gas near room 210" always resolves to exactly one room, even without a QR code. The resolver still handles ambiguity in general. |
| 9 | Added `Location.room_type` (lab, restroom, elevator, ...) and floor-plan rectangle fields (`x, y, w, h`). | Room type drives location criticality for priority (labs, restrooms, elevators are higher); rectangles let us draw floor plans and hotspots in plain SVG. |
| 10 | Added `Ticket.source` (`snapfix` vs `seed`). AI-performance KPIs (photo → ticket latency, time-to-triage) count **only real pipeline tickets**. | We never present synthetic numbers as measured performance. |
| 11 | No HNSW index on embeddings; exact KNN with filters (same building, open, last 72 h). | At campus scale (thousands of tickets) exact search is fast and avoids recall loss from filtered approximate search. Add HNSW past ~100k tickets. |
| 12 | The browser always calls same-origin `/api` and `/media`; **Next.js rewrites proxy them to FastAPI** (`BACKEND_URL`, falling back to `NEXT_PUBLIC_API_URL`). | A phone needs only one HTTPS tunnel (to the frontend) for camera + microphone. `compress: false` keeps SSE unbuffered. |
| 13 | shadcn/ui components are vendored by hand in `frontend/components/ui` (Button, Card, Badge, Input, Tabs, ...). | Same code shadcn's CLI would generate, without an interactive CLI step in the build. |
| 14 | Historical open tickets older than their SLA are resolved during seeding; planted scenarios keep their timing. | A believable queue: most open work is within SLA, with a few deliberate tension points (hazard just overdue, repeat-failure sink about to breach). |
| 15 | Seed resets keep `timing_runs` (baseline vs SnapFix time-to-report measurements). | Those are real volunteer measurements, not demo data. |
| 16 | Hazards force severity 4 and P1. "Wet floor" alone is **not** a hazard keyword (it's a spill); "slippery", "someone fell", "black ice" are. Keyword rules prefer recall; negations ("no smoke") still escalate. | Avoids alert fatigue from every spill while keeping 100% recall on dangerous phrasing. Safety errs on the side of escalation. |
