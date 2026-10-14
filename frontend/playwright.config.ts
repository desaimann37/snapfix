import { defineConfig, devices } from "@playwright/test";

// Smoke tests run against a running stack (make dev, or `make db backend frontend`), mock or live LLM mode.
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  retries: 0,
  workers: 1, // every test talks to the same live stack + database
  fullyParallel: false,
  reporter: [["list"]],
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://localhost:3000",
    trace: "retain-on-failure",
  },
  projects: [{ name: "mobile-chrome", use: { ...devices["Pixel 7"] } }],
});
