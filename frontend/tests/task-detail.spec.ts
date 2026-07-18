import { expect, test } from "@playwright/test";

test("task detail groups script substeps in a collapsed scriptwriting stage", async ({ page }) => {
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
  const attempt = log.getByRole("button", { name: /attempt 1|第 1 次执行/i });
  await expect(attempt).toHaveAttribute("aria-expanded", "false");
  await attempt.click();
  const stage = log.getByRole("button", { name: /writing script|撰写脚本/i });
  await expect(stage).toHaveAttribute("aria-expanded", "false");
  await stage.click();
  await expect(log.getByText(/generate script|生成脚本/i)).toBeVisible();
  await expect(log.getByText(/script generated \(120 chars\)/i)).toBeVisible();
});

test("task detail keeps every execution attempt collapsed by default", async ({ page }) => {
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
  await expect(log.getByRole("button", { name: /attempt 2|第 2 次执行/i })).toHaveAttribute("aria-expanded", "false");
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
  await log.getByRole("button", { name: "第 1 次执行" }).click();
  await log.getByRole("button", { name: "撰写脚本" }).click();
  await expect(log.getByRole("button", { name: "策划" })).toBeVisible();
  await log.getByRole("button", { name: "策划" }).click();
  await expect(log.getByText("生成镜头计划", { exact: true })).toBeVisible();
  await expect(log.getByText("脚本已生成（120 个字符）", { exact: true })).toBeVisible();
  await expect(log.getByText("Script generated (120 chars)", { exact: true })).toHaveCount(0);
});

test("execution log keeps legacy image feedback in the image-generation stage", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("access_token", "test"));
  await page.route("**/api/v1/auth/me", route => route.fulfill({ json: { id: "u", email: "u@test", role: "customer" } }));
  await page.route("**/api/v1/tasks/task-image-log", route => route.fulfill({ json: {
    id: "task-image-log", status: "image_review", type: "promo", image_count: 2,
    progress_log: [
      { attempt: 1, stage: "imaging", step: "generate_images", status: "completed", summary: "Images: 2 generated/reused" },
      { attempt: 1, stage: "image", step: "review_feedback", status: "completed", summary: "Improvement guidance recorded for regeneration" },
    ],
  } }));
  await page.route("**/api/v1/tasks/task-image-log/creative-brief", route => route.fulfill({ status: 404 }));
  await page.route("**/api/v1/tasks/task-image-log/script", route => route.fulfill({ status: 404 }));
  await page.route("**/api/v1/tasks/task-image-log/shot-plan", route => route.fulfill({ status: 404 }));
  await page.route("**/api/v1/tasks/task-image-log/images", route => route.fulfill({ json: [] }));
  await page.route("**/api/v1/tasks/task-image-log/video-candidates", route => route.fulfill({ json: [] }));

  await page.goto("/tasks/task-image-log");

  const log = page.getByRole("region", { name: "Execution Log" });
  await log.getByRole("button", { name: "Attempt 1" }).click();
  await log.getByRole("button", { name: "Generate images" }).click();
  await expect(log.getByText("Improvement guidance recorded for regeneration", { exact: true })).toBeVisible();
  await expect(log.getByRole("button", { name: "image", exact: true })).toHaveCount(0);
});

test("video clip review presents four clips as a desktop contact sheet", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.addInitScript(() => localStorage.setItem("access_token", "test"));
  await page.route("**/api/v1/auth/me", route => route.fulfill({ json: { id: "u", email: "u@test", role: "customer" } }));
  await page.route("**/api/v1/tasks/task-video-grid", route => route.fulfill({ json: {
    id: "task-video-grid", status: "video_review", type: "promo", image_count: 4, progress_log: [],
  } }));
  await page.route("**/api/v1/tasks/task-video-grid/images", route => route.fulfill({ json: [
    { id: "keyframe-1", status: "approved", access_url: "https://example.test/keyframe-1.png", generation_context: {} },
  ] }));
  await page.route("**/api/v1/tasks/task-video-grid/video-candidates", route => route.fulfill({ json: [1, 2, 3, 4].map(index => ({
    id: `clip-${index}`, kind: "clip", is_current: true, status: "pending_review", access_url: `https://example.test/clip-${index}.mp4`,
  })) }));

  await page.goto("/tasks/task-video-grid");

  const review = page.getByRole("region", { name: "Shot segments" });
  expect((await page.getByRole("button", { name: "View keyframe 1" }).boundingBox())!.y).toBeLessThan((await review.boundingBox())!.y);
  const clips = review.locator("video");
  await expect(clips).toHaveCount(4);
  await expect(clips.first()).toHaveAttribute("controls", "");
  const positions = await clips.evaluateAll(elements => elements.map(element => {
    const box = element.getBoundingClientRect();
    return { x: Math.round(box.x), y: Math.round(box.y), width: Math.round(box.width) };
  }));
  expect(new Set(positions.map(position => position.y)).size).toBe(1);
  expect(positions.every(position => position.width > 200)).toBe(true);
});

test("shot segment viewer is muted, navigable, and exposes review actions", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("access_token", "test"));
  await page.route("**/api/v1/auth/me", route => route.fulfill({ json: { id: "u", email: "u@test", role: "customer" } }));
  await page.route("**/api/v1/tasks/task-video-viewer", route => route.fulfill({ json: {
    id: "task-video-viewer", status: "video_review", type: "promo", image_count: 2, progress_log: [],
  } }));
  await page.route("**/api/v1/tasks/task-video-viewer/images", route => route.fulfill({ json: [] }));
  await page.route("**/api/v1/tasks/task-video-viewer/video-candidates", route => route.fulfill({ json: [1, 2].map(index => ({
    id: `clip-${index}`, kind: "clip", is_current: true, status: "pending_review", access_url: `https://example.test/clip-${index}.mp4`,
  })) }));

  await page.goto("/tasks/task-video-viewer");
  await page.getByRole("button", { name: "Open video clip 1 in viewer" }).click();

  const viewer = page.getByRole("dialog", { name: "Video viewer" });
  const video = viewer.locator("video");
  await expect(video).toHaveAttribute("controls", "");
  await expect(video).toHaveJSProperty("muted", true);
  await expect(viewer.getByRole("button", { name: "Approve" })).toBeVisible();
  await page.keyboard.press("ArrowRight");
  await expect(viewer.getByText("2 / 2", { exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(viewer).toHaveCount(0);
});

test("composition review separates approved shot segments from final composition review", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("access_token", "test"));
  await page.route("**/api/v1/auth/me", route => route.fulfill({ json: { id: "u", email: "u@test", role: "customer" } }));
  await page.route("**/api/v1/tasks/task-composition-review", route => route.fulfill({ json: {
    id: "task-composition-review", status: "composition_review", type: "promo", image_count: 2, progress_log: [],
  } }));
  await page.route("**/api/v1/tasks/task-composition-review/editing-blueprint", route => route.fulfill({ json: { entries: [] } }));
  await page.route("**/api/v1/tasks/task-composition-review/images", route => route.fulfill({ json: [] }));
  await page.route("**/api/v1/tasks/task-composition-review/video-candidates", route => route.fulfill({ json: [
    { id: "clip-1", kind: "clip", is_current: true, status: "approved", access_url: "https://example.test/clip-1.mp4" },
    { id: "composition-1", kind: "composition", is_current: true, status: "pending_review", access_url: "https://example.test/composition-1.mp4" },
  ] }));

  await page.goto("/tasks/task-composition-review");
  const approvedSegments = page.getByRole("region", { name: "Approved shot segments" });
  const composition = page.getByRole("region", { name: "Final composition review" });
  await expect(approvedSegments.getByRole("button", { name: "Approve" })).toHaveCount(0);
  await expect(composition.getByRole("button", { name: "Approve" })).toHaveCount(1);
  expect((await approvedSegments.boundingBox())!.y).toBeLessThan((await composition.boundingBox())!.y);
});

test("keyframe review opens a full-screen viewer with keyboard navigation", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("access_token", "test"));
  await page.route("**/api/v1/auth/me", route => route.fulfill({ json: { id: "u", email: "u@test", role: "customer" } }));
  await page.route("**/api/v1/tasks/task-keyframe-viewer", route => route.fulfill({ json: {
    id: "task-keyframe-viewer", status: "image_review", type: "promo", image_count: 2, progress_log: [],
  } }));
  await page.route("**/api/v1/tasks/task-keyframe-viewer/creative-brief", route => route.fulfill({ status: 404 }));
  await page.route("**/api/v1/tasks/task-keyframe-viewer/script", route => route.fulfill({ status: 404 }));
  await page.route("**/api/v1/tasks/task-keyframe-viewer/shot-plan", route => route.fulfill({ status: 404 }));
  await page.route("**/api/v1/tasks/task-keyframe-viewer/images", route => route.fulfill({ json: [
    { id: "keyframe-1", status: "pending_review", access_url: "https://example.test/keyframe-1.png", generation_context: {} },
    { id: "keyframe-2", status: "pending_review", access_url: "https://example.test/keyframe-2.png", generation_context: {} },
  ] }));
  await page.route("**/api/v1/tasks/task-keyframe-viewer/video-candidates", route => route.fulfill({ json: [] }));

  await page.goto("/tasks/task-keyframe-viewer");
  await page.getByRole("button", { name: "View keyframe 1" }).click();

  const viewer = page.getByRole("dialog", { name: "Keyframe viewer" });
  await expect(viewer.getByRole("img", { name: "Keyframe 1" })).toBeVisible();
  await page.keyboard.press("ArrowRight");
  await expect(viewer.getByRole("img", { name: "Keyframe 2" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(viewer).toHaveCount(0);
});

test("regenerating one keyframe keeps other keyframes reviewable", async ({ page }) => {
  let regenerationStarted = false;
  await page.addInitScript(() => localStorage.setItem("access_token", "test"));
  await page.route("**/api/v1/auth/me", route => route.fulfill({ json: { id: "u", email: "u@test", role: "customer" } }));
  await page.route("**/api/v1/tasks/task-batch", route => route.fulfill({ json: {
    id: "task-batch", status: regenerationStarted ? "imaging" : "image_review", type: "promo", image_count: 2, progress_log: [],
  } }));
  await page.route("**/api/v1/tasks/task-batch/creative-brief", route => route.fulfill({ json: { id: "brief-1", task_id: "task-batch", content: {}, status: "approved" } }));
  await page.route("**/api/v1/tasks/task-batch/script", route => route.fulfill({ json: {
    id: "script-1", task_id: "task-batch", content: "A script", edited_content: null, image_prompts: [], voiceover_text: "A script", status: "approved",
  } }));
  await page.route("**/api/v1/tasks/task-batch/shot-plan", route => route.fulfill({ json: { id: "plan-1", task_id: "task-batch", shots: [], status: "approved" } }));
  await page.route("**/api/v1/tasks/task-batch/images", route => route.fulfill({ json: [
    { id: "image-rejected", status: "rejected", access_url: "https://example.test/rejected.png", generation_context: {} },
    { id: "image-pending", status: "pending_review", access_url: "https://example.test/pending.png", generation_context: {} },
  ] }));
  await page.route("**/api/v1/tasks/task-batch/video-candidates", route => route.fulfill({ json: [] }));
  await page.route("**/api/v1/tasks/task-batch/images/image-rejected/regenerate", route => {
    regenerationStarted = true;
    return route.fulfill({ status: 202, json: { status: "queued" } });
  });

  await page.goto("/tasks/task-batch");
  await expect(page.getByRole("button", { name: "Approve" })).toHaveCount(1);
  await page.getByRole("button", { name: "Regen" }).first().click();
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("textbox").fill("Use a clearer product angle.");
  await dialog.getByRole("button", { name: "Confirm regeneration" }).click();

  await expect(page.getByText("Running · Generating Images", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve" })).toHaveCount(1);
});
