import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import api from "../api/client";
import { catalogApi, type Category, type Product } from "../api/catalog";
import MediaImage from "../components/MediaImage";
import { CreateTaskForm } from "./CreateTaskPage";
import TaskDetailPage from "./TaskDetailPage";

interface TaskItem {
  id: string;
  type: string;
  status: string;
  created_at: string;
  product_snapshot?: { name?: string; main_image_asset_id?: string; category?: { name?: string } };
}

const REVIEW_STATUSES = new Set(["script_review", "image_review", "character_review", "video_review", "composition_review"]);
const RUNNING_STATUSES = new Set(["pending", "scripting", "imaging", "video_gen", "compositing", "cancellation_requested"]);

function taskStatusClass(status: string) {
  if (status === "done" || status === "cancelled") return "is-done";
  if (status === "failed") return "is-failed";
  if (REVIEW_STATUSES.has(status)) return "is-review";
  return "is-running";
}

export default function TaskWorkspacePage() {
  const { t, i18n } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const [tasks, setTasks] = useState<TaskItem[]>([]);
  const [categories, setCategories] = useState<Category[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [loaded, setLoaded] = useState(false);
  const selectedId = searchParams.get("task");
  const categoryId = searchParams.get("category") || "";
  const productId = searchParams.get("product") || "";
  const mode = searchParams.get("mode");
  const locale = i18n.language === "zh" ? "zh-CN" : "en-US";

  const updateWorkspace = useCallback((changes: Record<string, string | null>, replace = false) => {
    const next = new URLSearchParams(searchParams);
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value);
      else next.delete(key);
    }
    setSearchParams(next, { replace });
  }, [searchParams, setSearchParams]);

  const loadTasks = useCallback(async () => {
    const response = await api.get("/tasks", { params: { page_size: 100, ...(categoryId ? { category_id: categoryId } : {}), ...(productId ? { product_id: productId } : {}) } }).catch(() => null);
    const nextTasks = response?.data.items ?? [];
    setTasks(nextTasks);
    setLoaded(true);
    if (!selectedId && nextTasks[0] && mode !== "create") updateWorkspace({ task: nextTasks[0].id }, true);
  }, [categoryId, mode, productId, selectedId, updateWorkspace]);

  useEffect(() => { void catalogApi.listCategories().then(setCategories); }, []);
  useEffect(() => { void catalogApi.listProducts({ ...(categoryId ? { category_id: categoryId } : {}), page_size: 100 }).then(result => setProducts(result.items)); }, [categoryId]);
  useEffect(() => { void loadTasks(); }, [loadTasks]);
  useEffect(() => {
    const timer = window.setInterval(() => void loadTasks(), 10000);
    return () => window.clearInterval(timer);
  }, [loadTasks]);

  const selectTask = (taskId: string) => updateWorkspace({ task: taskId, mode: null });
  const startCreate = () => updateWorkspace({ mode: "create" });
  const cancelCreate = () => updateWorkspace({ mode: null });
  const createdTask = async (taskId: string) => {
    updateWorkspace({ task: taskId, mode: null });
    await loadTasks();
  };
  const changeCategory = (value: string) => updateWorkspace({ category: value || null, product: null });
  const changeProduct = (value: string) => updateWorkspace({ product: value || null });
  const removeTask = async (taskId: string) => {
    if (!window.confirm(String(t("task.deleteConfirm")))) return;
    await api.delete(`/tasks/${taskId}`);
    if (selectedId === taskId) updateWorkspace({ task: null }, true);
    await loadTasks();
  };
  const attentionTasks = tasks.filter(task => REVIEW_STATUSES.has(task.status) || RUNNING_STATUSES.has(task.status));
  const recentTasks = tasks.filter(task => !attentionTasks.includes(task));
  const showCreate = mode === "create" || (loaded && tasks.length === 0 && !selectedId);

  const taskList = (items: TaskItem[]) => items.map(task => (
    <div key={task.id} className={`task-queue-item ${task.id === selectedId && !showCreate ? "is-selected" : ""} ${taskStatusClass(task.status)}`}>
      <button type="button" className="task-queue-select" onClick={() => selectTask(task.id)} aria-current={task.id === selectedId && !showCreate ? "true" : undefined}>
      {task.product_snapshot?.main_image_asset_id ? <MediaImage className="task-queue-image" assetId={task.product_snapshot.main_image_asset_id} alt="" /> : <span className="task-queue-placeholder" aria-hidden="true">{task.type.slice(0, 1)}</span>}
      <span className="task-queue-copy"><strong>{task.product_snapshot?.name ?? String(t(`types.${task.type}`, task.type))}</strong><small>{String(t(`steps.${task.status}`, task.status.replace(/_/g, " ")))}</small><time>{new Date(task.created_at).toLocaleDateString(locale, { month: "short", day: "numeric" })}</time></span>
      </button>
      {["done", "failed", "cancelled"].includes(task.status) && <button className="btn btn-danger-ghost btn-sm" onClick={() => void removeTask(task.id)}>{t("task.delete")}</button>}
    </div>
  ));

  return <section className="task-workspace" aria-label={t("nav.dashboard")}>
    <aside className="task-queue" aria-label={t("dashboard.title")}>
      <div className="task-queue-heading"><div><span className="eyebrow">{t("nav.dashboard")}</span><h1>{t("dashboard.title")}</h1><small>{tasks.length} {t("dashboard.title").toLowerCase()}</small></div><button className="btn btn-primary btn-sm" onClick={startCreate}>{t("dashboard.newVideo")}</button></div>
      <div className="task-queue-filters">
        <select aria-label={t("products.category")} value={categoryId} onChange={event => changeCategory(event.target.value)}><option value="">{t("products.allCategories")}</option>{categories.map(category => <option key={category.id} value={category.id}>{category.name}</option>)}</select>
        <select aria-label={t("task.product")} value={productId} onChange={event => changeProduct(event.target.value)}><option value="">{t("task.selectProduct")}</option>{products.map(product => <option key={product.id} value={product.id}>{product.name}</option>)}</select>
      </div>
      <div className="task-queue-list">
        {attentionTasks.length > 0 && <div className="task-queue-group"><h2>{t("workspace.attention")}</h2>{taskList(attentionTasks)}</div>}
        {recentTasks.length > 0 && <div className="task-queue-group"><h2>{t("workspace.recent")}</h2>{taskList(recentTasks)}</div>}
        {loaded && tasks.length === 0 && <div className="task-queue-empty"><p>{categoryId || productId ? t("workspace.noMatches") : t("dashboard.noVideos")}</p>{(categoryId || productId) && <button className="btn btn-ghost btn-sm" onClick={() => updateWorkspace({ category: null, product: null })}>{t("products.clearFilters")}</button>}</div>}
      </div>
    </aside>
    <main className="task-workspace-main">
      {showCreate ? <><header className="workspace-main-header"><div><span className="eyebrow">{t("dashboard.newVideo")}</span><h2>{t("task.newVideo")}</h2></div>{selectedId && <button className="btn btn-ghost btn-sm" onClick={cancelCreate}>{t("products.cancel")}</button>}</header><CreateTaskForm initialCategoryId={categoryId} initialProductId={productId} onCreated={createdTask} onCancel={selectedId ? cancelCreate : undefined} /></> : selectedId ? <TaskDetailPage key={selectedId} taskId={selectedId} /> : <div className="task-workspace-empty"><p>{t("task.loading")}</p></div>}
    </main>
  </section>;
}
