import { useEffect, useState, useRef, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import api from "../api/client";

function ResumeButton({ taskId, onResumed }: { taskId: string; onResumed: () => void }) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  const resume = async () => {
    setLoading(true);
    try {
      await api.post(`/tasks/${taskId}/resume`);
      setDone(true);
      setTimeout(onResumed, 1500);
    } finally {
      setLoading(false);
    }
  };

  return (
    <button className="btn btn-primary btn-sm" onClick={resume} disabled={loading || done}>
      {done ? "✓" : loading ? t("task.starting") : t("task.resume")}
    </button>
  );
}

const REVIEW_STATES = ["creative_brief_review", "script_review", "shot_plan_review", "image_review", "character_review", "video_review", "composition_review"];
const FINAL_STATES = ["done", "failed", "cancelled"];
const STEPS_DISPLAY = ["pending", "planning", "creative_brief_review", "scripting", "script_review", "shot_plan_review", "imaging", "image_review", "video_gen", "video_review", "compositing", "composition_review", "done"];
const SCRIPT_AVAILABLE_STATES = ["script_review", "planning", "shot_plan_review", "imaging", "image_review", "video_gen", "compositing", "done"];
const SHOT_PLAN_AVAILABLE_STATES = ["shot_plan_review", "imaging", "image_review", "video_gen", "compositing", "done"];

const STAGE_FOR_STEP: Record<string, string> = {
  analyze_source: "analysis", generate_script: "scripting", generate_rewritten_script: "scripting",
  generate_character: "character", generate_images: "imaging", generate_video_clips: "video_gen",
  generate_clips_and_voiceover: "video_gen", generate_voiceover: "video_gen",
  generate_tts_and_lipsync: "video_gen", composite_video: "compositing", composite: "compositing",
};

const LEGACY_FEEDBACK_STAGE: Record<string, string> = {
  creative_brief: "planning", shot_plan: "planning", script: "scripting", image: "imaging",
  character: "character", video: "video_gen", composition: "compositing",
};

const PROGRESS_STAGE: Record<string, string> = {
  planning: "planning",
  scripting: "scripting",
  imaging: "imaging",
  video_gen: "video_gen",
  compositing: "compositing",
};

type LogEntry = { attempt?: number; stage?: string; step: string; status: string; summary?: string; time?: string; started_at?: string; finished_at?: string; duration_ms?: number };

function executionAttempts(log: LogEntry[]) {
  const attempts = new Map<number, Map<string, LogEntry[]>>();
  for (const entry of log) {
    const attempt = entry.attempt || 1;
    const stage = entry.step === "review_feedback"
      ? LEGACY_FEEDBACK_STAGE[entry.stage || ""] || "other"
      : entry.stage || STAGE_FOR_STEP[entry.step] || "other";
    if (!attempts.has(attempt)) attempts.set(attempt, new Map());
    const stages = attempts.get(attempt)!;
    if (!stages.has(stage)) stages.set(stage, []);
    stages.get(stage)!.push(entry);
  }
  return [...attempts.entries()].sort(([a], [b]) => a - b).map(([attempt, stages]) => ({
    attempt, stages: [...stages.entries()].map(([stage, entries]) => ({ stage, entries })),
  }));
}

function stepIndex(status: string) { return Math.max(0, STEPS_DISPLAY.indexOf(status)); }

type TaskDetailPageProps = {
  taskId?: string;
  onTaskLoaded?: (task: any) => void;
};

type FeedbackDialog = { title: string; submit: (feedback: string) => Promise<void> };

export default function TaskDetailPage({ taskId, onTaskLoaded }: TaskDetailPageProps) {
  const { t } = useTranslation();
  const { id: routeTaskId } = useParams<{ id: string }>();
  const id = taskId ?? routeTaskId;
  const [task, setTask] = useState<any>(null);
  const [script, setScript] = useState<any>(null);
  const [creativeBrief, setCreativeBrief] = useState<any>(null);
  const [shotPlan, setShotPlan] = useState<any>(null);
  const [editingBlueprint, setEditingBlueprint] = useState<any>(null);
  const [creativeBriefDraft, setCreativeBriefDraft] = useState("");
  const [shotPlanDraft, setShotPlanDraft] = useState("");
  const [images, setImages] = useState<any[]>([]);
  const [videoCandidates, setVideoCandidates] = useState<any[]>([]);
  const [editedContent, setEditedContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [videoSrc, setVideoSrc] = useState<string | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const videoPreviewRefs = useRef(new Map<string, HTMLVideoElement>());
  const actionRef = useRef(new Set<string>());
  const [busyActions, setBusyActions] = useState<string[]>([]);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [feedbackDialog, setFeedbackDialog] = useState<FeedbackDialog | null>(null);
  const [feedback, setFeedback] = useState("");
  const [viewerIndex, setViewerIndex] = useState<number | null>(null);
  const [viewerZoom, setViewerZoom] = useState(1);
  const [viewerPan, setViewerPan] = useState({ x: 0, y: 0 });
  const viewerDragRef = useRef<{ x: number; y: number } | null>(null);
  const [videoViewerIds, setVideoViewerIds] = useState<string[] | null>(null);
  const [videoViewerIndex, setVideoViewerIndex] = useState<number | null>(null);
  const [generationStage, setGenerationStage] = useState<string | null>(null);
  const [generationRecords, setGenerationRecords] = useState<any[]>([]);
  const [selectedGenerationRecord, setSelectedGenerationRecord] = useState<any>(null);
  const [sourcePreview, setSourcePreview] = useState<string | null>(null);
  const [stageModelSelections, setStageModelSelections] = useState<any[]>([]);
  const videoViewerRef = useRef<HTMLVideoElement | null>(null);
  const runAction = async (key: string, action: () => Promise<void>) => {
    if (actionRef.current.has(key)) return;
    actionRef.current.add(key); setBusyActions([...actionRef.current]);
    try { await action(); } finally { actionRef.current.delete(key); setBusyActions([...actionRef.current]); }
  };

  const fetchData = useCallback(async () => {
    if (!id) return;
    const tdata = await api.get(`/tasks/${id}`).then(r => r.data).catch(() => null);
    if (!tdata) return;
    const [bdata, sdata, pdata, edata, idata, vdata, selections] = await Promise.all([
      ["creative_brief_review", ...SCRIPT_AVAILABLE_STATES].includes(tdata.status)
        ? api.get(`/tasks/${id}/creative-brief`).then(r => r.data).catch(() => null)
        : Promise.resolve(null),
      SCRIPT_AVAILABLE_STATES.includes(tdata.status)
        ? api.get(`/tasks/${id}/script`).then(r => r.data).catch(() => null)
        : Promise.resolve(null),
      SHOT_PLAN_AVAILABLE_STATES.includes(tdata.status)
        ? api.get(`/tasks/${id}/shot-plan`).then(r => r.data).catch(() => null)
        : Promise.resolve(null),
      ["composition_review", "done"].includes(tdata.status)
        ? api.get(`/tasks/${id}/editing-blueprint`).then(r => r.data).catch(() => null)
        : Promise.resolve(null),
      api.get(`/tasks/${id}/images`).then(r => r.data).catch(() => []),
      api.get(`/tasks/${id}/video-candidates`).then(r => r.data).catch(() => []),
      api.get(`/tasks/${id}/stage-model-selections`).then(r => r.data).catch(() => []),
    ]);
    if (tdata) { setTask(tdata); onTaskLoaded?.(tdata); }
    setCreativeBrief(bdata);
    if (bdata) setCreativeBriefDraft(JSON.stringify(bdata.content, null, 2));
    setShotPlan(pdata);
    setEditingBlueprint(edata);
    if (pdata) setShotPlanDraft(JSON.stringify(pdata.shots, null, 2));
    if (sdata) { setScript(sdata); setEditedContent(sdata.edited_content || sdata.content); }
    if (idata.length > 0) setImages(idata);
    setVideoCandidates(vdata);
    setStageModelSelections(selections);
  }, [id, onTaskLoaded]);

  useEffect(() => { fetchData(); }, [fetchData]);

  useEffect(() => {
    if (viewerIndex === null) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setViewerIndex(null);
      if (event.key === "ArrowLeft") setViewerIndex(index => index === null ? null : (index - 1 + images.length) % images.length);
      if (event.key === "ArrowRight") setViewerIndex(index => index === null ? null : (index + 1) % images.length);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [viewerIndex, images.length]);

  useEffect(() => { setViewerZoom(1); setViewerPan({ x: 0, y: 0 }); }, [viewerIndex]);

  useEffect(() => {
    if (videoViewerIndex === null || !videoViewerIds) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { setVideoViewerIndex(null); setVideoViewerIds(null); }
      if (event.key === "ArrowLeft") { event.preventDefault(); setVideoViewerIndex(index => index === null ? null : (index - 1 + videoViewerIds.length) % videoViewerIds.length); }
      if (event.key === "ArrowRight") { event.preventDefault(); setVideoViewerIndex(index => index === null ? null : (index + 1) % videoViewerIds.length); }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [videoViewerIndex, videoViewerIds]);

  useEffect(() => {
    if (videoViewerIndex === null) return;
    for (const video of videoPreviewRefs.current.values()) video.pause();
    const video = videoViewerRef.current;
    if (video) { video.muted = true; video.currentTime = 0; void video.play().catch(() => undefined); }
  }, [videoViewerIndex]);

  // Local HyperFrames outputs are served by the authenticated API endpoint;
  // fetch them with axios so the bearer token is included, then give the
  // video element a browser-readable object URL.
  useEffect(() => {
    let objectUrl: string | null = null;
    if (!task?.result_video_asset_id || !id) {
      setVideoSrc(null);
      return;
    }
    api.get(`/tasks/${id}/video`, { responseType: "blob" }).then((response) => {
      objectUrl = URL.createObjectURL(response.data);
      setVideoSrc(objectUrl);
    }).catch(() => setVideoSrc(null));
    return () => { if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [task?.result_video_asset_id, id]);

  useEffect(() => {
    if (!task || FINAL_STATES.includes(task.status) || REVIEW_STATES.includes(task.status)) {
      if (pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null; }
      return;
    }
    if (!pollingRef.current) pollingRef.current = setInterval(fetchData, 3000);
    return () => { if (pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null; } };
  }, [task?.status, fetchData]);

  const doResume = async () => {
    await runAction("resume", async () => { setLoading(true); try { await api.post(`/tasks/${id}/resume`); await fetchData(); } finally { setLoading(false); } });
  };
  const cancelTask = async () => {
    if (!window.confirm(String(t("task.cancelConfirm")))) return;
    await runAction("cancel", async () => { await api.post(`/tasks/${id}/cancel`); await fetchData(); });
  };
  const deleteTask = async () => {
    if (!window.confirm(String(t("task.deleteConfirm")))) return;
    await runAction("delete", async () => { await api.delete(`/tasks/${id}`); window.location.assign("/dashboard"); });
  };

  const approveScript = async () => {
    await runAction("script", async () => { setLoading(true); try { await api.put(`/tasks/${id}/script`, { approved: true, edited_content: editedContent }); await fetchData(); } finally { setLoading(false); } });
  };
  const approveCreativeBrief = async () => {
    await runAction("creative-brief", async () => {
      await api.put(`/tasks/${id}/creative-brief`, { approved: true, content: JSON.parse(creativeBriefDraft) });
      await fetchData();
    });
  };
  const regenerateCreativeBrief = async (suggestion: string) => {
    await api.put(`/tasks/${id}/creative-brief`, { approved: false, feedback: suggestion });
    await fetchData();
  };
  const approveShotPlan = async () => {
    await runAction("shot-plan", async () => {
      await api.put(`/tasks/${id}/shot-plan`, { approved: true, shots: JSON.parse(shotPlanDraft) });
      await fetchData();
    });
  };
  const regenerateShotPlan = async (suggestion: string) => {
    await api.put(`/tasks/${id}/shot-plan`, { approved: false, feedback: suggestion });
    await fetchData();
  };

  const rejectScript = async (suggestion: string) => {
    await api.put(`/tasks/${id}/script`, { approved: false, feedback: suggestion });
    await fetchData();
  };

  const reviewCharacter = async (imageId: string, action: "approve" | "reject", suggestion?: string) => {
    await runAction("character", async () => { setLoading(true); try { await api.put(`/tasks/${id}/characters/${imageId}`, { action, feedback: suggestion }); await fetchData(); } finally { setLoading(false); } });
  };

  const reviewImage = async (imageId: string, action: "approve" | "reject") => {
    await runAction(`image:${imageId}`, async () => { await api.put(`/tasks/${id}/images/${imageId}`, { action }); const { data } = await api.get(`/tasks/${id}/images`); setImages(data); if (data.every((i: any) => i.status === "approved")) await fetchData(); });
  };

  const regenerateImage = async (imageId: string, suggestion: string) => {
    await runAction(`image:${imageId}`, async () => { await api.post(`/tasks/${id}/images/${imageId}/regenerate`, { feedback: suggestion }); await fetchData(); });
  };

  const reviewVideoCandidate = async (candidateId: string, action: "approve" | "reject") => {
    await runAction(`video:${candidateId}`, async () => { await api.put(`/tasks/${id}/video-candidates/${candidateId}`, { action }); await fetchData(); });
  };

  const playVideoPreview = (candidateId: string) => {
    for (const [id, video] of videoPreviewRefs.current) if (id !== candidateId) video.pause();
    void videoPreviewRefs.current.get(candidateId)?.play().catch(() => undefined);
  };

  const openKeyframeViewer = (index: number) => setViewerIndex(index);
  const moveViewer = (offset: number) => setViewerIndex(index => index === null ? null : (index + offset + images.length) % images.length);
  const openVideoViewer = (candidates: any[], candidateId: string) => {
    const ids = candidates.map(candidate => candidate.id);
    setVideoViewerIds(ids);
    setVideoViewerIndex(Math.max(0, ids.indexOf(candidateId)));
  };

  const regenerateVideoCandidate = async (candidateId: string, suggestion: string) => {
    await runAction(`video:${candidateId}`, async () => { await api.post(`/tasks/${id}/video-candidates/${candidateId}/regenerate`, { feedback: suggestion }); await fetchData(); });
  };

  const openGenerationMaterials = async (stage: string) => {
    if (!id) return;
    const records = await api.get(`/tasks/${id}/generation-records`, { params: { stage } }).then(response => response.data).catch(() => []);
    setGenerationStage(stage);
    setGenerationRecords(records);
    setSelectedGenerationRecord(records[0] || null);
  };

  const openFeedback = (title: string, submit: (suggestion: string) => Promise<void>) => {
    setFeedback("");
    setFeedbackDialog({ title, submit });
  };

  const submitFeedback = async () => {
    const suggestion = feedback.trim();
    if (suggestion.length < 5 || suggestion.length > 1000 || !feedbackDialog) return;
    await feedbackDialog.submit(suggestion);
    setFeedbackDialog(null);
  };

  if (!task) return <div className="empty-state"><p>{t("task.loading")}</p></div>;

  const log: LogEntry[] = Array.isArray(task.progress_log) ? task.progress_log : [];
  const attempts = executionAttempts(log);
  const effectiveStep = task.status === "failed" && task.current_step
    ? task.current_step
    : task.status;
  const currentStepIdx = stepIndex(effectiveStep);
  const isProcessing = !FINAL_STATES.includes(task.status) && !REVIEW_STATES.includes(task.status);
  const isReview = REVIEW_STATES.includes(task.status);
  const keyframesAreReviewable = task.status === "image_review" || task.status === "imaging";
  const statusLabel = String(t(`steps.${task.status}`, task.status.replace(/_/g, " ")));
  const titleKey = task.type === "promo" ? "task.promoTitle" : task.type === "viral" ? "task.viralTitle" : "task.personifyTitle";
  const taskName = task.product_snapshot?.name || String(t(titleKey));
  const categoryName = task.product_snapshot?.category?.name;
  const statusClass = task.status === "failed" ? "is-failed" : FINAL_STATES.includes(task.status) ? "is-done" : isReview ? "is-review" : "is-running";
  const nodeLabel = (step: string) => t(`execution.steps.${step}`, step.replace(/_/g, " "));
  const entrySummary = (entry: any) => {
    const summary = String(entry.summary || "");
    const scriptGenerated = summary.match(/^Script generated \((\d+) chars\)$/);
    if (scriptGenerated) return t("execution.summaries.scriptGeneratedWithCharacters", { characters: scriptGenerated[1] });
    const imagesGenerated = summary.match(/^Images: (\d+) generated\/reused$/);
    if (imagesGenerated) return t("execution.summaries.imagesGeneratedOrReused", { count: imagesGenerated[1] });
    const clipsGenerated = summary.match(/^Video clips: (\d+) generated$/);
    if (clipsGenerated) return t("execution.summaries.videoClipsGenerated", { count: clipsGenerated[1] });
    if (summary === "TTS audio generated") return t("execution.summaries.ttsAudioGenerated");
    if (summary.startsWith("Final video:")) return t("execution.summaries.finalVideoRendered");
    if (summary === "Waiting for user review") return t("execution.summaries.waitingForUserReview");
    if (summary === "Automatically approved by user preference") return t("execution.summaries.automaticallyApproved");
    if (summary === "Task cancelled") return t("execution.summaries.taskCancelled");
    if (summary === "Cancellation requested; no downstream steps will start") return t("execution.summaries.cancellationRequested");
    if (summary === "Improvement guidance recorded for regeneration") return t("execution.summaries.improvementGuidanceRecorded");
    const failedSubstep = summary.match(/^([^:]+): substep failed$/);
    if (failedSubstep) return t("execution.summaries.substepFailed", { errorType: failedSubstep[1] });
    if (summary) return summary;
    const params = entry.params || {};
    return String(t(`execution.summaries.${entry.step}`, "", params));
  };
  const toggle = (key: string, fallback: boolean) => setExpanded(current => ({ ...current, [key]: !(current[key] ?? fallback) }));
  const currentClipCandidates = videoCandidates.filter(candidate => candidate.is_current && candidate.kind === "clip");
  const reviewCandidates = videoCandidates.filter(candidate => candidate.is_current && (task.status === "composition_review" ? candidate.kind === "composition" : candidate.kind === "clip"));
  const videoViewerCandidates = videoViewerIds
    ? videoViewerIds.map(candidateId => videoCandidates.find(candidate => candidate.id === candidateId)).filter(Boolean)
    : [];
  const activeVideoViewerCandidate = videoViewerIndex === null ? null : videoViewerCandidates[videoViewerIndex];

  return (
    <div className="task-detail">
      <header className="task-context-header">
        <div>
          <span className="eyebrow">{t(titleKey)}</span>
          <h1>{taskName}</h1>
          <p className="task-context-meta">{categoryName && <span>{categoryName}</span>}<span>{statusLabel}</span>{task.created_at && <time>{new Date(task.created_at).toLocaleDateString()}</time>}</p>
        </div>
        <span className={`task-status-chip ${statusClass}`}>{statusLabel}</span>
      </header>

      <div className="flex gap-3 mb-6">
        {!FINAL_STATES.includes(task.status) && task.status !== "cancellation_requested" && <button className="btn btn-ghost btn-sm" disabled={busyActions.includes("cancel")} onClick={() => void cancelTask()}>{t("task.cancel")}</button>}
        {FINAL_STATES.includes(task.status) && <button className="btn btn-danger-ghost btn-sm" disabled={busyActions.includes("delete")} onClick={() => void deleteTask()}>{t("task.delete")}</button>}
      </div>

      {isProcessing && (
        <div className="task-live-status">
          <div>
            <strong>{task.status === "pending" ? t("task.readyToStart") : `${t("task.running")} · ${statusLabel}`}</strong>
            <span>{task.status === "pending" ? t("task.clickResume") : t("task.autoPolling")}</span>
          </div>
          {task.status === "pending" ? <ResumeButton taskId={task.id} onResumed={fetchData} /> : <span className="task-live-indicator" aria-hidden="true" />}
        </div>
      )}

      <div className="steps task-progress" aria-label={t("task.status")}>
        {STEPS_DISPLAY.filter(s => !s.includes("review")).map((s, i) => {
          const realIdx = STEPS_DISPLAY.indexOf(s);
          const cls = realIdx < currentStepIdx || task.status === "done"
            ? "step done"
            : realIdx === currentStepIdx ? "step active" : "step";
          const stage = PROGRESS_STAGE[s];
          const isCompletedStage = Boolean(stage && realIdx < currentStepIdx);
          const label = `${i + 1}. ${t(`steps.${s}`, s)}`;
          return isCompletedStage
            ? <button key={s} type="button" className={`${cls} task-progress-materials`} onClick={() => void openGenerationMaterials(stage)}>{label}</button>
            : <div key={s} className={cls}>{label}</div>;
        })}
      </div>

      {isReview && (
        <div className="card mb-6" style={{ background: "rgba(251,191,36,0.08)", borderColor: "var(--warning)" }}>
          <p style={{ fontWeight: 600, marginBottom: 4 }}>{t("task.awaitingReview")}</p>
          <p className="text-secondary text-sm">{t("task.reviewDesc")}</p>
        </div>
      )}

      {/* Progress log */}
      {log.length > 0 && (
        <section className="card mb-6" aria-label={t("execution.title")} style={{ borderColor: "var(--border)" }}>
          <h2 style={{ fontWeight: 600, fontSize: "0.9rem", padding: 4 }}>{t("execution.title")}</h2>
          {attempts.map(({ attempt, stages }) => {
            const attemptKey = `attempt:${attempt}`;
            const attemptDefault = false;
            const attemptOpen = expanded[attemptKey] ?? attemptDefault;
            return <div key={attemptKey} style={{ marginTop: 10 }}>
              <button className="btn btn-ghost btn-sm" onClick={() => toggle(attemptKey, attemptDefault)} aria-expanded={attemptOpen}>
                {attemptOpen ? "▾" : "▸"} {t("execution.attempt", { number: attempt })}
              </button>
              {attemptOpen && stages.map(({ stage, entries }) => {
                const stageKey = `${attemptKey}:${stage}`;
                const stageDefault = false;
                const stageOpen = expanded[stageKey] ?? stageDefault;
                return <div key={stageKey} style={{ margin: "8px 0 0 14px", borderLeft: "2px solid var(--border)", paddingLeft: 10 }}>
                  <button className="btn btn-ghost btn-sm" onClick={() => { toggle(stageKey, stageDefault); void openGenerationMaterials(stage); }} aria-expanded={stageOpen}>
                    {stageOpen ? "▾" : "▸"} {t(`execution.stages.${stage}`, stage.replace(/_/g, " "))}
                  </button>
                  {stageOpen && entries.map((entry, i) => <div key={`${entry.step}:${i}`} style={{ display: "flex", gap: 12, padding: "8px 0", fontSize: "0.82rem" }}>
                    <span style={{ color: entry.status === "error" ? "var(--danger)" : entry.status === "running" || entry.status === "waiting" ? "var(--warning)" : "var(--success)", fontWeight: 600, minWidth: 58 }}>
                      {entry.status === "error" ? t("execution.fail") : entry.status === "running" ? t("execution.running") : entry.status === "waiting" ? t("execution.waiting") : t("execution.ok")}
                    </span>
                    <div><div style={{ fontWeight: 500 }}>{nodeLabel(entry.step)}</div>
                      {entry.summary && <div style={{ color: entry.status === "error" ? "var(--danger)" : "var(--text-secondary)" }}>{entrySummary(entry)}</div>}
                      <div style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginTop: 2 }}>{entry.duration_ms != null ? t("execution.duration", { seconds: (entry.duration_ms / 1000).toFixed(1) }) : entry.started_at || entry.time ? new Date(entry.started_at || entry.time!).toLocaleTimeString() : ""}</div>
                    </div>
                  </div>)}
                </div>;
              })}
            </div>;
          })}
        </section>
      )}

      {generationStage && (
        <div className="generation-materials-backdrop" role="presentation" onMouseDown={() => setGenerationStage(null)}>
          <aside className="generation-materials-panel" role="dialog" aria-label={t("generationMaterials.title")} aria-modal="true" onMouseDown={event => event.stopPropagation()}>
            <header className="generation-materials-header">
              <div><span className="eyebrow">{t("generationMaterials.eyebrow")}</span><h2>{t("generationMaterials.title")}</h2><p>{t(`execution.stages.${generationStage}`, generationStage)}</p></div>
              <button className="btn btn-ghost btn-sm" aria-label={t("generationMaterials.close")} onClick={() => setGenerationStage(null)}>×</button>
            </header>
            {generationRecords.length === 0 ? <p className="generation-materials-empty">{t("generationMaterials.empty")}</p> : <div className="generation-materials-layout">
              <nav className="generation-materials-history" aria-label={t("generationMaterials.history")}>
                {generationRecords.map(record => <button key={record.id} className={selectedGenerationRecord?.id === record.id ? "is-selected" : ""} onClick={() => setSelectedGenerationRecord(record)}><span>{t("generationMaterials.attempt", { number: record.attempt })}</span><small>{record.model}</small></button>)}
              </nav>
              {selectedGenerationRecord && <article className="generation-materials-content">
                <section><h3>{t("generationMaterials.overview")}</h3><dl><div><dt>{t("generationMaterials.provider")}</dt><dd>{selectedGenerationRecord.provider} / {selectedGenerationRecord.model}</dd></div>{selectedGenerationRecord.model_resolution_snapshot?.selection_version && <div><dt>Model selection</dt><dd>{`Selection v${selectedGenerationRecord.model_resolution_snapshot.selection_version} · ${selectedGenerationRecord.model_resolution_snapshot.availability_status || "available"}`}</dd></div>}<div><dt>{t("generationMaterials.substep")}</dt><dd>{nodeLabel(selectedGenerationRecord.substep)}</dd></div><div><dt>{t("generationMaterials.provenance")}</dt><dd>{selectedGenerationRecord.provenance?.workflow_commit || "—"}</dd></div></dl></section>
                <section><h3>{t("generationMaterials.input")}</h3><pre>{JSON.stringify(selectedGenerationRecord.normalized_input, null, 2)}</pre></section>
                <section><h3>{t("generationMaterials.output")}</h3><pre>{JSON.stringify(selectedGenerationRecord.normalized_output, null, 2)}</pre></section>
                {selectedGenerationRecord.media_asset_ids?.length > 0 && <section><h3>{t("generationMaterials.mediaAssets")}</h3><ul className="generation-material-refs">{selectedGenerationRecord.media_asset_ids.map((assetId: string) => <li key={assetId}><code>{assetId}</code></li>)}</ul></section>}
                <section><h3>{t("generationMaterials.payload")}</h3><pre>{JSON.stringify(selectedGenerationRecord.provider_payload, null, 2)}</pre></section>
              </article>}
            </div>}
          </aside>
        </div>
      )}

      {stageModelSelections.length > 0 && <section className="card mt-6" aria-label={t("modelConfigurations.stageSelectionsTitle")}>
        <h2>{t("modelConfigurations.stageSelectionsTitle")}</h2>
        <ul>{stageModelSelections.map(selection => {
          const pending = selection.resolution_snapshot?.state === "pending_resolution";
          return <li key={selection.stage}>{selection.stage}: {pending ? t("modelConfigurations.pendingResolution") : `${selection.resolution_snapshot?.adapter || selection.resolution_snapshot?.provider} / ${selection.resolution_snapshot?.model_id}`} · Selection v{selection.selection_version} · {selection.availability_status}</li>;
        })}</ul>
      </section>}

      {task.error_message && (
        <div className="card mb-6" style={{ borderColor: "var(--danger)", background: "rgba(248,113,113,0.06)" }}>
          <p className="text-danger text-sm">{task.error_message}</p>
          <button className="btn btn-primary btn-sm mt-4" disabled={busyActions.includes("resume")} onClick={doResume}>{t("task.retry")}</button>
        </div>
      )}

      {task.status === "done" && (
        <div className="card mb-6" style={{ borderColor: "var(--success)", background: "rgba(52,211,153,0.06)" }}>
          <div className="flex items-center justify-between">
            <div>
              <p style={{ fontWeight: 600, marginBottom: 4, color: "var(--success)" }}>{t("task.videoComplete")}</p>
              <p className="text-secondary text-sm">{task.result_video_asset_id ? t("task.videoReady") : t("task.videoPending")}</p>
            </div>
            {task.result_video_asset_id && videoSrc && (
              <a href={videoSrc} download="video.mp4" className="btn btn-primary btn-sm" style={{ textDecoration: "none" }}>{t("task.download")}</a>
            )}
          </div>
        </div>
      )}

      {videoSrc && (
        <div className="card mb-6">
          <h3 className="mb-4">{t("task.yourVideo")}</h3>
          <video src={videoSrc} controls style={{ width: "100%", borderRadius: "var(--radius)" }} />
        </div>
      )}

      {task.status === "composition_review" && currentClipCandidates.length > 0 && (
        <section className="card mb-6 media-video-review" aria-label={t("task.approvedShotSegments")}><h3 className="mb-4">{t("task.approvedShotSegments")}</h3><div className="video-review-grid">
          {currentClipCandidates.map((candidate, index) => <article key={candidate.id} className="video-review-card">{candidate.access_url && <div className="video-preview-frame"><video ref={video => { if (video) videoPreviewRefs.current.set(candidate.id, video); else videoPreviewRefs.current.delete(candidate.id); }} src={candidate.access_url} controls muted playsInline preload="metadata" aria-label={t("task.videoClip", { number: index + 1 })} onPlay={() => playVideoPreview(candidate.id)} /><button type="button" className="video-preview-expand" aria-label={t("task.openVideoViewer", { number: index + 1 })} onClick={() => openVideoViewer(currentClipCandidates, candidate.id)}>⛶</button></div>}</article>)}
        </div></section>
      )}
      {reviewCandidates.length > 0 && (
        <section className="card mb-6 media-video-review" aria-label={task.status === "composition_review" ? t("task.finalCompositionReview") : t("task.shotSegments")}>
          <h3 className="mb-4">{task.status === "composition_review" ? t("task.finalCompositionReview") : t("task.shotSegments")}</h3>
          <div className="video-review-grid">
          {reviewCandidates.map((candidate, index) => (
            <article key={candidate.id} className="video-review-card">
              {candidate.access_url && <div className="video-preview-frame">
                <video ref={video => { if (video) videoPreviewRefs.current.set(candidate.id, video); else videoPreviewRefs.current.delete(candidate.id); }} src={candidate.access_url} controls muted playsInline preload="metadata" aria-label={t("task.videoClip", { number: index + 1 })} onPlay={() => playVideoPreview(candidate.id)} />
                <button type="button" className="video-preview-expand" aria-label={t("task.openVideoViewer", { number: index + 1 })} onClick={() => openVideoViewer(reviewCandidates, candidate.id)}>⛶</button>
              </div>}
              <div className="video-review-actions">
                {candidate.kind === "composition" && <>
                  <button className="btn btn-ghost btn-sm" onClick={() => setSourcePreview(`/api/v1/tasks/${id}/video-candidates/${candidate.id}/composition-source/preview`)}>Preview source</button>
                  <a className="btn btn-ghost btn-sm" href={`/api/v1/tasks/${id}/video-candidates/${candidate.id}/composition-source/download`}>Download HTML</a>
                  <button className="btn btn-ghost btn-sm" onClick={() => runAction(`replay:${candidate.id}`, async () => { await api.post(`/tasks/${id}/video-candidates/${candidate.id}/composition-source/replay`); await fetchData(); })}>Replay source</button>
                  <button className="btn btn-ghost btn-sm" onClick={() => runAction(`reconstruct:${candidate.id}`, async () => { await api.post(`/tasks/${id}/video-candidates/${candidate.id}/composition-source/reconstruct`); await fetchData(); })}>Reconstruct source</button>
                </>}
                {(task.status === "video_review" && candidate.kind === "clip" || task.status === "composition_review" && candidate.kind === "composition") && candidate.status === "pending_review" && <>
                  <button className="btn btn-primary btn-sm" onClick={() => reviewVideoCandidate(candidate.id, "approve")}>{t("task.approve")}</button>
                  <button className="btn btn-ghost btn-sm" onClick={() => openFeedback(String(candidate.kind === "clip" ? t("task.regenerateClip") : t("task.recompose")), suggestion => regenerateVideoCandidate(candidate.id, suggestion))}>{candidate.kind === "clip" ? t("task.regenerateClip") : t("task.recompose")}</button>
                </>}
              </div>
            </article>
          ))}
          </div>
        </section>
      )}

      {sourcePreview && <section className="card mb-6" aria-label="Composition source preview"><button className="btn btn-ghost btn-sm" onClick={() => setSourcePreview(null)}>Close preview</button><iframe title="Composition source preview" src={sourcePreview} sandbox="allow-same-origin" style={{ width: "100%", height: 560, border: 0, marginTop: 12 }} /></section>}
      {editingBlueprint && (
        <div className="card mb-6 media-keyframe-review">
          <h3 className="mb-4">{t("task.editingBlueprint")}</h3>
          <p className="text-secondary text-sm mb-4">{t("task.editingBlueprintDesc")}</p>
          <pre style={{ whiteSpace: "pre-wrap", color: "var(--text-secondary)", background: "var(--bg)", padding: 16, borderRadius: "var(--radius)" }}>{JSON.stringify(editingBlueprint.entries, null, 2)}</pre>
        </div>
      )}

      {creativeBrief && creativeBrief.status === "pending_review" && (
        <div className="card mb-6">
          <h3 className="mb-4">{t("task.creativeBrief")}</h3>
          <textarea className="textarea" value={creativeBriefDraft} onChange={e => setCreativeBriefDraft(e.target.value)} aria-label={t("task.creativeBriefJson")} />
          <div className="flex gap-3 mt-4">
            <button className="btn btn-primary" disabled={busyActions.includes("creative-brief")} onClick={() => void approveCreativeBrief()}>{t("task.approveGenerateScript")}</button>
            <button className="btn btn-ghost" onClick={() => openFeedback(String(t("task.regenerateCreativeBrief")), regenerateCreativeBrief)}>{t("task.regen")}</button>
          </div>
        </div>
      )}

      {script && script.status === "pending_review" && (
        <div className="card mb-6">
          <h3 className="mb-4">{t("task.scriptReview")}</h3>
          <div className="mb-6" style={{ whiteSpace: "pre-wrap", color: "var(--text-secondary)", fontSize: "0.9rem", lineHeight: 1.8, background: "var(--bg)", padding: 16, borderRadius: "var(--radius)" }}>
            {script.content}
          </div>
          <div className="form-group">
            <label className="form-label">{t("task.editScript")}</label>
            <textarea className="textarea" value={editedContent} onChange={e => setEditedContent(e.target.value)} />
          </div>
          <div className="flex gap-3 mt-4">
            <button className="btn btn-primary" onClick={approveScript} disabled={loading}>
              {loading ? t("task.submitting") : t("task.approveContinue")}
            </button>
            <button className="btn btn-ghost" onClick={() => openFeedback(t("task.requestRewrite"), rejectScript)} disabled={loading}>{t("task.requestRewrite")}</button>
          </div>
        </div>
      )}

      {shotPlan && shotPlan.status === "pending_review" && (
        <div className="card mb-6">
          <h3 className="mb-4">{t("task.shotPlan")}</h3>
          <p className="text-secondary text-sm mb-4">{t("task.shotPlanDesc")}</p>
          <textarea className="textarea" value={shotPlanDraft} onChange={e => setShotPlanDraft(e.target.value)} aria-label={t("task.shotPlanJson")} />
          <div className="flex gap-3 mt-4">
            <button className="btn btn-primary" disabled={busyActions.includes("shot-plan")} onClick={() => void approveShotPlan()}>{t("task.approveGenerateKeyframes")}</button>
            <button className="btn btn-ghost" onClick={() => openFeedback(String(t("task.regenerateShotPlan")), regenerateShotPlan)}>{t("task.regen")}</button>
          </div>
        </div>
      )}

      {images.length > 0 && (
        <div className="card mb-6 media-keyframe-review">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h3>{shotPlan ? t("task.keyframeReview") : t("task.imageReview")}</h3>
              {shotPlan && <p className="text-secondary text-sm">{t("task.keyframeReviewDesc")}</p>}
            </div>
            <span className="text-secondary text-sm">{images.filter((i: any) => i.status === "approved").length}/{images.length} {t("task.approved")}</span>
          </div>
          <div className="image-grid">
            {images.map((img: any, imageIndex: number) => (
              <div key={img.id} className="image-card">
                {img.access_url ? (
                  <button type="button" className="keyframe-open" aria-label={t("task.viewKeyframe", { number: imageIndex + 1 })} onClick={() => openKeyframeViewer(imageIndex)}><img src={img.access_url} alt="" /></button>
                ) : (
                  <div style={{ aspectRatio: "1", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)" }}>
                    {t("task.regenerating")}
                  </div>
                )}
                <div className="image-status">{img.status.replace(/_/g, " ")}</div>
                {img.generation_context?.keyframe_role && <div className="text-secondary text-sm">{t("task.keyframeLocation", { shot: Number(img.generation_context.shot_index) + 1, segment: Number(img.generation_context.segment_index) + 1, role: t(`task.keyframeRole${img.generation_context.keyframe_role === "end" ? "End" : "Start"}`) })}</div>}
                {keyframesAreReviewable && (
                  <div className="image-actions">
                    {img.status === "pending_review" && img.access_url && (
                      <button className="btn btn-primary btn-sm" disabled={busyActions.includes(`image:${img.id}`)} style={{ flex: 1 }} onClick={() => reviewImage(img.id, "approve")}>{t("task.approve")}</button>
                    )}
                    {img.status !== "approved" && (
                      <button className="btn btn-ghost btn-sm" disabled={busyActions.includes(`image:${img.id}`)} style={{ flex: 1 }} onClick={() => openFeedback(t("task.regen"), suggestion => regenerateImage(img.id, suggestion))}>{t("task.regen")}</button>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {task.status === "character_review" && (
        <div className="card mb-6">
          <h3 className="mb-4">{t("task.characterReview")}</h3>
          <p className="text-secondary mb-6">{t("task.characterDesc")}</p>
          {images.find(image => image.prompt === "character")?.access_url && <img className="image-preview" src={images.find(image => image.prompt === "character").access_url} alt={t("task.characterReview")} />}
          <button className="btn btn-primary" onClick={() => { const image = images.find(item => item.prompt === "character"); if (image) void reviewCharacter(image.id, "approve"); }} disabled={loading}>
            {loading ? t("task.submitting") : t("task.approveCharacter")}
          </button>
          <button className="btn btn-ghost ml-3" onClick={() => { const image = images.find(item => item.prompt === "character"); if (image) openFeedback(t("task.regenerateCharacter"), suggestion => reviewCharacter(image.id, "reject", suggestion)); }} disabled={loading}>{t("task.regenerateCharacter")}</button>
        </div>
      )}
      {viewerIndex !== null && images[viewerIndex] && (
        <div className="keyframe-viewer-backdrop" role="presentation">
          <section className="keyframe-viewer" role="dialog" aria-modal="true" aria-label={t("task.keyframeViewer")}>
            <header><span>{viewerIndex + 1} / {images.length}</span><div><button type="button" className="btn btn-ghost btn-sm" onClick={() => { setViewerZoom(1); setViewerPan({ x: 0, y: 0 }); }}>{t("task.fitToScreen")}</button><button type="button" className="btn btn-ghost btn-sm" onClick={() => { setViewerZoom(1); setViewerPan({ x: 0, y: 0 }); }}>{t("task.actualSize")}</button><button type="button" className="btn btn-ghost btn-sm" aria-label={t("task.closeViewer")} onClick={() => setViewerIndex(null)}>×</button></div></header>
            <div className="keyframe-viewer-body">
              <button type="button" className="keyframe-nav" aria-label={t("task.previousKeyframe")} onClick={() => moveViewer(-1)}>‹</button>
              <div className="keyframe-canvas" onWheel={event => { event.preventDefault(); setViewerZoom(value => Math.min(3, Math.max(.5, value + (event.deltaY < 0 ? .15 : -.15)))); }} onPointerDown={event => { viewerDragRef.current = { x: event.clientX, y: event.clientY }; event.currentTarget.setPointerCapture(event.pointerId); }} onPointerMove={event => { if (!viewerDragRef.current) return; setViewerPan(value => ({ x: value.x + event.clientX - viewerDragRef.current!.x, y: value.y + event.clientY - viewerDragRef.current!.y })); viewerDragRef.current = { x: event.clientX, y: event.clientY }; }} onPointerUp={() => { viewerDragRef.current = null; }}>
                <img src={images[viewerIndex].access_url} alt={`Keyframe ${viewerIndex + 1}`} style={{ transform: `translate(${viewerPan.x}px, ${viewerPan.y}px) scale(${viewerZoom})` }} />
              </div>
              <button type="button" className="keyframe-nav" aria-label={t("task.nextKeyframe")} onClick={() => moveViewer(1)}>›</button>
              <aside className="keyframe-viewer-actions"><p>{t("task.keyframeLocation", { shot: Number(images[viewerIndex].generation_context?.shot_index || 0) + 1, segment: Number(images[viewerIndex].generation_context?.segment_index || 0) + 1, role: t(`task.keyframeRole${images[viewerIndex].generation_context?.keyframe_role === "end" ? "End" : "Start"}`) })}</p><button className="btn btn-primary" onClick={() => reviewImage(images[viewerIndex].id, "approve")}>{t("task.approve")}</button><button className="btn btn-ghost" onClick={() => openFeedback(t("task.regen"), suggestion => regenerateImage(images[viewerIndex].id, suggestion))}>{t("task.regen")}</button></aside>
            </div>
          </section>
        </div>
      )}
      {activeVideoViewerCandidate?.access_url && videoViewerIndex !== null && (
        <div className="keyframe-viewer-backdrop" role="presentation">
          <section className="video-viewer" role="dialog" aria-modal="true" aria-label={t("task.videoViewer")}>
            <header><span>{videoViewerIndex + 1} / {videoViewerCandidates.length}</span><button type="button" className="btn btn-ghost btn-sm" aria-label={t("task.closeViewer")} onClick={() => { setVideoViewerIndex(null); setVideoViewerIds(null); }}>×</button></header>
            <div className="video-viewer-body">
              <button type="button" className="keyframe-nav" aria-label={t("task.previousShotSegment")} onClick={() => setVideoViewerIndex(index => index === null ? null : (index - 1 + videoViewerCandidates.length) % videoViewerCandidates.length)}>‹</button>
              <video key={activeVideoViewerCandidate.id} ref={videoViewerRef} src={activeVideoViewerCandidate.access_url} controls muted autoPlay playsInline />
              <button type="button" className="keyframe-nav" aria-label={t("task.nextShotSegment")} onClick={() => setVideoViewerIndex(index => index === null ? null : (index + 1) % videoViewerCandidates.length)}>›</button>
              <aside className="keyframe-viewer-actions">
                {activeVideoViewerCandidate.status === "pending_review" && ((task.status === "video_review" && activeVideoViewerCandidate.kind === "clip") || (task.status === "composition_review" && activeVideoViewerCandidate.kind === "composition")) && <><button className="btn btn-primary" onClick={() => reviewVideoCandidate(activeVideoViewerCandidate.id, "approve")}>{t("task.approve")}</button><button className="btn btn-ghost" onClick={() => openFeedback(String(activeVideoViewerCandidate.kind === "clip" ? t("task.regenerateClip") : t("task.recompose")), suggestion => regenerateVideoCandidate(activeVideoViewerCandidate.id, suggestion))}>{activeVideoViewerCandidate.kind === "clip" ? t("task.regenerateClip") : t("task.recompose")}</button></>}
              </aside>
            </div>
          </section>
        </div>
      )}
      {feedbackDialog && (
        <div className="review-feedback-backdrop" role="presentation">
          <section className="review-feedback-dialog" role="dialog" aria-modal="true" aria-labelledby="review-feedback-title">
            <h2 id="review-feedback-title">{feedbackDialog.title}</h2>
            <p className="text-secondary text-sm">{t("task.feedbackHelp")}</p>
            <textarea autoFocus className="textarea" value={feedback} onChange={event => setFeedback(event.target.value)} minLength={5} maxLength={1000} />
            <p className="text-secondary text-sm">{feedback.trim().length}/1000</p>
            <div className="task-create-actions"><button className="btn btn-ghost" onClick={() => setFeedbackDialog(null)}>{t("products.cancel")}</button><button className="btn btn-primary" disabled={feedback.trim().length < 5 || feedback.trim().length > 1000} onClick={() => void submitFeedback()}>{t("task.confirmRegeneration")}</button></div>
          </section>
        </div>
      )}
    </div>
  );
}
