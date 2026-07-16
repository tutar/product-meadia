import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import api from "../api/client";
import MediaImage from "../components/MediaImage";

interface TaskItem { id: string; type: string; status: string; created_at: string; product_snapshot?: { name?: string; main_image_asset_id?: string; category?: { name?: string } } }

function statusBadge(status: string) {
  const cls = status === "done" ? "badge-done" : status === "failed" ? "badge-failed" : status.includes("review") ? "badge-active" : "badge-pending";
  return <span className={`badge ${cls}`}>{status.replace(/_/g, " ")}</span>;
}

export default function DashboardPage() {
  const { t } = useTranslation();
  const [tasks, setTasks] = useState<TaskItem[]>([]);

  useEffect(() => {
    api.get("/tasks").then(r => setTasks(r.data.items)).catch(() => {});
  }, []);

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1>{t("dashboard.title")}</h1>
          <p className="text-secondary text-sm mt-3">{t("dashboard.subtitle")}</p>
        </div>
        <Link to="/tasks/new" className="btn btn-primary">{t("dashboard.newVideo")}</Link>
      </div>

      {tasks.length === 0 ? (
        <div className="empty-state card">
          <h2>{t("dashboard.noVideos")}</h2>
          <p>{t("dashboard.noVideosDesc")}</p>
          <Link to="/tasks/new" className="btn btn-primary">{t("dashboard.createFirst")}</Link>
        </div>
      ) : (
        <div className="table-wrap card" style={{ padding: 0 }}>
          <table>
            <thead>
              <tr><th>{t("dashboard.type")}</th><th>{t("dashboard.status")}</th><th>{t("dashboard.created")}</th><th></th></tr>
            </thead>
            <tbody>
              {tasks.map(task => (
                <tr key={task.id}>
                  <td><div className="flex items-center gap-2">{task.product_snapshot?.main_image_asset_id && <MediaImage assetId={task.product_snapshot.main_image_asset_id} alt="" width="40" height="40" />}<span><strong>{task.product_snapshot?.name ?? String(t(`types.${task.type}`, task.type))}</strong>{task.product_snapshot?.category?.name && <small> · {task.product_snapshot.category.name}</small>}</span></div></td>
                  <td>{statusBadge(task.status)}</td>
                  <td className="text-secondary text-sm">{new Date(task.created_at).toLocaleDateString(t("auth.signInButton") === "登录" ? "zh-CN" : "en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</td>
                  <td><Link to={`/tasks/${task.id}`} className="btn btn-ghost btn-sm">{t("dashboard.view")}</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
