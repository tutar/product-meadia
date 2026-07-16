import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { catalogApi, type Category, type MainImageCandidate, type ProductDraft } from "../api/catalog";

type CandidateState = "idle" | "generating" | "preview" | "confirmed" | "error";

export default function ProductFormPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [categories, setCategories] = useState<Category[]>([]);
  const [categoryId, setCategoryId] = useState("");
  const [name, setName] = useState("");
  const [attributes, setAttributes] = useState<Record<string, unknown>>({});
  const [imageUrl, setImageUrl] = useState("");
  const [candidate, setCandidate] = useState<MainImageCandidate | null>(null);
  const [candidateState, setCandidateState] = useState<CandidateState>("idle");

  useEffect(() => {
    void catalogApi.listCategories().then(setCategories);
    if (id) void catalogApi.getProduct(id).then(product => {
      setCategoryId(product.category_id); setName(product.name); setAttributes(product.attributes); setImageUrl(product.main_image_url);
    });
  }, [id]);

  const category = categories.find(item => item.id === categoryId);
  const setAttribute = (key: string, value: unknown) => setAttributes(current => ({ ...current, [key]: value }));
  const draft = (): ProductDraft => ({
    category_id: categoryId, category_template_version: category?.template_version ?? 1, name,
    description: null, selling_points: [], scenarios: [], attributes,
    ...(imageUrl ? { main_image_url: imageUrl } : candidateState === "confirmed" && candidate ? { main_image_candidate_id: candidate.candidate_id } : {}),
  });
  const generate = async () => { setCandidateState("generating"); try { setCandidate(await catalogApi.generateMainImage(draft())); setCandidateState("preview"); } catch { setCandidateState("error"); } };
  const save = async () => { const product = id ? await catalogApi.updateProduct(id, draft()) : await catalogApi.createProduct(draft()); navigate(`/products/${product.id}/edit`); };

  return <section><h1>{id ? "Edit product" : "New product"}</h1><div className="card category-editor">
    <label>Name<input aria-label="Name" value={name} onChange={event => setName(event.target.value)} /></label>
    <label>Category<select aria-label="Category" value={categoryId} onChange={event => { if (Object.keys(attributes).length && !window.confirm("Changing category clears attributes")) return; setCategoryId(event.target.value); setAttributes({}); }}><option value="">Choose category</option>{categories.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
    {category?.attributes.map(attribute => <label key={attribute.key}>{attribute.label}{attribute.required && " *"}
      {attribute.type === "boolean" && <input type="checkbox" checked={Boolean(attributes[attribute.key])} onChange={event => setAttribute(attribute.key, event.target.checked)} />}
      {attribute.type === "single_select" && <select aria-label={attribute.label} required={attribute.required} value={String(attributes[attribute.key] ?? "")} onChange={event => setAttribute(attribute.key, event.target.value)}><option value="">Choose</option>{attribute.options.map(option => <option key={option} value={option}>{option}</option>)}</select>}
      {attribute.type === "multi_select" && <select aria-label={attribute.label} multiple required={attribute.required} value={Array.isArray(attributes[attribute.key]) ? attributes[attribute.key] as string[] : []} onChange={event => setAttribute(attribute.key, Array.from(event.target.selectedOptions, option => option.value))}>{attribute.options.map(option => <option key={option} value={option}>{option}</option>)}</select>}
      {attribute.type !== "boolean" && attribute.type !== "single_select" && attribute.type !== "multi_select" && <input aria-label={attribute.label} required={attribute.required} type={attribute.type === "number" ? "number" : "text"} value={String(attributes[attribute.key] ?? "")} onChange={event => setAttribute(attribute.key, attribute.type === "number" ? Number(event.target.value) : event.target.value)} />}
    </label>)}
    <label>Image URL<input aria-label="Image URL" value={imageUrl} onChange={event => setImageUrl(event.target.value)} /></label>
    <button className="btn" onClick={() => void generate()} disabled={candidateState === "generating"}>Generate AI image</button>
    {candidateState === "preview" && candidate && <div><img src={candidate.preview_url} alt="AI candidate" width="180" /><button onClick={() => setCandidateState("confirmed")}>Confirm image</button></div>}
    <button className="btn btn-primary" disabled={!categoryId || !name || (!imageUrl && candidateState !== "confirmed")} onClick={() => void save()}>Save</button>
  </div></section>;
}
