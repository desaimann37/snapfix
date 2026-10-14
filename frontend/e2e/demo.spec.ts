import path from "node:path";
import { expect, test } from "@playwright/test";

// The stage demo (docs/DEMO_SCRIPT.md) as an automated run. Each run starts from `demo-reset`, so it can be
// repeated back to back:  npx playwright test e2e/demo.spec.ts --repeat-each=3
const TOKEN = process.env.ADMIN_TOKEN || "change-me";
const PHOTO = path.join(__dirname, "fixtures", "photo.jpg");

test.describe.configure({ mode: "serial" });

test("demo script runs end to end", async ({ page, browser, request }) => {
  test.setTimeout(180_000);
  const reset = await request.post("/api/admin/demo-reset", { headers: { "X-Admin-Token": TOKEN }, timeout: 120_000 });
  expect(reset.ok(), await reset.text()).toBeTruthy();

  // The projector: dispatcher queue on a desktop screen, listening live.
  const projector = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await projector.goto("/tickets");
  await expect(projector.getByRole("status").filter({ hasText: "Live" })).toBeVisible({ timeout: 15_000 });

  // 1. The pain: the legacy form.
  await page.goto("/baseline");
  await expect(page.getByText("14. Attachment (optional)")).toBeVisible();
  await expect(page.getByRole("timer")).toBeVisible();

  // 2. The magic moment: QR sticker -> photo + one sentence -> live ticket on the projector.
  await page.goto("/r/engr-101");
  await expect(page.getByText("Innovation Lab (Demo Room)")).toBeVisible();
  await page.setInputFiles("#photo-library", PHOTO);
  await page.getByLabel("What's wrong?").fill("the chair by the window has a broken leg");
  await page.getByRole("button", { name: "Send report" }).click();
  await expect(page.getByRole("heading", { name: "Does this look right?" })).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: /Looks right/ }).click();
  await expect(page.getByRole("heading", { name: /Thanks, it's reported/ })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText("Photo → ticket")).toBeVisible();
  const code = (await page.getByText(/SF-\d{4}/).first().innerText()).match(/SF-\d{4}/)![0];
  await expect(projector.getByText(code)).toBeVisible({ timeout: 5_000 });

  // 3. Duplicates: two teammates report the same chair in their own words -> one ticket, 3 reports.
  for (const text of ["broken chair near the window, one leg snapped", "the chair next to the window is broken"]) {
    const intake = await (await request.post("/api/reports", { multipart: { text, location_code: "engr-101" } })).json();
    const done = await (await request.post(`/api/reports/${intake.report_id}/confirm`, { data: {} })).json();
    expect(done.merged, JSON.stringify(done.dedupe)).toBe(true);
    expect(done.ticket.short_code).toBe(code);
  }
  await expect(projector.locator("tr", { hasText: code }).getByText("3 reports")).toBeVisible({ timeout: 5_000 });

  // 4. Safety: "I smell gas near room 210" -> instant P1, alert on the projector, safety text for the reporter.
  await page.goto("/report");
  await page.getByLabel("What's wrong?").fill("I smell gas near room 210");
  await page.getByRole("button", { name: "Send report" }).click();
  await expect(page.getByRole("heading", { name: "Emergency alert sent" })).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText(/leave the area/i).first()).toBeVisible();
  await expect(projector.getByRole("region", { name: "Hazard alerts" })).toContainText(/Gas/, { timeout: 5_000 });

  // 5. Manager view: the root-cause cluster.
  await projector.goto("/dashboard");
  const cluster = projector.getByText(/floors 3–4 water intrusion/i).first();
  await expect(cluster).toBeVisible({ timeout: 15_000 });
  await expect(projector.getByText(/5 open reports/).first()).toBeVisible();

  // 6. Technician brief for the repeat-failure sink.
  const sink = await (await request.get("/api/tickets?q=Faucet%20leaking%20again")).json();
  await projector.goto(`/tickets/${sink.items[0].short_code}`);
  await expect(projector.getByText(/Faucet Cartridge Replacement §4/).first()).toBeVisible({ timeout: 30_000 });
  await expect(projector.getByText(/2[0-2] days ago/).first()).toBeVisible();

  // 7. Proof: the evaluation page.
  await projector.goto("/eval");
  await expect(projector.getByText("Hazard recall").first()).toBeVisible({ timeout: 15_000 });
  await expect(projector.getByText("100.0%").first()).toBeVisible();
  await projector.close();
});
