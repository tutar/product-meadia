import { expect, test } from "@playwright/test";
test("catalog initialization remains non blocking", async ({ page }) => { await page.goto("/products"); await expect(page.getByRole("link", { name: /new product|新建商品/i })).toBeVisible(); });
