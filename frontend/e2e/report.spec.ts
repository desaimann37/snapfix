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
