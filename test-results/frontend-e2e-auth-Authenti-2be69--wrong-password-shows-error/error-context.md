# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: frontend/e2e/auth.spec.ts >> Authentication >> login with wrong password shows error
- Location: frontend/e2e/auth.spec.ts:21:3

# Error details

```
Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
Call log:
  - navigating to "/login", waiting until "load"

```

# Test source

```ts
  1  | import { test, expect } from '@playwright/test';
  2  | 
  3  | const TEST_EMAIL = `e2e-${Date.now()}@test.com`;
  4  | const TEST_PASSWORD = 'test123456';
  5  | 
  6  | test.describe('Authentication', () => {
  7  | 
  8  |   test('register a new account', async ({ page }) => {
  9  |     await page.goto('/register');
  10 |     await expect(page.locator('h1')).toContainText('Create your account');
  11 | 
  12 |     await page.locator('input[type="email"]').fill(TEST_EMAIL);
  13 |     await page.locator('input[type="password"]').fill(TEST_PASSWORD);
  14 |     await page.locator('button[type="submit"]').click();
  15 | 
  16 |     // Should redirect to login page after registration
  17 |     await page.waitForURL('**/login');
  18 |     await expect(page.locator('h1')).toContainText('Sign in');
  19 |   });
  20 | 
  21 |   test('login with wrong password shows error', async ({ page }) => {
> 22 |     await page.goto('/login');
     |                ^ Error: page.goto: Protocol error (Page.navigate): Cannot navigate to invalid URL
  23 | 
  24 |     await page.locator('input[type="email"]').fill('nonexistent@test.com');
  25 |     await page.locator('input[type="password"]').fill('wrongpassword');
  26 |     await page.locator('button[type="submit"]').click();
  27 | 
  28 |     // Error message should appear
  29 |     await expect(page.locator('text=Invalid')).toBeVisible({ timeout: 10000 });
  30 |   });
  31 | 
  32 |   test('login with valid credentials and see dashboard', async ({ page }) => {
  33 |     // First register via API
  34 |     const apiBase = 'http://localhost:8000/api/v1';
  35 |     const resp = await page.request.post(`${apiBase}/auth/register`, {
  36 |       data: { email: TEST_EMAIL, password: TEST_PASSWORD },
  37 |     });
  38 |     expect(resp.status()).toBe(201);
  39 | 
  40 |     await page.goto('/login');
  41 |     await page.locator('input[type="email"]').fill(TEST_EMAIL);
  42 |     await page.locator('input[type="password"]').fill(TEST_PASSWORD);
  43 |     await page.locator('button[type="submit"]').click();
  44 | 
  45 |     // Should end up on dashboard
  46 |     await page.waitForURL('**/dashboard');
  47 |     await expect(page.locator('h1')).toContainText('Videos');
  48 | 
  49 |     // Refresh should keep us logged in
  50 |     await page.reload();
  51 |     await expect(page.locator('h1')).toContainText('Videos');
  52 |   });
  53 | 
  54 | });
  55 | 
```