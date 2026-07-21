import { expect, test } from "@playwright/test";

test("preferences filters stage defaults to verified compatible model configurations", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("access_token", "test"));
  await page.route("**/api/v1/auth/me", route => route.fulfill({ json: { id: "u", email: "u@test", role: "customer" } }));
  await page.route("**/api/v1/auth/preferences", route => route.fulfill({ json: { auto_approve_script: false, auto_approve_images: false } }));
  await page.route("**/api/v1/provider-model-catalog**", route => route.fulfill({ json: [{
    id: "catalog-text", provider: "openai", model_id: "gpt-4.1-mini", display_name: "GPT-4.1 mini",
    capabilities: ["creative_planning", "scriptwriting"], constraints: {}, capability_revision: 1,
    platform_default_available: false, is_available: true,
  }] }));
  await page.route("**/api/v1/model-configurations", route => route.fulfill({ json: [{
    id: "configuration-1", catalog_model_id: "catalog-text", provider: "openai", model_id: "gpt-4.1-mini", display_name: "GPT-4.1 mini",
    capabilities: ["creative_planning", "scriptwriting"], constraints: {}, uses_platform_default: false,
    verification_status: "verified", verification_error: null, verified_at: "2026-07-21T00:00:00Z", revoked_at: null,
    created_at: "2026-07-21T00:00:00Z", updated_at: "2026-07-21T00:00:00Z",
  }] }));
  await page.route("**/api/v1/stage-model-defaults", route => route.fulfill({ json: [] }));
  await page.route("**/api/v1/stage-model-defaults/creative_planning", route => {
    expect(route.request().method()).toBe("PUT");
    expect(route.request().postDataJSON()).toEqual({ model_configuration_id: "configuration-1" });
    return route.fulfill({ json: { stage: "creative_planning", model_configuration_id: "configuration-1" } });
  });

  await page.goto("/preferences");

  await expect(page.getByRole("heading", { name: "Model configurations" })).toBeVisible();
  const planning = page.getByLabel("Creative planning default");
  await expect(planning.locator("option")).toHaveCount(2);
  await planning.selectOption("configuration-1");
});

test("preferences submits a BYOK only on configuration creation and never renders it", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("access_token", "test"));
  await page.route("**/api/v1/auth/me", route => route.fulfill({ json: { id: "u", email: "u@test", role: "customer" } }));
  await page.route("**/api/v1/auth/preferences", route => route.fulfill({ json: { auto_approve_script: false, auto_approve_images: false } }));
  await page.route("**/api/v1/provider-model-catalog**", route => route.fulfill({ json: [{
    id: "catalog-text", provider: "openai", model_id: "gpt-4.1-mini", display_name: "GPT-4.1 mini",
    capabilities: ["creative_planning"], constraints: {}, capability_revision: 1,
    platform_default_available: false, is_available: true,
  }] }));
  await page.route("**/api/v1/stage-model-defaults", route => route.fulfill({ json: [] }));
  let posted = false;
  await page.route("**/api/v1/model-configurations", route => {
    if (route.request().method() === "POST") {
      posted = true;
      expect(route.request().postDataJSON()).toEqual({ catalog_model_id: "catalog-text", credential: "byok-never-returned" });
      return route.fulfill({ status: 201, json: {
        id: "configuration-2", catalog_model_id: "catalog-text", provider: "openai", model_id: "gpt-4.1-mini", display_name: "GPT-4.1 mini",
        capabilities: ["creative_planning"], constraints: {}, uses_platform_default: false, verification_status: "unverified",
        verification_error: null, verified_at: null, revoked_at: null, created_at: "2026-07-21T00:00:00Z", updated_at: "2026-07-21T00:00:00Z",
      } });
    }
    return route.fulfill({ json: [] });
  });

  await page.goto("/preferences");
  await page.getByLabel("Provider credential").fill("byok-never-returned");
  await page.getByRole("button", { name: "Add configuration" }).click();
  await expect.poll(() => posted).toBe(true);
  await expect(page.locator("body")).not.toContainText("byok-never-returned");
});
