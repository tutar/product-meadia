import { useEffect, useState, useRef, useCallback } from "react";
import { useParams } from "react-router-dom";
import api from "../api/client";

const STEP_LABELS: Record<string, string> = {
  pending: "Queued", scripting: "Writing Script", script_review: "Review Script",
  imaging: "Generating Images", image_review: "Review Images",
  character_review: "Review Character", video_gen: "Generating Video",
  compositing: "Compositing", done: "Complete", failed: "Failed",
};

const STEPS = ["pending", "scripting", "script_review", "imaging", "image_review", "video_gen", "compositing", "done"];

const REVIEW_STATES = ["script_review", "image_review", "character_review"];
const FINAL_STATES = ["done", "failed"];
const PROCESSING_STATES = ["pending", "scripting", "imaging", "video_gen", "compositing"];

function stepIndex(status: string) { return Math.max(0, STEPS.indexOf(status)); }

export default function TaskDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [task, setTask] = useState<any>(null);
  const [script, setScript] = useState<any>(null);
  const [images, setImages] = useState<any[]>([]);
  const [editedContent, setEditedContent] = useState("");
  const [loading, setLoading] = useState(false);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchData = useCallback(async () => {
    if (!id) return;
    const [t, s, imgs] = await Promise.all([
      api.get(`/tasks/${id}`).then(r => r.data).catch(() => null),
      api.get(`/tasks/${id}/script`).then(r => r.data).catch(() => null),
      api.get(`/tasks/${id}/images`).then(r => r.data).catch(() => []),
    ]);
    if (t) setTask(t);
    if (s) { setScript(s); setEditedContent(s.edited_content || s.content); }
    if (imgs.length > 0) setImages(imgs);
  }, [id]);

  // Initial load
  useEffect(() => { fetchData(); }, [fetchData]);

  // Auto-poll when processing
  useEffect(() => {
    if (!task || FINAL_STATES.includes(task.status) || REVIEW_STATES.includes(task.status)) {
      if (pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null; }
      return;
    }
    if (!pollingRef.current) {
      pollingRef.current = setInterval(fetchData, 3000);
    }
    return () => { if (pollingRef.current) { clearInterval(pollingRef.current); pollingRef.current = null; } };
  }, [task?.status, fetchData]);

  const doResume = async () => {
    setLoading(true);
    await api.post(`/tasks/${id}/resume`);
    await fetchData();
    setLoading(false);
  };

  const approveScript = async () => {
    setLoading(true);
    await api.put(`/tasks/${id}/script`, { approved: true, edited_content: editedContent });
    await api.post(`/tasks/${id}/resume`);
    await fetchData();
    setLoading(false);
  };

  const approveCharacter = async () => {
    setLoading(true);
    await api.put(`/tasks/${id}/script`, { approved: true });
    await api.post(`/tasks/${id}/resume`);
    await fetchData();
    setLoading(false);
  };

  const reviewImage = async (imageId: string, action: "approve" | "reject") => {
    await api.put(`/tasks/${id}/images/${imageId}`, { action });
    const { data } = await api.get(`/tasks/${id}/images`);
    setImages(data);
    // If all approved, trigger resume
    if (data.every((i: any) => i.status === "approved")) {
      await api.post(`/tasks/${id}/resume`);
      await fetchData();
    }
  };

  const regenerateImage = async (imageId: string) => {
    await api.post(`/tasks/${id}/images/${imageId}/regenerate`);
    const { data } = await api.get(`/tasks/${id}/images`);
    setImages(data);
  };

  if (!task) return <div className="empty-state"><p>Loading...</p></div>;

  const currentStepIdx = stepIndex(task.status);
  const isProcessing = PROCESSING_STATES.includes(task.status);
  const isReview = REVIEW_STATES.includes(task.status);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1>{task.type === "promo" ? "Promotional Video" : task.type === "viral" ? "Viral Remix" : "Personification"}</h1>
          <p className="text-secondary text-sm mt-3">Status: {STEP_LABELS[task.status] || task.status}</p>
        </div>
        {task.status === "failed" && <span className="badge badge-failed">Failed</span>}
        {task.status === "done" && <span className="badge badge-done">Complete</span>}
      </div>

      {/* Processing card */}
      {isProcessing && (
        <div className="card mb-6" style={{ background: task.status === "pending" ? "rgba(124,92,252,0.06)" : "rgba(124,92,252,0.04)", borderColor: "var(--accent)" }}>
          <div className="flex items-center justify-between">
            <div>
              <p style={{ fontWeight: 600, marginBottom: 4 }}>
                {task.status === "pending" ? "Ready to start" : `Running — ${STEP_LABELS[task.status]}`}
              </p>
              <p className="text-secondary text-sm">
                {task.status === "pending"
                  ? "Click Resume to start the AI pipeline."
                  : "The AI is working on this step. Progress updates automatically."}
              </p>
            </div>
            {task.status === "pending" ? (
              <button className="btn btn-primary btn-sm" onClick={doResume} disabled={loading}>
                {loading ? "Starting..." : "Resume"}
              </button>
            ) : (
              <span style={{ color: "var(--accent)", fontSize: "0.85rem" }}>
                {loading ? "Working..." : "Auto-polling..."}
              </span>
            )}
          </div>
        </div>
      )}

      {/* Progress steps */}
      {!FINAL_STATES.includes(task.status) && (
        <div className="steps mb-6">
          {STEPS.filter(s => !s.includes("review")).map((s, i) => {
            const realIdx = STEPS.indexOf(s);
            const cls = realIdx < currentStepIdx ? "step done" : realIdx === currentStepIdx ? "step active" : "step";
            return <div key={s} className={cls}>{i + 1}. {STEP_LABELS[s]}</div>;
          })}
        </div>
      )}

      {/* Review notice */}
      {isReview && (
        <div className="card mb-6" style={{ background: "rgba(251,191,36,0.08)", borderColor: "var(--warning)" }}>
          <p style={{ fontWeight: 600, marginBottom: 4 }}>Awaiting your review</p>
          <p className="text-secondary text-sm">Review and approve the content below to continue.</p>
        </div>
      )}

      {/* Error */}
      {task.error_message && (
        <div className="card mb-6" style={{ borderColor: "var(--danger)", background: "rgba(248,113,113,0.06)" }}>
          <p className="text-danger text-sm">{task.error_message}</p>
          <button className="btn btn-primary btn-sm mt-4" onClick={doResume}>Retry</button>
        </div>
      )}

      {/* Video output */}
      {task.result_video_url && (
        <div className="card mb-6">
          <h3 className="mb-4">Your Video</h3>
          <video src={task.result_video_url} controls style={{ width: "100%", borderRadius: "var(--radius)" }} />
        </div>
      )}

      {/* Script Review */}
      {script && script.status === "pending_review" && (
        <div className="card mb-6">
          <h3 className="mb-4">Script Review</h3>
          <div className="mb-6" style={{ whiteSpace: "pre-wrap", color: "var(--text-secondary)", fontSize: "0.9rem", lineHeight: 1.8, background: "var(--bg)", padding: 16, borderRadius: "var(--radius)" }}>
            {script.content}
          </div>
          <div className="form-group">
            <label className="form-label">Edit script (optional)</label>
            <textarea className="textarea" value={editedContent} onChange={e => setEditedContent(e.target.value)} />
          </div>
          <div className="flex gap-3 mt-4">
            <button className="btn btn-primary" onClick={approveScript} disabled={loading}>
              {loading ? "Submitting..." : "Approve & Continue"}
            </button>
          </div>
        </div>
      )}

      {/* Image Review */}
      {images.length > 0 && (
        <div className="card mb-6">
          <div className="flex items-center justify-between mb-6">
            <h3>Image Review</h3>
            <span className="text-secondary text-sm">{images.filter((i: any) => i.status === "approved").length}/{images.length} approved</span>
          </div>
          <div className="image-grid">
            {images.map((img: any) => (
              <div key={img.id} className="image-card">
                {img.image_url ? (
                  <img src={img.image_url} alt="" />
                ) : (
                  <div style={{ aspectRatio: "1", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--text-muted)" }}>
                    Regenerating...
                  </div>
                )}
                <div className="image-status">{img.status.replace(/_/g, " ")}</div>
                <div className="image-actions">
                  {img.status === "pending_review" && img.image_url && (
                    <button className="btn btn-primary btn-sm" style={{ flex: 1 }} onClick={() => reviewImage(img.id, "approve")}>Approve</button>
                  )}
                  {img.status !== "approved" && (
                    <button className="btn btn-ghost btn-sm" style={{ flex: 1 }} onClick={() => reviewImage(img.id, "reject")}>Reject</button>
                  )}
                  {img.status === "rejected" && (
                    <button className="btn btn-ghost btn-sm" style={{ flex: 1 }} onClick={() => regenerateImage(img.id)}>Regen</button>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Character Review */}
      {task.status === "character_review" && (
        <div className="card mb-6">
          <h3 className="mb-4">Character Review</h3>
          <p className="text-secondary mb-6">Review the AI-generated character before continuing.</p>
          <button className="btn btn-primary" onClick={approveCharacter} disabled={loading}>
            {loading ? "Submitting..." : "Approve Character"}
          </button>
        </div>
      )}
    </div>
  );
}
