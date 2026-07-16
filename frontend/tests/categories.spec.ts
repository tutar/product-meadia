import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("access_token", "test");
    localStorage.setItem("refresh_token", "test");
  });
  await page.route("**/api/v1/auth/me", route => route.fulfill({ json: { id: "u1", email: "a@test.com", role: "customer", is_active: true } }));
  await page.route("**/api/v1/categories", async route => {
    if (route.request().method() === "POST") return route.fulfill({ status: 201, json: { id: "c2", name: "Food", description: null, template_version: 1, attributes: [] } });
    return route.fulfill({ json: [{ id: "c1", name: "Electronics", description: "Devices", template_version: 1, product_count: 2, attributes: [] }] });
  });
});

test("manages category templates", async ({ page }) => {
  await page.goto("/categories");
  await expect(page.getByRole("heading", { name: /categories|品类/i })).toBeVisible();
  await page.getByRole("button", { name: /new category|新建品类/i }).click();
  await page.getByLabel(/name|名称/i).fill("Food");
  await page.getByRole("button", { name: /add attribute|添加属性/i }).click();
  const type = page.getByLabel(/type|类型/i);
  for (const value of ["text", "number", "single_select", "multi_select", "boolean"]) await type.selectOption(value);
  await type.selectOption("single_select");
  await expect(page.getByLabel(/options|选项/i)).toBeVisible();
  await expect(page.getByRole("button", { name: /move up|上移/i })).toBeVisible();
  await page.getByRole("button", { name: /save|保存/i }).click();
  await expect(page.getByText("Food")).toBeVisible();
  await expect(page.getByRole("button", { name: /delete|删除/i }).first()).toBeDisabled();
});
