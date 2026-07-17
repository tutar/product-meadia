import { expect, test } from "@playwright/test";
test("product management route and dynamic form", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("access_token", "test"));
  await page.route("**/api/v1/auth/me", r => r.fulfill({ json: { id: "u", email: "u@test", role: "customer" } }));
  await page.route("**/api/v1/products", r => r.fulfill({ json: { items: [], total: 0, page: 1, page_size: 20 } }));
  await page.route("**/api/v1/categories", r => r.fulfill({ json: [] }));
  await page.goto("/products");
  await expect(page.locator("h1")).toHaveText(/products|商品/i);
  await page.locator('a[href="/products/new"]').first().click();
  await expect(page.getByLabel(/category|品类/i)).toBeVisible();
});

test("product filters keep the search field editable", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("access_token", "test"));
  await page.route("**/api/v1/auth/me", r => r.fulfill({ json: { id: "u", email: "u@test", role: "customer" } }));
  await page.route("**/api/v1/products**", r => r.fulfill({ json: { items: [], total: 0, page: 1, page_size: 20 } }));
  await page.route("**/api/v1/categories", r => r.fulfill({ json: [{ id: "c1", name: "Home fragrance" }] }));
  await page.goto("/products");

  const search = page.getByLabel(/search|搜索/i);
  const category = page.getByLabel(/category|品类/i);
  await search.fill("candle");

  await expect(search).toHaveValue("candle");
  await expect(search).toBeVisible();
  await expect(category).toBeVisible();
  expect((await search.boundingBox())!.width).toBeGreaterThan((await category.boundingBox())!.width);
});

test("editing a product with a main image displays the existing image", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("access_token", "test"));
  await page.route("**/api/v1/auth/me", r => r.fulfill({ json: { id: "u", email: "u@test", role: "customer" } }));
  await page.route("**/api/v1/categories", r => r.fulfill({ json: [] }));
  await page.route("**/api/v1/products/p1", r => r.fulfill({ json: {
    id: "p1", category_id: "c1", name: "Studio Headphones", description: null,
    selling_points: [], scenarios: [], attributes: {}, main_image_asset_id: "asset-1",
    main_image_source: "asset", category_template_version: 1,
  } }));
  await page.route("**/api/v1/media/asset-1/access", r => r.fulfill({ json: { asset_id: "asset-1", url: "https://example.test/existing.png" } }));
  await page.route("https://example.test/existing.png", r => r.fulfill({ contentType: "image/png", body: "" }));

  await page.goto("/products/p1/edit");

  await expect(page.getByRole("img", { name: /existing main image|当前主图/i })).toBeVisible();
});
