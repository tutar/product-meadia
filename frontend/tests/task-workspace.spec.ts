import { expect, test } from "@playwright/test";

const tasks = [
  { id: "task-1", type: "promo", status: "compositing", created_at: "2026-07-17T08:00:00Z", product_snapshot: { name: "Cedar candle", category: { id: "category-1", name: "Home fragrance" } } },
  { id: "task-2", type: "viral", status: "done", created_at: "2026-07-16T08:00:00Z", product_snapshot: { name: "Travel mug", category: { id: "category-2", name: "Drinkware" } } },
];

async function mockWorkspace(page: import("@playwright/test").Page) {
  await page.addInitScript(() => localStorage.setItem("access_token", "test"));
  await page.route("**/api/v1/auth/me", route => route.fulfill({ json: { id: "u", email: "u@test", role: "customer" } }));
  await page.route("**/api/v1/categories", route => route.fulfill({ json: [{ id: "category-1", name: "Home fragrance", attributes: [] }, { id: "category-2", name: "Drinkware", attributes: [] }] }));
  await page.route("**/api/v1/products**", route => route.fulfill({ json: { items: [{ id: "product-1", name: "Cedar candle", category_id: "category-1", category: { name: "Home fragrance" } }], total: 1 } }));
  await page.route("**/api/v1/tasks**", route => {
    if (route.request().method() === "POST") return route.fulfill({ status: 201, json: { id: "task-3" } });
    return route.fulfill({ json: { items: tasks, total: tasks.length } });
  });
  await page.route("**/api/v1/tasks/task-*", route => {
    const task = tasks.find(item => route.request().url().endsWith(item.id)) ?? { ...tasks[0], id: "task-3" };
    return route.fulfill({ json: { ...task, image_count: 4, progress_log: [] } });
  });
  await page.route("**/api/v1/tasks/task-*/script", route => route.fulfill({ status: 404 }));
  await page.route("**/api/v1/tasks/task-*/images", route => route.fulfill({ json: [] }));
  await page.route("**/api/v1/tasks/task-*/video-candidates", route => route.fulfill({ json: [] }));
  await page.route("**/api/v1/model-configurations", route => route.fulfill({ json: [{
    id: "creative-model", catalog_model_id: "catalog-text", provider: "openai", model_id: "gpt-4.1-mini", display_name: "GPT-4.1 mini",
    capabilities: ["creative_planning"], constraints: {}, uses_platform_default: false, verification_status: "verified",
    verification_error: null, verified_at: "2026-07-21T00:00:00Z", revoked_at: null, created_at: "2026-07-21T00:00:00Z", updated_at: "2026-07-21T00:00:00Z",
  }] }));
  await page.route("**/api/v1/stage-model-defaults", route => route.fulfill({ json: [] }));
}

test("workspace keeps the task queue and filters in place while selecting", async ({ page }) => {
  await mockWorkspace(page);
  await page.goto("/dashboard");

  await expect(page.locator(".task-queue").getByRole("button", { name: /cedar candle/i })).toBeVisible();
  await expect(page.locator("header a[href='/tasks/new']")).toHaveCount(0);
  await page.getByLabel(/category|品类/i).selectOption("category-1");
  await expect(page).toHaveURL(/category=category-1/);

  await page.locator(".task-queue").getByRole("button", { name: /travel mug/i }).click();
  await expect(page).toHaveURL(/task=task-2/);
  await expect(page.locator(".task-queue-item.is-selected")).toContainText("Travel mug");
});

test("new video replaces the workspace main area and selects its result", async ({ page }) => {
  await mockWorkspace(page);
  await page.goto("/dashboard?task=task-1&category=category-1&product=product-1");
  await page.locator(".task-queue").getByRole("button", { name: /new video|新建视频/i }).click();

  await expect(page).toHaveURL(/mode=create/);
  await expect(page.getByRole("heading", { name: /new video|新建视频/i })).toBeVisible();
  await expect(page.getByLabel(/choose a product|选择商品/i)).toHaveValue("product-1");
  await page.getByRole("button", { name: /generate video|生成视频/i }).click();

  await expect(page).toHaveURL(/task=task-3/);
  await expect(page).not.toHaveURL(/mode=create/);
});

test("new video submits an explicit verified stage override to freeze with the task", async ({ page }) => {
  await mockWorkspace(page);
  await page.route("**/api/v1/tasks", route => {
    expect(route.request().method()).toBe("POST");
    expect(route.request().postDataJSON()).toMatchObject({
      product_id: "product-1", type: "promo", stage_model_configuration_ids: { creative_planning: "creative-model" },
    });
    return route.fulfill({ status: 201, json: { id: "task-3" } });
  });
  await page.goto("/dashboard?mode=create&product=product-1");
  await page.getByLabel("Creative planning").selectOption("creative-model");
  await page.getByRole("button", { name: /generate video|生成视频/i }).click();
  await expect(page).toHaveURL(/task=task-3/);
});
