import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  timeout: 30000,
  retries: 1,
  use: {
    baseURL: 'http://localhost:5174',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: {
    command: 'npm run dev -- --host 0.0.0.0 --port 5174',
    url: 'http://localhost:5174',
    // A developer may already be inspecting this isolated worktree on 5174.
    // Reusing it keeps Playwright from failing before tests start.
    reuseExistingServer: true,
  },
});
