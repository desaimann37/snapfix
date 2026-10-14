# SnapFix demo script (about 5 minutes)

The product is designed around this run-of-show. Every step is automated in `frontend/e2e/demo.spec.ts`; run it as a
pre-flight check (it passes 3 times in a row from a reset).

## Before you go on stage (T-30 min)

1. `make dev` (or confirm the deployment is up), then `make demo-reset`. This loads the exact starting state:
   - an Engineering Hall floors 3–4 water cluster (5 tickets);
   - a repeat-failure sink in the Library 2F men's restroom;
   - one sparking-wires hazard from today.
2. Start the tunnel: `cloudflared tunnel --url http://localhost:3000`. Open `/admin/qr`, paste the https URL, print
   the stickers and put **`engr-101` (Innovation Lab, the demo room)** on the table.
3. Open `/admin` and enter the admin token. Leave this tab open: it holds the offline-mock switch and Reset.
4. Projector: one window on `/tickets` and a second tab on `/dashboard`. Check the green **Live** pill on both.
5. Demo phone: scan the `engr-101` sticker once, allow camera and microphone, and check the page says "Innovation Lab
   (Demo Room)". Keep it open.
6. Pre-flight: `cd frontend && npx playwright test e2e/demo.spec.ts`, then `make demo-reset` again.
7. Have the backup screen recording ready (see the end of this file).

## Run of show

| Time | Step | Do this | Say this |
|---|---|---|---|
| 0:30 | **1. The pain** | Open `/baseline`. Scroll the 14 fields; point at the running timer and the problem-code dropdown. | "This is how you report a leak today: about 3 minutes, and most people give up." |
| 1:00 | **2. The magic moment** | Hand the judge the phone on `/r/engr-101`. They tap **Take photo** (a chair, an outlet, a staged "leak") and the mic, and say one sentence. **Send report**, then **Looks right**. On the projector the row animates into `/tickets`. | "No portal, no dropdown, no room number. The QR sticker knows the room; the photo and one sentence do the rest. It's classified, routed and prioritized. Photo to ticket in a few seconds; the time is on the phone." |
| 0:45 | **3. Duplicates** | Two teammates report the **same** thing from different angles with different words. On the projector the row shows **3 reports** and stays one ticket. Open it: the decision log shows the score table. | "Ten people report the same leak. Dispatch sees one ticket with ten reports, not ten tickets. Here's why it merged: same room, same category, similar description." |
| 0:30 | **4. Safety** | On the phone at `/report`, type **"I smell gas near room 210"** and send. The phone shows the safety instructions; the red P1 bar appears on the projector immediately (and Slack/SMS if configured). | "Hazards never wait for AI. Keyword rules escalate in under a second. The model can add a hazard but can never remove one." |
| 0:45 | **5. Manager view** | Switch to `/dashboard`. Show the cluster card "Engineering Hall floors 3–4 water intrusion" with its 5 tickets and the hypothesis. Optionally click **Confirm** to create the parent inspection. | "Five small reports across two floors in 36 hours. SnapFix sees one roof or riser leak: one inspection instead of five visits." |
| 0:30 | **6. Technician brief** | Open the repeat-failure sink: in `/tickets` search "Faucet leaking again". Show the history callout (the earlier ticket "21 days ago … possible repeat failure") and the procedure steps with `§4` citations. | "The technician arrives knowing this sink failed three weeks ago, with the exact SOP steps cited, not invented." |
| 0:30 | **7. Proof** | Open `/eval`: hazard recall, category accuracy, dedupe F1, latency, cost per report, and legacy form vs SnapFix time. | "Measured, not claimed. 100% hazard recall is a hard gate; the eval fails the build otherwise." |
| 0:30 | **Close** | Back to the landing page. | "Works for any campus, hospital, property manager or city. No training needed. Plugs into existing work-order systems (Maximo, ServiceNow, MaintainX) through a webhook." |

## If something goes wrong

| Problem | Fix |
|---|---|
| Venue Wi-Fi or the AI API is slow or down | `/admin` → **Force offline mock**. Every flow keeps working with deterministic results; hazard rules, dedupe and routing are unchanged. Switch back with **Use live AI**. |
| The judge's photo gets an odd classification | Tap **Edit** on the confirmation card. That's the point: the human stays in control, and the edit shows in the decision log. |
| Phone can't open the camera | It must be the https tunnel URL, not http. "Choose from your library" also works, and so does typing. |
| Dashboard stopped updating | Refresh the page; the Live pill should turn green. |
| Data got messy in rehearsal | `/admin` → **Reset to demo start**, or `make demo-reset` (about 10 s). |
| Everything is down | Play the backup recording. |

## Backup screen recording

Record the full run once at the venue resolution: reset, then steps 1–7. On Windows: Win+Alt+R (Xbox Game Bar) or
OBS. Save it on the presenting laptop **and** a USB stick.
