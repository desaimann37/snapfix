# SnapFix pitch notes

## One line

Snap a photo and say one sentence: SnapFix turns it into a routed, de-duplicated, prioritized work order in seconds.
Hazards escalate instantly, managers see root causes, and technicians arrive with the history and the right procedure.

## Problem

- **Reporting is painful.** Find the portal, pick from a long category dropdown, describe the exact room. Many people
  give up; reports that do arrive are vague ("bathroom broken").
- **Triage is manual.** Dispatchers guess trade and priority from vague text, miss duplicates (ten reports of one leak)
  and miss that several small reports share one root cause.
- **Technicians arrive under-informed**, without asset history or the relevant procedure.

## Solution

1. **Photo + sentence → structured work order.** Vision AI against a fixed taxonomy (10 trades, 33 categories,
   4 severities), with location from the QR sticker, words, signage or GPS.
2. **Safety first.** Deterministic hazard rules create a P1 and alert on-call in under a second, with no AI dependency.
3. **One ticket per problem.** Duplicate detection merges reports of the same issue.
4. **Root causes.** Clustering + AI hypotheses ("one roof inspection instead of five visits").
5. **Technician brief.** Likely causes, a parts checklist, and SOP-cited safety steps and procedure, plus repeat-failure
   warnings.
6. **Trust.** An AI decision log on every ticket and a public evaluation page.

## How it works (for technical judges)

- **Models:**
  - Claude Sonnet 5.5 with structured outputs for extraction, briefs and the agent;
  - Claude Haiku 5.5 for duplicate confirmation and cluster naming;
  - local bge-small embeddings;
  - pgvector for similarity search.
- **No training needed.** Zero-shot with a strong vision-language model, a fixed taxonomy, few-shot examples and
  schema-constrained output. Accuracy comes from prompt design and deterministic rules, measured on a labelled set.
- **Deterministic where it matters:** hazard rules, routing and SLAs are plain, tested code. The model never picks a
  team.
- **Built to survive a live demo:** a mock mode for every AI call, graceful fallbacks, 274 backend tests, 22
  end-to-end tests, and the demo script automated end to end.

## Impact numbers

Measured with `make eval` (98 labelled reports) and the `/baseline` vs `/report` timing study. **Replace the
bracketed values after the live run and the volunteer study.**

| Metric | Value | Source |
|---|---|---|
| Hazard recall | 100% (19/19) | eval, all modes. Rules guarantee this independently of the model |
| Duplicate detection F1 | 97.1% (mock run) | eval |
| Category accuracy, Claude | [live run] | eval (`make eval` with API key) |
| Category accuracy, keyword baseline (no AI) | 85.7% | eval |
| Photo → ticket (server, p50) | [live run, target < 6 s] | eval + dashboard |
| Time to report: legacy form vs SnapFix | [e.g. 2m 50s vs 15s, N volunteers] | `/eval` timing study |
| Cost per report | [live run] | eval token accounting |

Talking points:
- **Faster to report → more problems reported early.** Cheaper fixes, fewer complaints.
- **Fewer duplicate tickets** → dispatch time goes to dispatching.
- **One inspection instead of five visits** when a root cause is found.
- **Technicians fix it the first time:** the history plus the right SOP on the first visit.

## Market

Anyone with buildings and a maintenance team: university campuses, hospitals, K-12 districts, property managers,
corporate real estate and cities (311-style reporting). SnapFix sits in front of existing CMMS / work-order systems
(Maximo, ServiceNow, MaintainX) and pushes the structured ticket through a webhook, so there's nothing to rip and
replace.

## Risks and how we handle them

| Risk | Mitigation |
|---|---|
| Model misclassifies | One-tap human confirmation with edit; decision log; dispatcher override; measured accuracy |
| Missed hazard | Deterministic keyword rules first; the model can only add hazards; 100% recall gate in the eval |
| Privacy (photos of people) | EXIF stripped, optional face blur, contact info never sent to the model, synthetic demo data |
| Wrong location | QR stickers first; never invents a room; asks the user when unsure |
| AI outage or cost spike | Mock/offline fallback, timeouts + retries, prompt caching, Haiku for cheap calls, cost tracked per report |
| Duplicate over-merging | Auto-merge only in the same room; borderline cases get a second opinion; a missed merge is the safe failure |

## Limitations (say them before they're asked)

- The evaluation set is text-only until we add campus photos; live-model numbers come from the live run.
- Single-campus prototype: one backend instance and an in-process event stream.
- No CMMS integration yet (webhook planned).

## Future work

CMMS webhooks and two-way status sync, SMS/WhatsApp intake, multilingual reports, CLIP image similarity for duplicates,
asset-level failure prediction from the history, an on-device mode for low connectivity, and per-tenant taxonomies and
SOP libraries.

## Q&A prep

- **"How do we trust it?"** Every decision is logged with its reason and scores, humans confirm and can override,
  hazards don't depend on the model, and accuracy is measured on `/eval`.
- **"Why not fine-tune?"** We don't need to. A fixed taxonomy and structured outputs give stable results; fine-tuning
  would need labelled data we don't have and would cost the time we spent on safety and evaluation.
- **"What does it cost?"** Measured per report in the eval. The system prompt is cached, and the cheap calls use Haiku.
- **"What if the internet goes down?"** Offline mock mode keeps the whole flow working; hazards and dedupe are local
  logic.
- **"Does it work for my building?"** Load your rooms, assets and SOPs (JSON + markdown) and print QR stickers. No
  training.
