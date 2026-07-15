import { test, expect } from '@playwright/test';

const API = 'http://localhost:8000/api/v1';

test.describe('Authentication', () => {

  test('register a new account', async ({ page }) => {
    const email = `e2e-1-${Date.now()}@test.com`;
    await page.goto('/register');
    await expect(page.locator('h1')).toContainText('Create your account');
    await page.locator('input[type="email"]').fill(email);
    await page.locator('input[type="password"]').fill('test123456');
    await page.locator('button[type="submit"]').click();
    await page.waitForURL('**/login');
    await expect(page.locator('h1')).toContainText('Sign in');
  });

  test('login with wrong password shows error', async ({ page }) => {
    await page.goto('/login');
    await page.locator('input[type="email"]').fill('nonexistent@test.com');
    await page.locator('input[type="password"]').fill('wrongpassword');
    await page.locator('button[type="submit"]').click();
    await expect(page.locator('text=Invalid')).toBeVisible({ timeout: 10000 });
  });

  test('login, dashboard, and persist after refresh', async ({ page }) => {
    const email = `e2e-3-${Date.now()}@test.com`;
    // Register
    await page.request.post(`${API}/auth/register`, { data: { email, password: 'test123456' } });
    // Login
    await page.goto('/login');
    await page.locator('input[type="email"]').fill(email);
    await page.locator('input[type="password"]').fill('test123456');
    await page.locator('button[type="submit"]').click();
    // Dashboard
    await page.waitForURL('**/dashboard');
    await expect(page.locator('h1')).toContainText('Videos');
    // Refresh persists login
    await page.reload();
    await expect(page.locator('h1')).toContainText('Videos');
  });

});
