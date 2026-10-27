import { expect, test } from "@playwright/test";

test("first-run setup wizard accepts API URL and key", async ({ page }) => {
  const apiUrl = process.env.ZUZU_API_URL || "http://127.0.0.1:8000/api/v1";
  const apiKey = (process.env.ZUZU_API_KEY || "").trim();
  if (!apiKey) {
    test.skip(true, "ZUZU_API_KEY is not set");
  }

  await page.goto("/setup");
  await expect(page.getByTestId("setup-api-url")).toBeVisible();
  await page.getByTestId("setup-api-url").fill(apiUrl);
  await page.getByTestId("setup-api-key").fill(apiKey);
  await page.getByTestId("setup-submit").click();

  await expect(page).toHaveURL("/");
  await expect(page.getByText("Say hello to Zuzu")).toBeVisible();
});
