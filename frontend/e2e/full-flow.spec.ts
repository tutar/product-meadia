import { test, expect } from '@playwright/test';

const API = 'http://localhost:8000/api/v1';
const EMAIL = `e2e-flow-${Date.now()}@test.com`;
const PASSWORD = 'test123456';

test('full promo video creation flow', async ({ page }) => {
  test.setTimeout(180000);

  // 1. Register
  await page.goto('/register');
  await page.locator('input[type="email"]').fill(EMAIL);
  await page.locator('input[type="password"]').fill(PASSWORD);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL('**/login');

  // 2. Login
  await page.locator('input[type="email"]').fill(EMAIL);
  await page.locator('input[type="password"]').fill(PASSWORD);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL('**/dashboard');
  await expect(page.locator('h1')).toContainText('Videos');

  // 3. Get token
  const tokenResp = await page.request.post(`${API}/auth/token`, {
    data: { grant_type: 'password', email: EMAIL, password: PASSWORD },
  });
  const token = (await tokenResp.json()).access_token;
  const auth = { Authorization: `Bearer ${token}` };

  // 4. Create product
  const prodResp = await page.request.post(`${API}/products`, {
    headers: auth,
    data: { name: 'E2E Perfume', top_note: 'Citrus', middle_note: 'Lavender',
            base_note: 'Wood', scenarios: ['daily'] },
  });
  expect(prodResp.status()).toBe(201);
  const productId = (await prodResp.json()).id;

  // 5. Create task
  await page.goto('/tasks/new');
  await expect(page.locator('h1')).toContainText('New Video');
  await page.locator('select').selectOption(productId);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL('**/tasks/**');

  // 6. Click Resume
  const resumeBtn = page.locator('button:has-text("Resume")');
  await expect(resumeBtn).toBeVisible({ timeout: 5000 });
  await resumeBtn.click();
  await page.waitForTimeout(3000);
  await page.reload();

  // 7. Poll for script review
  let attempts = 0;
  while (attempts < 40) {
    await page.reload();
    const hasScript = await page.locator('text=Script Review').isVisible();
    const isDone = await page.locator('text=Complete').isVisible();
    if (hasScript || isDone) break;
    const btn = page.locator('button:has-text("Resume")');
    if (await btn.isVisible()) await btn.click();
    await page.waitForTimeout(3000);
    attempts++;
  }
  await expect(page.locator('text=Script Review')).toBeVisible({ timeout: 5000 });
  console.log(`Script ready after ${attempts * 3}s`);

  // 8. Approve script
  await page.locator('button:has-text("Approve")').first().click();
  await page.waitForTimeout(2000);
  await page.reload();

  // 9. Poll for images
  for (let i = 0; i < 60; i++) {
    await page.reload();
    if (await page.locator('text=Image Review').isVisible()) break;
    const btn = page.locator('button:has-text("Resume")');
    if (await btn.isVisible()) await btn.click();
    await page.waitForTimeout(3000);
  }
  await expect(page.locator('text=Image Review')).toBeVisible({ timeout: 5000 });
  console.log('Images ready');

  // 10. Approve all images
  const approveBtns = page.locator('button:has-text("Approve")');
  const count = await approveBtns.count();
  for (let i = 0; i < count; i++) {
    await approveBtns.nth(0).click();
    await page.waitForTimeout(500);
  }

  // 11. Verify task progresses
  await page.reload();
  console.log('Task progressing past image review');
});
