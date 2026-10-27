import { defineConfig } from "@playwright/test";

/**
 * Playwright e2e config. Requires the API to be running (default
 * http://127.0.0.1:8000) and `npx playwright install` to have been run.
 */
const apiKey = (process.env.ZUZU_API_KEY || "").trim();

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 30000,
  use: {
    baseURL: process.env.ZUZU_WEB_URL || "http://127.0.0.1:3000",
    extraHTTPHeaders: apiKey
      ? { Authorization: `Bearer ${apiKey}` }
      : undefined,
  },
});
