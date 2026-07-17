import { expect, test } from "@playwright/test";

test("task detail groups script substeps in an expanded scriptwriting stage", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("access_token", "test"));
  await page.route("**/api/v1/auth/me", route => route.fulfill({ json: { id: "u", email: "u@test", role: "customer" } }));
  await page.route("**/api/v1/tasks/task-1", route => route.fulfill({ json: {
    id: "task-1", status: "script_review", type: "promo", image_count: 2,
    progress_log: [
      { attempt: 1, stage: "scripting", step: "generate_script", status: "completed",
        started_at: "2026-07-17T10:00:00Z", finished_at: "2026-07-17T10:00:03Z",
        summary: "Script generated (120 chars)" },
      { attempt: 1, stage: "scripting", step: "wait_script_review", status: "waiting",
        started_at: "2026-07-17T10:00:03Z", summary: "Waiting for user review" },
    ],
  } }));
  await page.route("**/api/v1/tasks/task-1/script", route => route.fulfill({ json: {
    id: "script-1", task_id: "task-1", content: "A script", edited_content: null,
    image_prompts: [], voiceover_text: "A script", status: "pending_review",
  } }));
  await page.route("**/api/v1/tasks/task-1/images", route => route.fulfill({ json: [] }));

  await page.goto("/tasks/task-1");

  const log = page.getByRole("region", { name: /execution log|执行日志/i });
  const stage = log.getByRole("button", { name: /writing script|撰写脚本/i });
  await expect(stage).toBeVisible();
  await expect(log.getByText(/generate script|生成脚本/i)).toBeVisible();
  await expect(log.getByText(/script generated \(120 chars\)/i)).toBeVisible();
});

test("task detail expands the latest attempt and keeps completed history collapsed", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("access_token", "test"));
  await page.route("**/api/v1/auth/me", route => route.fulfill({ json: { id: "u", email: "u@test", role: "customer" } }));
  await page.route("**/api/v1/tasks/task-2", route => route.fulfill({ json: {
    id: "task-2", status: "scripting", type: "promo", image_count: 2,
    progress_log: [
      { attempt: 1, stage: "scripting", step: "generate_script", status: "completed", started_at: "2026-07-17T10:00:00Z", finished_at: "2026-07-17T10:00:01Z" },
      { attempt: 2, stage: "scripting", step: "generate_script", status: "running", started_at: "2026-07-17T10:01:00Z" },
    ],
  } }));
  await page.route("**/api/v1/tasks/task-2/images", route => route.fulfill({ json: [] }));

  await page.goto("/tasks/task-2");

  const log = page.getByRole("region", { name: /execution log|执行日志/i });
  const firstAttempt = log.getByRole("button", { name: /attempt 1|第 1 次执行/i });
  await expect(firstAttempt).toHaveAttribute("aria-expanded", "false");
  await expect(log.getByRole("button", { name: /attempt 2|第 2 次执行/i })).toHaveAttribute("aria-expanded", "true");
  await firstAttempt.click();
  await expect(log.getByRole("button", { name: /writing script|撰写脚本/i }).first()).toHaveAttribute("aria-expanded", "false");
});
