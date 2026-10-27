import { expect, test } from "@playwright/test";

/**
 * E2E: requires the API running with AI_PROVIDER=mock (or real key) and the
 * web dev server. Run: npx playwright test (after `npx playwright install`).
 */

test("chat round trip through the real API", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("API ok")).toBeVisible({ timeout: 10000 });

  await page.getByPlaceholder("Message Zuzu…").fill("echo:e2e works");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByText("e2e works").first()).toBeVisible({ timeout: 10000 });
});

test("tasks page loads", async ({ page }) => {
  await page.goto("/tasks");
  await expect(page.getByRole("heading", { name: "Tasks" })).toBeVisible();
});

test("approvals page loads", async ({ page }) => {
  await page.goto("/approvals");
  await expect(page.getByRole("heading", { name: "Approvals" })).toBeVisible();
});

test("memories create and delete", async ({ page }) => {
  await page.goto("/memories");
  const box = page.getByPlaceholder("New memory…");
  await box.fill("E2E test memory");
  await page.getByRole("button", { name: "Add" }).click();
  await expect(page.getByText("E2E test memory")).toBeVisible();

  const row = page.getByRole("row", { name: /E2E test memory/ });
  await row.getByRole("button", { name: "Delete" }).click();
  await expect(page.getByText("E2E test memory")).toHaveCount(0);
});
