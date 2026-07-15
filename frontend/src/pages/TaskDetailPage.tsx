import { useEffect, useState, useRef } from "react";
import { useParams } from "react-router-dom";
import api from "../api/client";

function ResumeButton({ taskId }: { taskId: string }) {
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  const resume = async () => {
    setLoading(true);
    try {
      await api.post(`/tasks/${taskId}/resume`);
      setDone(true);
      setTimeout(() => window.location.reload(), 1500);
    } finally {
      setLoading(false);
    }
  };

  return (
    <button className="btn btn-primary btn-sm" onClick={resume} disabled={loading || done}>
      {done ? "Resumed!" : loading ? "Resuming..." : "Resume"}
    </button>
  );
}

const STEP_LABELS: Record<string, string> = {
  pending: "Queued", scripting: "Writing Script", script_review: "Review Script",
  imaging: "Generating Images", image_review: "Review Images",
  character_review: "Review Character", video_gen: "Generating Video",
  compositing: "Compositing", done: "Complete", failed: "Failed",
};

const STEPS = ["pending", "scripting", "script_review", "imaging", "image_review", "video_gen", "compositing", "done"];

function stepIndex(status: string) {
  const idx = STEPS.indexOf(status);
  return idx >= 0 ? idx : -1;
}

export default function TaskDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [task, setTask] = useState<any>(null);
  const [script, setScript] = useState<any>(null);
  const [images, setImages] = useState<any[]>([]);
  const [editedContent, setEditedContent] = useState("");
  const [scriptLoading, setScriptLoading] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    api.get(`/tasks/${id}`).then(r => setTask(r.data)).catch(() => {});
    api.get(`/tasks/${id}/script`).then(r => { setScript(r.data); setEditedContent(r.data.edited_content || r.data.content); }).catch(() => {});
    api.get(`/tasks/${id}/images`).then(r => setImages(r.data)).catch(() => {});

    const ws = new WebSocket(`ws://localhost:8000/ws/tasks/${id}`);
    ws.onmessage = (e) => {
      const p = JSON.parse(e.data);
      if (p.status === "done") setTask((prev: any) => ({ ...prev, status: "done", result_video_url: p.video_url }));
      if (p.status === "failed") setTask((prev: any) => ({ ...prev, status: "failed", error_message: p.error }));
    };
    wsRef.current = ws;
    return () => ws.close();
  }, [id]);

  const approveScript = async () => {
    setScriptLoading(true);
    await api.put(`/tasks/${id}/script`, { approved: true, edited_content: editedContent });
    setTask((prev: any) => ({ ...prev, status: "imaging" }));
    setScriptLoading(false);
  };

  const reviewImage = async (imageId: string, action: "approve" | "reject") => {
    await api.put(`/tasks/${id}/images/${imageId}`, { action });
    const { data } = await api.get(`/tasks/${id}/images`);
    setImages(data);
  };

  if (!task) return <div className="empty-state"><p>Loading...</p></div>;

  const currentStepIdx = stepIndex(task.status);

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

      {/* Stuck / Resume hint */}
      {!["done", "failed", "script_review", "image_review", "character_review"].includes(task.status) && (
        <div className="card mb-6" style={{ background: "rgba(124,92,252,0.06)", borderColor: "var(--accent)" }}>
          <div className="flex items-center justify-between">
            <div>
              <p style={{ fontWeight: 600, marginBottom: 4 }}>Processing — {STEP_LABELS[task.status] || task.status}</p>
              <p className="text-secondary text-sm">The AI pipeline is working on this step. If stuck, click Resume to retry.</p>
            </div>
            <ResumeButton taskId={task.id} />
          </div>
        </div>
      )}

      {/* Progress */}
      {task.status !== "done" && task.status !== "failed" && currentStepIdx >= 0 && (
        <div className="steps mb-6">
          {STEPS.filter(s => !s.includes("review")).map((s, i) => {
            const realIdx = STEPS.indexOf(s);
            const cls = realIdx < currentStepIdx ? "step done" : realIdx === currentStepIdx ? "step active" : "step";
            return <div key={s} className={cls}>{i + 1}. {STEP_LABELS[s]}</div>;
          })}
        </div>
      )}

      {/* Stuck — also show Resume for review states that need manual approval */}
      {["script_review", "image_review", "character_review"].includes(task.status) && (
        <div className="card mb-6" style={{ background: "rgba(251,191,36,0.08)", borderColor: "var(--warning)" }}>
          <p style={{ fontWeight: 600, marginBottom: 4 }}>Awaiting your review</p>
          <p className="text-secondary text-sm">Review and approve the content below to continue the pipeline.</p>
        </div>
      )}
        <div className="steps mb-6">
          {STEPS.filter(s => !s.includes("review")).map((s, i) => {
            const realIdx = STEPS.indexOf(s);
            const cls = realIdx < currentStepIdx ? "step done" : realIdx === currentStepIdx ? "step active" : "step";
            return <div key={s} className={cls}>{i + 1}. {STEP_LABELS[s]}</div>;
          })}
        </div>
      )}

      {task.error_message && (
        <div className="card mb-6" style={{ borderColor: "var(--danger)", background: "rgba(248,113,113,0.06)" }}>
          <p className="text-danger text-sm">{task.error_message}</p>
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
            <button className="btn btn-primary" onClick={approveScript} disabled={scriptLoading}>
              {scriptLoading ? "Approving..." : "Approve & Continue"}
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
                <img src={img.image_url} alt="" />
                <div className="image-status">{img.status.replace(/_/g, " ")}</div>
                <div className="image-actions">
                  {img.status !== "approved" && (
                    <button className="btn btn-primary btn-sm" style={{ flex: 1 }} onClick={() => reviewImage(img.id, "approve")}>Approve</button>
                  )}
                  <button className="btn btn-ghost btn-sm" style={{ flex: 1 }} onClick={() => reviewImage(img.id, "reject")}>Reject</button>
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
          <p className="text-secondary mb-6">Review the AI-generated character before generating the script.</p>
          <div className="flex gap-3">
            <button className="btn btn-primary" onClick={approveScript}>Approve Character</button>
          </div>
        </div>
      )}
    </div>
  );
}
