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

test("preferences translates model configuration controls to Chinese", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("access_token", "test");
    localStorage.setItem("i18nextLng", "zh");
  });
  await page.route("**/api/v1/auth/me", route => route.fulfill({ json: { id: "u", email: "u@test", role: "customer" } }));
  await page.route("**/api/v1/auth/preferences", route => route.fulfill({ json: { auto_approve_script: false, auto_approve_images: false } }));
  await page.route("**/api/v1/provider-model-catalog**", route => route.fulfill({ json: [] }));
  await page.route("**/api/v1/model-configurations", route => route.fulfill({ json: [] }));
  await page.route("**/api/v1/stage-model-defaults", route => route.fulfill({ json: [] }));

  await page.goto("/preferences");

  await expect(page.getByRole("heading", { name: "模型配置" })).toBeVisible();
  await expect(page.getByText("接入模型", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "阶段默认模型" })).toBeVisible();
});

test("preferences creates a private OpenAI-compatible model without rendering its credential", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("access_token", "test"));
  await page.route("**/api/v1/auth/me", route => route.fulfill({ json: { id: "u", email: "u@test", role: "customer" } }));
  await page.route("**/api/v1/auth/preferences", route => route.fulfill({ json: { auto_approve_script: false, auto_approve_images: false } }));
  await page.route("**/api/v1/provider-model-catalog**", route => route.fulfill({ json: [] }));
  await page.route("**/api/v1/stage-model-defaults", route => route.fulfill({ json: [] }));
  let posted = false;
  await page.route("**/api/v1/model-configurations", route => {
    if (route.request().method() === "POST") {
      posted = true;
      expect(route.request().postDataJSON()).toEqual({
        display_name: "Studio voice", adapter: "openai_compatible", api_base: "http://voice.internal/v1",
        model_id: "voice-v1", capabilities: ["voice_generation"], credential: "private-byok",
      });
      return route.fulfill({ status: 201, json: { id: "private-voice", catalog_model_id: null, adapter: "openai_compatible", api_base: "http://voice.internal/v1", provider: "openai_compatible", model_id: "voice-v1", display_name: "Studio voice", capabilities: ["voice_generation"], constraints: {}, revision: 1, uses_platform_default: false, verification_status: "unverified", verification_error: null, verified_at: null, revoked_at: null, created_at: "2026-07-21T00:00:00Z", updated_at: "2026-07-21T00:00:00Z" } });
    }
    return route.fulfill({ json: [] });
  });

  await page.goto("/preferences");
  await page.getByRole("button", { name: "Configure private model" }).click();
  await page.getByLabel("Configuration name").fill("Studio voice");
  await page.getByLabel("Private endpoint").fill("http://voice.internal/v1");
  await page.getByLabel("Model ID").fill("voice-v1");
  await page.getByRole("checkbox", { name: "Voice generation" }).check();
  await page.getByLabel("Provider credential").fill("private-byok");
  await page.getByRole("button", { name: "Add configuration" }).click();

  await expect.poll(() => posted).toBe(true);
  await expect(page.locator("body")).not.toContainText("private-byok");
});
