import { expect, test } from "@playwright/test";

const product = {
  id: "p1", category_id: "c1", category: { id: "c1", name: "Electronics", description: null, template_version: 1, attributes: [] },
  name: "Studio Headphones", description: null, selling_points: [], scenarios: [], attributes: {},
  main_image_url: "https://example.test/headphones.png", main_image_source: "upload", category_template_version: 1,
};

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => { localStorage.setItem("access_token", "test"); localStorage.setItem("refresh_token", "test"); });
  await page.route("**/api/v1/auth/me", route => route.fulfill({ json: { id: "u1", email: "u@test.com", role: "customer" } }));
  await page.route("https://example.test/headphones.png", route => route.fulfill({ contentType: "image/png", body: "" }));
});

test("pending initialization polls until completed and removes notice", async ({ page }) => {
  let checks = 0;
  await page.route("**/api/v1/initialization-status", route => route.fulfill({ json: { status: checks++ === 0 ? "pending" : "completed", sample_version: 1, attempts: 1 } }));
  await page.route("**/api/v1/products**", route => route.fulfill({ json: { items: [], total: 0 } }));
  await page.route("**/api/v1/categories", route => route.fulfill({ json: [] }));
  await page.goto("/products");
  await expect(page.getByText(/being prepared|正在准备/i)).toBeVisible();
  await expect(page.getByText(/being prepared|正在准备/i)).toBeHidden({ timeout: 5000 });
  expect(checks).toBeGreaterThan(1);
});

test("failed initialization remains non-blocking", async ({ page }) => {
  await page.route("**/api/v1/initialization-status", route => route.fulfill({ json: { status: "failed", sample_version: 1, attempts: 2, error_message: "seed failed" } }));
  await page.route("**/api/v1/products**", route => route.fulfill({ json: { items: [], total: 0 } }));
  await page.route("**/api/v1/categories", route => route.fulfill({ json: [] }));
  await page.goto("/products");
  await expect(page.getByRole("status")).toContainText(/failed|失败/i);
  await page.getByRole("link", { name: /new product|新建商品/i }).click();
  await expect(page).toHaveURL(/\/products\/new$/);
});

test("task selector previews generic product and creates task", async ({ page }) => {
  await page.route("**/api/v1/products", route => route.fulfill({ json: { items: [product], total: 1 } }));
  let submitted: unknown;
  await page.route("**/api/v1/tasks", async route => {
    if (route.request().method() === "POST") { submitted = route.request().postDataJSON(); return route.fulfill({ status: 201, json: { id: "t1" } }); }
    return route.fulfill({ json: { items: [], total: 0 } });
  });
  await page.route("**/api/v1/tasks/t1", route => route.fulfill({ json: { id: "t1", status: "pending", type: "promo", image_count: 4, progress_log: [] } }));
  await page.goto("/tasks/new");
  await page.getByLabel(/choose a product|选择商品/i).selectOption("p1");
  await expect(page.getByText("Studio Headphones")).toBeVisible();
  await expect(page.getByText("Electronics")).toBeVisible();
  await expect(page.getByRole("img", { name: "Studio Headphones" })).toBeVisible();
  await page.getByRole("button", { name: /generate video|生成视频/i }).click();
  await expect.poll(() => submitted).not.toBeUndefined();
  expect(submitted).toMatchObject({ product_id: "p1", type: "promo" });
});

test("dashboard displays deleted product from task snapshot", async ({ page }) => {
  await page.route("**/api/v1/products**", route => route.fulfill({ json: { items: [], total: 0 } }));
  await page.route("**/api/v1/tasks", route => route.fulfill({ json: { items: [{ id: "t1", type: "promo", status: "done", created_at: "2026-01-01T00:00:00Z", product_id: null, product_snapshot: { version: 1, name: "Deleted Cookies", main_image_url: "https://example.test/headphones.png", category: { name: "Food" }, attributes: [] } }], total: 1 } }));
  await page.goto("/dashboard");
  await expect(page.getByText("Deleted Cookies")).toBeVisible();
  await expect(page.getByText("Food")).toBeVisible();
  await expect(page.locator("img[src='https://example.test/headphones.png']")).toBeVisible();
});
