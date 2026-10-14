import path from "node:path";
import { expect, test } from "@playwright/test";

test("QR report becomes a ticket in the dispatcher queue", async ({ page }) => {
  const sentence = `Projector shows no signal from the lectern HDMI (${Date.now()})`;
  await page.goto("/r/engr-405");
  await expect(page.getByRole("heading", { name: "Report a problem" })).toBeVisible();
  await expect(page.getByText("Seminar Room 405")).toBeVisible();

  await page.setInputFiles("#photo-library", path.join(__dirname, "fixtures", "photo.jpg"));
  await page.getByLabel("What's wrong?").fill(sentence);
  await page.getByRole("button", { name: "Send report" }).click();

  await expect(page.getByRole("heading", { name: "Does this look right?" })).toBeVisible({ timeout: 30_000 });
  await page.getByRole("button", { name: /Looks right/ }).click();
  await expect(page.getByRole("heading", { name: /Thanks|Already reported/ })).toBeVisible({ timeout: 30_000 });

  const codeText = await page.getByText(/SF-\d{4}/).first().innerText();
  const code = codeText.match(/SF-\d{4}/)![0];

  await page.goto("/tickets");
  await expect(page.getByRole("link", { name: /Projector/ }).first()).toBeVisible();
  await expect(page.getByText(code)).toBeVisible();
});

test("queue pins open hazards to the top", async ({ page }) => {
  await page.goto("/tickets");
  const firstRow = page.locator("tbody tr").first();
  await expect(firstRow.getByText(/Hazard/i)).toBeVisible({ timeout: 15_000 });
});

test("new tickets and hazard alerts appear live (SSE) without reloading", async ({ page, request }) => {
  // Start from the demo state so the gas report creates a NEW hazard (a merge into an existing one doesn't re-alert).
  const token = process.env.ADMIN_TOKEN || "change-me";
  expect((await request.post("/api/admin/demo-reset", { headers: { "X-Admin-Token": token }, timeout: 120_000 })).ok()).toBeTruthy();
  await page.goto("/tickets");
  await expect(page.getByRole("status").filter({ hasText: "Live" })).toBeVisible({ timeout: 15_000 });

  const unique = `Wobbly table in the game room ${Date.now()}`;
  const intake = await (await request.post("/api/reports", { multipart: { text: unique, location_code: "stuc-247" } })).json();
  const done = await (await request.post(`/api/reports/${intake.report_id}/confirm`, { data: {} })).json();
  await expect(page.getByText(done.ticket.short_code)).toBeVisible({ timeout: 5_000 });

  const gas = await (await request.post("/api/reports", { multipart: { text: "I smell gas near room 210" } })).json();
  const bar = page.getByRole("region", { name: "Hazard alerts" });
  await expect(bar.getByText(/P1 hazard/i)).toBeVisible({ timeout: 3_000 });
  await expect(bar.getByText(gas.ticket.short_code)).toBeVisible();
});

test("manager dashboard shows the root-cause cluster and the assistant answers", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "Operations dashboard" })).toBeVisible();
  await expect(page.getByText(/water intrusion/i).first()).toBeVisible({ timeout: 15_000 });
  await expect(page.getByRole("button", { name: /Confirm: create one inspection ticket/ }).first()).toBeVisible();
  await page.getByRole("button", { name: "Any hazards right now?" }).click();
  await expect(page.getByText(/HAZARD/).last()).toBeVisible({ timeout: 15_000 });
});

test("ticket detail shows an SOP-cited technician brief", async ({ page, request }) => {
  const found = await (await request.get("/api/tickets?q=Faucet%20leaking%20again")).json();
  await page.goto(`/tickets/${found.items[0].short_code}`);
  await expect(page.getByRole("heading", { name: "Technician brief" })).toBeVisible();
  await expect(page.getByText(/Faucet Cartridge Replacement §4/).first()).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/repeat failure/i).first()).toBeVisible();
});
