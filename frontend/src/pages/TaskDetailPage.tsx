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

const REVIEW_STATES = ["script_review", "image_review", "character_review"];
const FINAL_STATES = ["done", "failed"];
const STEPS_DISPLAY = ["pending", "scripting", "script_review", "imaging", "image_review", "video_gen", "compositing", "done"];
const SCRIPT_AVAILABLE_STATES = ["script_review", "imaging", "image_review", "video_gen", "compositing", "done"];

function stepIndex(status: string) { return Math.max(0, STEPS_DISPLAY.indexOf(status)); }

export default function TaskDetailPage() {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const [task, setTask] = useState<any>(null);
  const [script, setScript] = useState<any>(null);
  const [images, setImages] = useState<any[]>([]);
  const [editedContent, setEditedContent] = useState("");
  const [loading, setLoading] = useState(false);
  const [videoSrc, setVideoSrc] = useState<string | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const actionRef = useRef(new Set<string>());
  const [busyActions, setBusyActions] = useState<string[]>([]);
  const runAction = async (key: string, action: () => Promise<void>) => {
    if (actionRef.current.has(key)) return;
    actionRef.current.add(key); setBusyActions([...actionRef.current]);
    try { await action(); } finally { actionRef.current.delete(key); setBusyActions([...actionRef.current]); }
  };

  const fetchData = useCallback(async () => {
    if (!id) return;
    const tdata = await api.get(`/tasks/${id}`).then(r => r.data).catch(() => null);
    if (!tdata) return;
    const [sdata, idata] = await Promise.all([
      SCRIPT_AVAILABLE_STATES.includes(tdata.status)
        ? api.get(`/tasks/${id}/script`).then(r => r.data).catch(() => null)
        : Promise.resolve(null),
      api.get(`/tasks/${id}/images`).then(r => r.data).catch(() => []),
    ]);
    if (tdata) setTask(tdata);
    if (sdata) { setScript(sdata); setEditedContent(sdata.edited_content || sdata.content); }
    if (idata.length > 0) setImages(idata);
  }, [id]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // Local HyperFrames outputs are served by the authenticated API endpoint;
  // fetch them with axios so the bearer token is included, then give the
  // video element a browser-readable object URL.
  useEffect(() => {
    let objectUrl: string | null = null;
    if (!task?.result_video_url || !id) {
      setVideoSrc(null);
      return;
    }
    api.get(`/tasks/${id}/video`, { responseType: "blob" }).then((response) => {
      objectUrl = URL.createObjectURL(response.data);
      setVideoSrc(objectUrl);
    }).catch(() => setVideoSrc(null));
    return () => { if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [task?.result_video_url, id]);

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

  if (!task) return <div className="empty-state"><p>{t("task.loading")}</p></div>;

  const log = Array.isArray(task.progress_log) ? task.progress_log : [];
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
    const params = entry.params || {};
    return String(t(`execution.summaries.${entry.step}`, entry.summary, params));
  };

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
        <div className="card mb-6" style={{ background: task.status === "pending" ? "rgba(124,92,252,0.06)" : "rgba(124,92,252,0.04)", borderColor: "var(--accent)" }}>
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
        <details className="card mb-6" style={{ borderColor: "var(--border)" }}>
          <summary style={{ cursor: "pointer", fontWeight: 600, fontSize: "0.9rem", padding: 4 }}>
            {t("execution.title")} ({log.length} {t("execution.stepsCount")})
          </summary>
          <div style={{ marginTop: 16 }}>
            {log.map((entry: any, i: number) => (
              <div key={i} style={{
                display: "flex", gap: 12, padding: "10px 0", borderBottom: "1px solid var(--border)",
                fontSize: "0.82rem", alignItems: "flex-start"
              }}>
                <span style={{
                  color: entry.status === "error" ? "var(--danger)" : "var(--success)",
                  fontWeight: 600, minWidth: 48
                }}>
                  {entry.status === "error" ? t("execution.fail") : t("execution.ok")}
                </span>
                <div>
                  <div style={{ color: "var(--text)", fontWeight: 500 }}>{nodeLabel(entry.step)}</div>
                  <div style={{ color: entry.status === "error" ? "var(--danger)" : "var(--text-secondary)" }}>
                    {entrySummary(entry)}
                  </div>
                  <div style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginTop: 2 }}>
                    {new Date(entry.time).toLocaleTimeString()}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </details>
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
              <p className="text-secondary text-sm">{task.result_video_url ? t("task.videoReady") : t("task.videoPending")}</p>
            </div>
            {task.result_video_url && videoSrc && (
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
                {img.image_url ? (
                  <img src={img.image_url} alt="" />
                ) : (
                  <div style={{ aspectRatio: "1", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)" }}>
                    {t("task.regenerating")}
                  </div>
                )}
                <div className="image-status">{img.status.replace(/_/g, " ")}</div>
                {task.status === "image_review" && (
                  <div className="image-actions">
                    {img.status === "pending_review" && img.image_url && (
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
