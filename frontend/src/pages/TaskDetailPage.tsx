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

const REVIEW_STATES = ["script_review", "image_review", "character_review", "video_review", "composition_review"];
const FINAL_STATES = ["done", "failed"];
const STEPS_DISPLAY = ["pending", "scripting", "script_review", "imaging", "image_review", "video_gen", "video_review", "compositing", "composition_review", "done"];
const SCRIPT_AVAILABLE_STATES = ["script_review", "imaging", "image_review", "video_gen", "compositing", "done"];

const STAGE_FOR_STEP: Record<string, string> = {
  analyze_source: "analysis", generate_script: "scripting", generate_rewritten_script: "scripting",
  generate_character: "character", generate_images: "imaging", generate_video_clips: "video_gen",
  generate_clips_and_voiceover: "video_gen", generate_voiceover: "video_gen",
  generate_tts_and_lipsync: "video_gen", composite_video: "compositing", composite: "compositing",
};

type LogEntry = { attempt?: number; stage?: string; step: string; status: string; summary?: string; time?: string; started_at?: string; finished_at?: string; duration_ms?: number };

function executionAttempts(log: LogEntry[]) {
  const attempts = new Map<number, Map<string, LogEntry[]>>();
  for (const entry of log) {
    const attempt = entry.attempt || 1;
    const stage = entry.stage || STAGE_FOR_STEP[entry.step] || "other";
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

export default function TaskDetailPage() {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const [task, setTask] = useState<any>(null);
  const [script, setScript] = useState<any>(null);
  const [images, setImages] = useState<any[]>([]);
  const [videoCandidates, setVideoCandidates] = useState<any[]>([]);
  const [editedContent, setEditedContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [videoSrc, setVideoSrc] = useState<string | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const actionRef = useRef(new Set<string>());
  const [busyActions, setBusyActions] = useState<string[]>([]);
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const runAction = async (key: string, action: () => Promise<void>) => {
    if (actionRef.current.has(key)) return;
    actionRef.current.add(key); setBusyActions([...actionRef.current]);
    try { await action(); } finally { actionRef.current.delete(key); setBusyActions([...actionRef.current]); }
  };

  const fetchData = useCallback(async () => {
    if (!id) return;
    const tdata = await api.get(`/tasks/${id}`).then(r => r.data).catch(() => null);
    if (!tdata) return;
    const [sdata, idata, vdata] = await Promise.all([
      SCRIPT_AVAILABLE_STATES.includes(tdata.status)
        ? api.get(`/tasks/${id}/script`).then(r => r.data).catch(() => null)
        : Promise.resolve(null),
      api.get(`/tasks/${id}/images`).then(r => r.data).catch(() => []),
      api.get(`/tasks/${id}/video-candidates`).then(r => r.data).catch(() => []),
    ]);
    if (tdata) setTask(tdata);
    if (sdata) { setScript(sdata); setEditedContent(sdata.edited_content || sdata.content); }
    if (idata.length > 0) setImages(idata);
    setVideoCandidates(vdata);
  }, [id]);

  useEffect(() => { fetchData(); }, [fetchData]);

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

  const approveScript = async () => {
    await runAction("script", async () => { setLoading(true); try { await api.put(`/tasks/${id}/script`, { approved: true, edited_content: editedContent }); await fetchData(); } finally { setLoading(false); } });
  };

  const approveCharacter = async () => {
    await runAction("character", async () => { setLoading(true); try { await api.put(`/tasks/${id}/script`, { approved: true }); await fetchData(); } finally { setLoading(false); } });
  };

  const reviewImage = async (imageId: string, action: "approve" | "reject") => {
    await runAction(`image:${imageId}`, async () => { await api.put(`/tasks/${id}/images/${imageId}`, { action }); const { data } = await api.get(`/tasks/${id}/images`); setImages(data); if (data.every((i: any) => i.status === "approved")) await fetchData(); });
  };

  const regenerateImage = async (imageId: string) => {
    await runAction(`image:${imageId}`, async () => { await api.post(`/tasks/${id}/images/${imageId}/regenerate`); const { data } = await api.get(`/tasks/${id}/images`); setImages(data); });
  };

  const reviewVideoCandidate = async (candidateId: string, action: "approve" | "reject") => {
    await runAction(`video:${candidateId}`, async () => { await api.put(`/tasks/${id}/video-candidates/${candidateId}`, { action }); await fetchData(); });
  };

  const regenerateVideoCandidate = async (candidateId: string) => {
    await runAction(`video:${candidateId}`, async () => { await api.post(`/tasks/${id}/video-candidates/${candidateId}/regenerate`); await fetchData(); });
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
  const statusLabel = String(t(`steps.${task.status}`, task.status.replace(/_/g, " ")));
  const titleKey = task.type === "promo" ? "task.promoTitle" : task.type === "viral" ? "task.viralTitle" : "task.personifyTitle";
  const nodeLabel = (step: string) => t(`execution.steps.${step}`, step.replace(/_/g, " "));
  const entrySummary = (entry: any) => {
    if (entry.summary) return String(entry.summary);
    const params = entry.params || {};
    return String(t(`execution.summaries.${entry.step}`, "", params));
  };
  const isOpenByDefault = (entries: LogEntry[]) => entries.some(entry => entry.status === "running" || entry.status === "error" || entry.status === "waiting");
  const toggle = (key: string, fallback: boolean) => setExpanded(current => ({ ...current, [key]: !(current[key] ?? fallback) }));

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1>{t(titleKey)}</h1>
          <p className="text-secondary text-sm mt-3">{t("task.status")}: {statusLabel}</p>
        </div>
        {task.status === "failed" && <span className="badge badge-failed">{t("task.failed")}</span>}
        {task.status === "done" && <span className="badge badge-done">{t("task.complete")}</span>}
      </div>

      {isProcessing && (
        <div className="card mb-6" style={{ background: "var(--accent-soft)", borderColor: "var(--accent)" }}>
          <div className="flex items-center justify-between">
            <div>
              <p style={{ fontWeight: 600, marginBottom: 4 }}>
                {task.status === "pending" ? t("task.readyToStart") : `${t("task.running")} — ${statusLabel}`}
              </p>
              <p className="text-secondary text-sm">
                {task.status === "pending" ? t("task.clickResume") : t("task.autoPolling")}
              </p>
            </div>
            {task.status === "pending" ? (
              <ResumeButton taskId={task.id} onResumed={fetchData} />
            ) : (
              <span style={{ color: "var(--accent)", fontSize: "0.85rem" }}>⏳</span>
            )}
          </div>
        </div>
      )}

      <div className="steps mb-6">
        {STEPS_DISPLAY.filter(s => !s.includes("review")).map((s, i) => {
          const realIdx = STEPS_DISPLAY.indexOf(s);
          const cls = realIdx < currentStepIdx || task.status === "done"
            ? "step done"
            : realIdx === currentStepIdx ? "step active" : "step";
          return <div key={s} className={cls}>{i + 1}. {t(`steps.${s}`, s)}</div>;
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
            const attemptDefault = attempt === attempts.at(-1)?.attempt;
            const attemptOpen = expanded[attemptKey] ?? attemptDefault;
            return <div key={attemptKey} style={{ marginTop: 10 }}>
              <button className="btn btn-ghost btn-sm" onClick={() => toggle(attemptKey, attemptDefault)} aria-expanded={attemptOpen}>
                {attemptOpen ? "▾" : "▸"} {t("execution.attempt", { number: attempt })}
              </button>
              {attemptOpen && stages.map(({ stage, entries }) => {
                const stageKey = `${attemptKey}:${stage}`;
                const stageDefault = isOpenByDefault(entries);
                const stageOpen = expanded[stageKey] ?? stageDefault;
                return <div key={stageKey} style={{ margin: "8px 0 0 14px", borderLeft: "2px solid var(--border)", paddingLeft: 10 }}>
                  <button className="btn btn-ghost btn-sm" onClick={() => toggle(stageKey, stageDefault)} aria-expanded={stageOpen}>
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

      {videoCandidates.filter(candidate => candidate.is_current).length > 0 && (
        <div className="card mb-6">
          <h3 className="mb-4">{task.status === "composition_review" ? "Final composition review" : "Video clip review"}</h3>
          {videoCandidates.filter(candidate => candidate.is_current).map(candidate => (
            <div key={candidate.id} className="mb-4">
              {candidate.access_url && <video src={candidate.access_url} controls style={{ width: "100%", borderRadius: "var(--radius)" }} />}
              <div className="flex gap-3 mt-3">
                {(task.status === "video_review" && candidate.kind === "clip" || task.status === "composition_review" && candidate.kind === "composition") && candidate.status === "pending_review" && <>
                  <button className="btn btn-primary btn-sm" onClick={() => reviewVideoCandidate(candidate.id, "approve")}>Approve</button>
                  <button className="btn btn-ghost btn-sm" onClick={() => regenerateVideoCandidate(candidate.id)}>{candidate.kind === "clip" ? "Regenerate clip" : "Recompose"}</button>
                </>}
              </div>
            </div>
          ))}
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
          </div>
        </div>
      )}

      {images.length > 0 && (
        <div className="card mb-6">
          <div className="flex items-center justify-between mb-6">
            <h3>{t("task.imageReview")}</h3>
            <span className="text-secondary text-sm">{images.filter((i: any) => i.status === "approved").length}/{images.length} {t("task.approved")}</span>
          </div>
          <div className="image-grid">
            {images.map((img: any) => (
              <div key={img.id} className="image-card">
                {img.access_url ? (
                  <img src={img.access_url} alt="" />
                ) : (
                  <div style={{ aspectRatio: "1", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)" }}>
                    {t("task.regenerating")}
                  </div>
                )}
                <div className="image-status">{img.status.replace(/_/g, " ")}</div>
                {task.status === "image_review" && (
                  <div className="image-actions">
                    {img.status === "pending_review" && img.access_url && (
                      <button className="btn btn-primary btn-sm" disabled={busyActions.includes(`image:${img.id}`)} style={{ flex: 1 }} onClick={() => reviewImage(img.id, "approve")}>{t("task.approve")}</button>
                    )}
                    {img.status !== "approved" && (
                      <button className="btn btn-ghost btn-sm" disabled={busyActions.includes(`image:${img.id}`)} style={{ flex: 1 }} onClick={() => reviewImage(img.id, "reject")}>{t("task.reject")}</button>
                    )}
                    {img.status === "rejected" && (
                      <button className="btn btn-ghost btn-sm" disabled={busyActions.includes(`image:${img.id}`)} style={{ flex: 1 }} onClick={() => regenerateImage(img.id)}>{t("task.regen")}</button>
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
          <button className="btn btn-primary" onClick={approveCharacter} disabled={loading}>
            {loading ? t("task.submitting") : t("task.approveCharacter")}
          </button>
        </div>
      )}
    </div>
  );
}
