import { useEffect, useState, useRef } from "react";
import { useParams } from "react-router-dom";
import api from "../api/client";

export default function TaskDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [task, setTask] = useState<any>(null);
  const [script, setScript] = useState<any>(null);
  const [images, setImages] = useState<any[]>([]);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    api.get(`/tasks/${id}`).then((r) => setTask(r.data)).catch(() => {});
    api.get(`/tasks/${id}/script`).then((r) => setScript(r.data)).catch(() => {});
    api.get(`/tasks/${id}/images`).then((r) => setImages(r.data)).catch(() => {});

    const ws = new WebSocket(`ws://localhost:8000/ws/tasks/${id}`);
    ws.onmessage = (e) => {
      const progress = JSON.parse(e.data);
      if (progress.status === "done") {
        setTask((prev: any) => ({ ...prev, status: "done", result_video_url: progress.video_url }));
      }
    };
    wsRef.current = ws;
    return () => ws.close();
  }, [id]);

  const approveScript = async () => {
    await api.put(`/tasks/${id}/script`, { approved: true });
    setTask((prev: any) => ({ ...prev, status: "imaging" }));
  };

  const reviewImage = async (imageId: string, action: "approve" | "reject") => {
    await api.put(`/tasks/${id}/images/${imageId}`, { action });
    const { data } = await api.get(`/tasks/${id}/images`);
    setImages(data);
  };

  if (!task) return <div>Loading...</div>;

  return (
    <div style={{ maxWidth: 800, margin: "40px auto" }}>
      <h1>Task: {task.type}</h1>
      <p>Status: {task.status}</p>
      {task.result_video_url && (
        <video src={task.result_video_url} controls style={{ width: "100%" }} />
      )}

      {script && script.status === "pending_review" && (
        <div>
          <h2>Script Review</h2>
          <pre>{script.content}</pre>
          <textarea defaultValue={script.content} style={{ width: "100%", height: 200 }} />
          <button onClick={approveScript}>Approve Script</button>
        </div>
      )}

      {images.length > 0 && (
        <div>
          <h2>Image Review ({images.filter((i: any) => i.status === "approved").length}/{images.length} approved)</h2>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: 16 }}>
            {images.map((img: any) => (
              <div key={img.id} style={{ border: "1px solid #ccc", padding: 8 }}>
                <img src={img.image_url} style={{ width: "100%" }} alt="" />
                <p>Status: {img.status}</p>
                {img.status !== "approved" && (
                  <button onClick={() => reviewImage(img.id, "approve")}>Approve</button>
                )}
                <button onClick={() => reviewImage(img.id, "reject")}>Reject</button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
