import { useEffect, useRef, useState } from "react";
import axios from "axios";
import { useTranslation } from "react-i18next";
import { catalogApi, type AttributeType, type Category, type CategoryAttribute, type CategoryInput } from "../api/catalog";

const types: AttributeType[] = ["text", "number", "single_select", "multi_select", "boolean"];
const blank = (): CategoryAttribute => ({ key: "", label: "", type: "text", required: false, options: [], sort_order: 0 });

export default function CategoriesPage() {
  const { t } = useTranslation();
  const [items, setItems] = useState<Category[]>([]);
  const [editing, setEditing] = useState<Category | null | undefined>();
  const [name, setName] = useState(""); const [description, setDescription] = useState("");
  const [attributes, setAttributes] = useState<CategoryAttribute[]>([]); const [error, setError] = useState("");
  const actionRef = useRef(new Set<string>());
  const load = () => { void catalogApi.listCategories().then(setItems).catch(() => setError(t("catalog.errors.load"))); };
  useEffect(() => { load(); }, []);
  const open = (category?: Category) => { setEditing(category ?? null); setName(category?.name ?? ""); setDescription(category?.description ?? ""); setAttributes(category?.attributes.map(a => ({ ...a, options: [...a.options] })) ?? []); };
  const updateRow = (index: number, patch: Partial<CategoryAttribute>) => setAttributes(rows => rows.map((row, i) => i === index ? { ...row, ...patch } : row));
  const move = (index: number, delta: number) => setAttributes(rows => { const next = [...rows]; const target = index + delta; if (target < 0 || target >= next.length) return rows; [next[index], next[target]] = [next[target], next[index]]; return next; });
  const message = (cause: unknown) => { if (axios.isAxiosError(cause)) { if (cause.response?.status === 409) return t("catalog.errors.conflict"); const detail = cause.response?.data?.detail; if (typeof detail === "string") return detail; if (detail && typeof detail === "object") return Object.values(detail).join(", "); } return t("catalog.errors.save"); };
  const save = async () => { if (actionRef.current.has("save")) return; actionRef.current.add("save"); const input: CategoryInput = { name, description: description || null, template_version: editing?.template_version, attributes: attributes.map(({ id: _id, ...a }, i) => ({ ...a, sort_order: i })) }; try { const saved = editing ? await catalogApi.updateCategory(editing.id, input) : await catalogApi.createCategory(input); setItems(old => editing ? old.map(x => x.id === saved.id ? saved : x) : [...old, saved]); setEditing(undefined); } catch (cause) { setError(message(cause)); } finally { actionRef.current.delete("save"); } };
  const remove = async (item: Category) => { const key = `delete:${item.id}`; if (actionRef.current.has(key)) return; actionRef.current.add(key); try { await catalogApi.deleteCategory(item.id); load(); } catch (cause) { setError(message(cause)); } finally { actionRef.current.delete(key); } };
  const attributeCount = items.reduce((total, item) => total + item.attributes.length, 0);
  return <section className="catalog-page">
    <header className="workspace-header"><div><span className="eyebrow">{t("catalog.title").toUpperCase()}</span><h1>{t("catalog.title")}</h1><p className="text-secondary">{t("catalog.subtitle")}</p></div><button className="btn btn-primary" onClick={() => open()}><span aria-hidden="true">＋</span> {t("catalog.new")}</button></header>
    <div className="catalog-summary"><div><strong>{items.length}</strong><span>{t("catalog.title")}</span></div><div><strong>{attributeCount}</strong><span>{t("catalog.attributes", { count: attributeCount })}</span></div><div className="summary-note">{t("catalog.summary")}</div></div>
    {error && <p role="alert" className="notice notice-error">{error}</p>}
    {items.length === 0 ? <div className="card empty-state"><div className="empty-icon">◇</div><h2>{t("catalog.emptyTitle")}</h2><p>{t("catalog.emptyDescription")}</p><button className="btn btn-primary" onClick={() => open()}>{t("catalog.new")}</button></div> :
      <div className="category-grid">{items.map(item => <article className="card category-card" key={item.id}>
        <div className="card-kicker">{t("catalog.templateVersion", { version: item.template_version })}</div><h2>{item.name}</h2><p className="card-description">{item.description || t("catalog.noDescription")}</p>
        <div className="chip-row">{item.attributes.slice(0, 4).map(attribute => <span className="chip" key={attribute.id ?? attribute.key}>{attribute.label || attribute.key}</span>)}{item.attributes.length > 4 && <span className="chip chip-muted">+{item.attributes.length - 4}</span>}</div>
        <div className="card-footer"><span className="metric">{t("catalog.products", { count: item.product_count ?? 0 })}</span><div className="card-actions"><button className="btn btn-ghost" onClick={() => open(item)}>{t("catalog.edit")}</button><button className="btn btn-danger-ghost" disabled={Boolean(item.product_count)} onClick={() => void remove(item)}>{t("catalog.delete")}</button></div></div>
      </article>)}</div>}
    {editing !== undefined && <div className="card category-editor"><div className="editor-heading"><div><span className="eyebrow">{t("catalog.builder")}</span><h2>{editing ? t("catalog.edit") : t("catalog.new")}</h2></div><button className="icon-button" onClick={() => setEditing(undefined)} aria-label={t("catalog.close")}>×</button></div>
      <div className="editor-fields"><label>{t("catalog.name")}<input value={name} onChange={e => setName(e.target.value)} /></label><label>{t("catalog.description")}<textarea value={description} onChange={e => setDescription(e.target.value)} /></label></div>
      <div className="attribute-heading"><div><h3>{t("catalog.attributes", { count: attributes.length })}</h3><p className="text-secondary">Define the fields that every product in this category shares.</p></div><button className="btn" onClick={() => setAttributes(rows => [...rows, { ...blank(), sort_order: rows.length }])}>＋ {t("catalog.addAttribute")}</button></div>
      {attributes.map((row, i) => <div className="attribute-row" key={i}><input aria-label={t("catalog.key")} placeholder={t("catalog.key")} value={row.key} onChange={e => updateRow(i, { key: e.target.value })}/><input aria-label={t("catalog.label")} placeholder={t("catalog.label")} value={row.label} onChange={e => updateRow(i, { label: e.target.value })}/><select aria-label={t("catalog.type")} value={row.type} onChange={e => updateRow(i, { type: e.target.value as AttributeType, options: [] })}>{types.map(type => <option key={type}>{type}</option>)}</select>{row.type.includes("select") && <input aria-label={t("catalog.options")} placeholder={t("catalog.options")} value={row.options.join(", ")} onChange={e => updateRow(i, { options: e.target.value.split(",").map(x => x.trim()).filter(Boolean) })}/>}<label className="check-label"><input type="checkbox" checked={row.required} onChange={e => updateRow(i, { required: e.target.checked })}/>{t("catalog.required")}</label><div className="row-actions"><button aria-label={t("catalog.up")} onClick={() => move(i, -1)}>↑</button><button aria-label={t("catalog.down")} onClick={() => move(i, 1)}>↓</button><button aria-label={t("catalog.remove")} onClick={() => setAttributes(rows => rows.filter((_, index) => index !== i))}>×</button></div></div>)}
      <div className="editor-actions"><button className="btn" onClick={() => setEditing(undefined)}>{t("catalog.cancel")}</button><button className="btn btn-primary" onClick={save}>{t("catalog.save")}</button></div>
    </div>}
  </section>;
}
