import { expect, test } from "@playwright/test";
test("product management route and dynamic form", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("access_token", "test"));
  await page.route("**/api/v1/auth/me", r => r.fulfill({ json: { id: "u", email: "u@test", role: "customer" } }));
  await page.route("**/api/v1/products", r => r.fulfill({ json: { items: [], total: 0, page: 1, page_size: 20 } }));
  await page.route("**/api/v1/categories", r => r.fulfill({ json: [] }));
  await page.goto("/products");
  await expect(page.getByRole("heading", { name: /products|商品/i })).toBeVisible();
  await page.getByRole("link", { name: /new product|新建商品/i }).click();
  await expect(page.getByLabel(/category|品类/i)).toBeVisible();
});
