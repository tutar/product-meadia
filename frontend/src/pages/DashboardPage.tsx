import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "../api/client";

const TYPE_LABELS: Record<string, string> = { promo: "Promo", viral: "Viral Remix", personify: "Personify" };

function statusBadge(status: string) {
  const cls = status === "done" ? "badge-done" : status === "failed" ? "badge-failed" : status.includes("review") ? "badge-active" : "badge-pending";
  return <span className={`badge ${cls}`}>{status.replace(/_/g, " ")}</span>;
}

export default function DashboardPage() {
  const [tasks, setTasks] = useState<any[]>([]);

  useEffect(() => {
    api.get("/tasks").then(r => setTasks(r.data.items)).catch(() => {});
  }, []);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1>Videos</h1>
          <p className="text-secondary text-sm mt-3">Your AI-generated short video projects</p>
        </div>
        <Link to="/tasks/new" className="btn btn-primary">New Video</Link>
      </div>

      {tasks.length === 0 ? (
        <div className="empty-state card">
          <h2>No videos yet</h2>
          <p>Create your first AI-powered short video from product information.</p>
          <Link to="/tasks/new" className="btn btn-primary">Create your first video</Link>
        </div>
      ) : (
        <div className="table-wrap card" style={{ padding: 0 }}>
          <table>
            <thead>
              <tr><th>Type</th><th>Status</th><th>Created</th><th></th></tr>
            </thead>
            <tbody>
              {tasks.map((t: any) => (
                <tr key={t.id}>
                  <td><strong>{TYPE_LABELS[t.type] || t.type}</strong></td>
                  <td>{statusBadge(t.status)}</td>
                  <td className="text-secondary text-sm">{new Date(t.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</td>
                  <td><Link to={`/tasks/${t.id}`} className="btn btn-ghost btn-sm">View</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
