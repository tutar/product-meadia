import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { catalogApi, type Category, type MainImageCandidate, type ProductDraft } from "../api/catalog";

type CandidateState = "idle" | "generating" | "preview" | "confirmed" | "error";

export default function ProductFormPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [categories, setCategories] = useState<Category[]>([]);
  const [categoryId, setCategoryId] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [sellingPoints, setSellingPoints] = useState("");
  const [scenarios, setScenarios] = useState("");
  const [attributes, setAttributes] = useState<Record<string, unknown>>({});
  const [imageUrl, setImageUrl] = useState("");
  const [filePreview, setFilePreview] = useState("");
  const [candidate, setCandidate] = useState<MainImageCandidate | null>(null);
  const [candidateState, setCandidateState] = useState<CandidateState>("idle");

  useEffect(() => {
    void catalogApi.listCategories().then(setCategories);
    if (id) void catalogApi.getProduct(id).then(product => {
      setCategoryId(product.category_id); setName(product.name); setDescription(product.description ?? ""); setSellingPoints(product.selling_points.join(", ")); setScenarios(product.scenarios.join(", ")); setAttributes(product.attributes); setImageUrl(product.main_image_url);
    });
  }, [id]);

  const category = categories.find(item => item.id === categoryId);
  const setAttribute = (key: string, value: unknown) => setAttributes(current => ({ ...current, [key]: value }));
  const draft = (): ProductDraft => ({
    category_id: categoryId, category_template_version: category?.template_version ?? 1, name,
    description: description || null, selling_points: sellingPoints.split(",").map(x=>x.trim()).filter(Boolean), scenarios: scenarios.split(",").map(x=>x.trim()).filter(Boolean), attributes,
    ...(imageUrl ? { main_image_url: imageUrl } : candidateState === "confirmed" && candidate ? { main_image_candidate_id: candidate.candidate_id } : {}),
  });
  const generate = async () => { setCandidateState("generating"); try { setCandidate(await catalogApi.generateMainImage(draft())); setCandidateState("preview"); } catch { setCandidateState("error"); } };
  const save = async () => { const product = id ? await catalogApi.updateProduct(id, draft()) : await catalogApi.createProduct(draft()); navigate(`/products/${product.id}/edit`); };
  const requiredValid = category?.attributes.every(attribute => !attribute.required || (attribute.type === "boolean" ? typeof attributes[attribute.key] === "boolean" : Array.isArray(attributes[attribute.key]) ? (attributes[attribute.key] as unknown[]).length > 0 : attributes[attribute.key] !== undefined && attributes[attribute.key] !== "")) ?? false;

  return <section><h1>{id ? t("products.form.edit") : t("products.form.new")}</h1><div className="card category-editor">
    <label>{t("products.form.name")}<input aria-label={t("products.form.name")} value={name} onChange={event => setName(event.target.value)} /></label><label>{t("products.form.description")}<textarea value={description} onChange={e=>setDescription(e.target.value)}/></label><label>{t("products.form.sellingPoints")}<input value={sellingPoints} onChange={e=>setSellingPoints(e.target.value)}/></label><label>{t("products.form.scenarios")}<input value={scenarios} onChange={e=>setScenarios(e.target.value)}/></label>
    <label>{t("products.category")}<select aria-label={t("products.category")} value={categoryId} onChange={event => { if (Object.keys(attributes).length && !window.confirm(t("products.form.categoryChange"))) return; setCategoryId(event.target.value); setAttributes({}); }}><option value="">{t("products.form.chooseCategory")}</option>{categories.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
    {category?.attributes.map(attribute => <label key={attribute.key}>{attribute.label}{attribute.required && " *"}
      {attribute.type === "boolean" && <input type="checkbox" checked={Boolean(attributes[attribute.key])} onChange={event => setAttribute(attribute.key, event.target.checked)} />}
      {attribute.type === "single_select" && <select aria-label={attribute.label} required={attribute.required} value={String(attributes[attribute.key] ?? "")} onChange={event => setAttribute(attribute.key, event.target.value)}><option value="">Choose</option>{attribute.options.map(option => <option key={option} value={option}>{option}</option>)}</select>}
      {attribute.type === "multi_select" && <select aria-label={attribute.label} multiple required={attribute.required} value={Array.isArray(attributes[attribute.key]) ? attributes[attribute.key] as string[] : []} onChange={event => setAttribute(attribute.key, Array.from(event.target.selectedOptions, option => option.value))}>{attribute.options.map(option => <option key={option} value={option}>{option}</option>)}</select>}
      {attribute.type !== "boolean" && attribute.type !== "single_select" && attribute.type !== "multi_select" && <input aria-label={attribute.label} required={attribute.required} type={attribute.type === "number" ? "number" : "text"} value={String(attributes[attribute.key] ?? "")} onChange={event => setAttribute(attribute.key, attribute.type === "number" ? Number(event.target.value) : event.target.value)} />}
    </label>)}
    <label>{t("products.form.file")}<input type="file" accept="image/*" onChange={event=>{const file=event.target.files?.[0];if(file){setFilePreview(URL.createObjectURL(file));setCandidateState("idle")}}}/></label>{filePreview&&<img src={filePreview} alt={t("products.form.uploadPreview")} width="180"/>}<label>{t("products.form.imageUrl")}<input aria-label={t("products.form.imageUrl")} value={imageUrl} onChange={event => setImageUrl(event.target.value)} /></label>
    <button className="btn" onClick={() => void generate()} disabled={candidateState === "generating"}>{candidateState==="preview"||candidateState==="error"?t("products.form.regenerate"):t("products.form.generate")}</button>{candidateState==="error"&&<p role="alert">{t("products.form.aiError")}</p>}
    {candidateState === "preview" && candidate && <div><img src={candidate.preview_url} alt={t("products.form.aiPreview")} width="180" /><button onClick={() => setCandidateState("confirmed")}>{t("products.form.confirm")}</button></div>}
    <button className="btn btn-primary" disabled={!categoryId || !name || !requiredValid || (!imageUrl && candidateState !== "confirmed")} onClick={() => void save()}>{t("products.form.save")}</button>
  </div></section>;
}
