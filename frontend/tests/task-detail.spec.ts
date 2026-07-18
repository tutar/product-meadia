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
  await page.route("**/api/v1/tasks/task-1/creative-brief", route => route.fulfill({ status: 404 }));
  await page.route("**/api/v1/tasks/task-1/video-candidates", route => route.fulfill({ json: [] }));

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
  await page.route("**/api/v1/tasks/task-2/video-candidates", route => route.fulfill({ json: [] }));

  await page.goto("/tasks/task-2");

  const log = page.getByRole("region", { name: /execution log|执行日志/i });
  const firstAttempt = log.getByRole("button", { name: /attempt 1|第 1 次执行/i });
  await expect(firstAttempt).toHaveAttribute("aria-expanded", "false");
  await expect(log.getByRole("button", { name: /attempt 2|第 2 次执行/i })).toHaveAttribute("aria-expanded", "true");
  await firstAttempt.click();
  await expect(log.getByRole("button", { name: /writing script|撰写脚本/i }).first()).toHaveAttribute("aria-expanded", "false");
});

test("promo workspace reviews an ordered Shot Plan before generating keyframes", async ({ page }) => {
  let planApproved = false;
  await page.addInitScript(() => localStorage.setItem("access_token", "test"));
  await page.route("**/api/v1/auth/me", route => route.fulfill({ json: { id: "u", email: "u@test", role: "customer" } }));
  await page.route("**/api/v1/tasks/task-plan", route => route.fulfill({ json: {
    id: "task-plan", status: planApproved ? "imaging" : "shot_plan_review", type: "promo", image_count: 2,
    product_snapshot: { name: "Cedar candle" }, progress_log: [], created_at: "2026-07-18T10:00:00Z",
  } }));
  await page.route("**/api/v1/tasks/task-plan/script", route => route.fulfill({ json: {
    id: "script-1", task_id: "task-plan", content: "A script", edited_content: null, image_prompts: [], voiceover_text: "A script", status: "approved",
  } }));
  await page.route("**/api/v1/tasks/task-plan/creative-brief", route => route.fulfill({ json: { id: "brief-1", task_id: "task-plan", content: {}, status: "approved" } }));
  await page.route("**/api/v1/tasks/task-plan/shot-plan", route => {
    if (route.request().method() === "PUT") { planApproved = true; return route.fulfill({ json: { id: "plan-1", task_id: "task-plan", shots: [], status: "approved" } }); }
    return route.fulfill({ json: { id: "plan-1", task_id: "task-plan", status: planApproved ? "approved" : "pending_review", shots: [{ narrative_purpose: "Hook", target_duration_seconds: 5, image_prompt: "Candle", video_motion_prompt: "Orbit" }] } });
  });
  await page.route("**/api/v1/tasks/task-plan/images", route => route.fulfill({ json: [] }));
  await page.route("**/api/v1/tasks/task-plan/video-candidates", route => route.fulfill({ json: [] }));

  await page.goto("/tasks/task-plan");
  await expect(page.getByRole("heading", { name: "Shot Plan" })).toBeVisible();
  await expect(page.getByLabel("Shot Plan JSON")).toContainText("Hook");
  await page.getByRole("button", { name: "Approve and generate keyframes" }).click();
  await expect(page.getByRole("heading", { name: "Shot Plan" })).toHaveCount(0);
});

test("promo workspace localizes Shot Plan review for Chinese", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("access_token", "test");
    localStorage.setItem("i18nextLng", "zh");
  });
  await page.route("**/api/v1/auth/me", route => route.fulfill({ json: { id: "u", email: "u@test", role: "customer" } }));
  await page.route("**/api/v1/tasks/task-plan-zh", route => route.fulfill({ json: {
    id: "task-plan-zh", status: "shot_plan_review", type: "promo", image_count: 2,
    product_snapshot: { name: "雪松蜡烛" }, progress_log: [], created_at: "2026-07-18T10:00:00Z",
  } }));
  await page.route("**/api/v1/tasks/task-plan-zh/script", route => route.fulfill({ json: {
    id: "script-1", task_id: "task-plan-zh", content: "脚本", edited_content: null, image_prompts: [], voiceover_text: "脚本", status: "approved",
  } }));
  await page.route("**/api/v1/tasks/task-plan-zh/creative-brief", route => route.fulfill({ json: { id: "brief-1", task_id: "task-plan-zh", content: {}, status: "approved" } }));
  await page.route("**/api/v1/tasks/task-plan-zh/shot-plan", route => route.fulfill({ json: {
    id: "plan-1", task_id: "task-plan-zh", status: "pending_review", shots: [{ narrative_purpose: "开场", target_duration_seconds: 5, image_prompt: "蜡烛", video_motion_prompt: "环绕" }],
  } }));
  await page.route("**/api/v1/tasks/task-plan-zh/images", route => route.fulfill({ json: [] }));
  await page.route("**/api/v1/tasks/task-plan-zh/video-candidates", route => route.fulfill({ json: [] }));

  await page.goto("/tasks/task-plan-zh");

  await expect(page.getByRole("heading", { name: "镜头计划" })).toBeVisible();
  await expect(page.getByLabel("镜头计划 JSON")).toContainText("开场");
  await expect(page.getByRole("button", { name: "批准并生成关键帧" })).toBeVisible();
});

test("task progress localizes the planning node for Chinese", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("access_token", "test");
    localStorage.setItem("i18nextLng", "zh");
  });
  await page.route("**/api/v1/auth/me", route => route.fulfill({ json: { id: "u", email: "u@test", role: "customer" } }));
  await page.route("**/api/v1/tasks/task-planning", route => route.fulfill({ json: {
    id: "task-planning", status: "planning", type: "promo", image_count: 2, progress_log: [],
  } }));
  await page.route("**/api/v1/tasks/task-planning/creative-brief", route => route.fulfill({ status: 404 }));
  await page.route("**/api/v1/tasks/task-planning/script", route => route.fulfill({ status: 404 }));
  await page.route("**/api/v1/tasks/task-planning/images", route => route.fulfill({ json: [] }));
  await page.route("**/api/v1/tasks/task-planning/video-candidates", route => route.fulfill({ json: [] }));

  await page.goto("/tasks/task-planning");

  await expect(page.getByLabel("状态").getByText("2. 策划中", { exact: true })).toBeVisible();
});

test("execution log localizes a known English summary for Chinese", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("access_token", "test");
    localStorage.setItem("i18nextLng", "zh");
  });
  await page.route("**/api/v1/auth/me", route => route.fulfill({ json: { id: "u", email: "u@test", role: "customer" } }));
  await page.route("**/api/v1/tasks/task-log-zh", route => route.fulfill({ json: {
    id: "task-log-zh", status: "script_review", type: "promo", image_count: 2,
    progress_log: [
      { attempt: 1, stage: "scripting", step: "generate_script", status: "completed", summary: "Script generated (120 chars)" },
      { attempt: 1, stage: "planning", step: "generate_shot_plan", status: "running" },
    ],
  } }));
  await page.route("**/api/v1/tasks/task-log-zh/script", route => route.fulfill({ json: {
    id: "script-1", task_id: "task-log-zh", content: "脚本", edited_content: null, image_prompts: [], voiceover_text: "脚本", status: "pending_review",
  } }));
  await page.route("**/api/v1/tasks/task-log-zh/creative-brief", route => route.fulfill({ status: 404 }));
  await page.route("**/api/v1/tasks/task-log-zh/images", route => route.fulfill({ json: [] }));
  await page.route("**/api/v1/tasks/task-log-zh/video-candidates", route => route.fulfill({ json: [] }));

  await page.goto("/tasks/task-log-zh");

  const log = page.getByRole("region", { name: "执行日志" });
  await log.getByRole("button", { name: "撰写脚本" }).click();
  await expect(log.getByRole("button", { name: "策划" })).toBeVisible();
  await expect(log.getByText("生成镜头计划", { exact: true })).toBeVisible();
  await expect(log.getByText("脚本已生成（120 个字符）", { exact: true })).toBeVisible();
  await expect(log.getByText("Script generated (120 chars)", { exact: true })).toHaveCount(0);
});
