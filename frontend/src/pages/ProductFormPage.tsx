import { useEffect, useRef, useState } from "react";
import axios from "axios";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { catalogApi, type Category, type MainImageCandidate, type PackagingImageCandidate, type ProductDraft } from "../api/catalog";
import MediaImage from "../components/MediaImage";

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
  const [imageAssetId, setImageAssetId] = useState("");
  const [packagingAssetIds, setPackagingAssetIds] = useState<string[]>([]);
  const [packagingPrompt, setPackagingPrompt] = useState("");
  const [packagingCandidate, setPackagingCandidate] = useState<PackagingImageCandidate | null>(null);
  const [filePreview, setFilePreview] = useState("");
  const [candidate, setCandidate] = useState<MainImageCandidate | null>(null);
  const [candidateState, setCandidateState] = useState<CandidateState>("idle");
  const [saveError, setSaveError] = useState(""); const [saving, setSaving] = useState(false);
  const saveRef = useRef(false); const generateRef = useRef(false);

  useEffect(() => {
    void catalogApi.listCategories().then(setCategories);
    if (id) void catalogApi.getProduct(id).then(product => {
      setCategoryId(product.category_id); setName(product.name); setDescription(product.description ?? ""); setSellingPoints(product.selling_points.join(", ")); setScenarios(product.scenarios.join(", ")); setAttributes(product.attributes); setImageAssetId(product.main_image_asset_id ?? ""); setPackagingAssetIds((product.packaging_images ?? []).sort((a,b)=>a.sort_order-b.sort_order).map(image=>image.asset_id));
    });
  }, [id]);

  const category = categories.find(item => item.id === categoryId);
  const setAttribute = (key: string, value: unknown) => setAttributes(current => ({ ...current, [key]: value }));
  const draft = (): ProductDraft => ({
    category_id: categoryId, category_template_version: category?.template_version ?? 1, name,
    description: description || null, selling_points: sellingPoints.split(",").map(x=>x.trim()).filter(Boolean), scenarios: scenarios.split(",").map(x=>x.trim()).filter(Boolean), attributes,
    ...(candidateState === "confirmed" && candidate ? { main_image_candidate_id: candidate.candidate_id } : imageAssetId ? { main_image_asset_id: imageAssetId } : {}), packaging_image_asset_ids: packagingAssetIds,
  });
  const generate = async () => { if (generateRef.current) return; generateRef.current = true; setCandidateState("generating"); try { setCandidate(await catalogApi.generateMainImage(draft())); setCandidateState("preview"); } catch { setCandidateState("error"); } finally { generateRef.current = false; } };
  const generatePackaging = async () => { if (!imageAssetId || packagingAssetIds.length >= 6) return; setPackagingCandidate(await catalogApi.generatePackagingImage({ ...draft(), main_image_asset_id: imageAssetId, prompt: packagingPrompt || undefined })); };
  const save = async () => {
    if (saveRef.current) return;
    if (!categoryId || !name || !requiredValid || (!imageAssetId && candidateState !== "confirmed")) {
      setSaveError(t("products.form.validationError")); return;
    }
    saveRef.current = true; setSaveError(""); setSaving(true);
    try {
      if (id) await catalogApi.updateProduct(id, draft());
      else await catalogApi.createProduct(draft());
      navigate("/products");
    } catch (cause) {
      if (axios.isAxiosError(cause)) {
        const detail = cause.response?.data?.detail;
        setSaveError(typeof detail === "string" ? detail : t("products.form.saveError"));
      } else setSaveError(t("products.form.saveError"));
    } finally { saveRef.current = false; setSaving(false); }
  };
  const requiredValid = category?.attributes.every(attribute => !attribute.required || (attribute.type === "boolean" ? typeof attributes[attribute.key] === "boolean" : Array.isArray(attributes[attribute.key]) ? (attributes[attribute.key] as unknown[]).length > 0 : attributes[attribute.key] !== undefined && attributes[attribute.key] !== "")) ?? false;

  return <section className="catalog-page product-form-page"><header className="workspace-header"><div><span className="eyebrow">{t("products.title").toUpperCase()}</span><h1>{id ? t("products.form.edit") : t("products.form.new")}</h1><p className="text-secondary">{t("products.formIntro")}</p></div><button className="btn" onClick={() => navigate("/products")}>← {t("products.title")}</button></header><div className="product-form-layout"><div className="card category-editor">
    <div className="form-section"><div className="section-heading"><span className="step-number">01</span><div><h2>{t("products.identity")}</h2><p className="text-secondary">{t("products.identityHelp")}</p></div></div><div className="form-grid"><label>{t("products.form.name")}<input aria-label={t("products.form.name")} value={name} onChange={event => setName(event.target.value)} /></label><label>{t("products.category")}<select aria-label={t("products.category")} value={categoryId} onChange={event => { if (Object.keys(attributes).length && !window.confirm(t("products.form.categoryChange"))) return; setCategoryId(event.target.value); setAttributes({}); }}><option value="">{t("products.form.chooseCategory")}</option>{categories.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label></div><label>{t("products.form.description")}<textarea value={description} onChange={e=>setDescription(e.target.value)}/></label></div>
    <div className="form-section"><div className="section-heading"><span className="step-number">02</span><div><h2>{t("products.positioning")}</h2><p className="text-secondary">{t("products.positioningHelp")}</p></div></div><div className="form-grid"><label>{t("products.form.sellingPoints")}<input value={sellingPoints} onChange={e=>setSellingPoints(e.target.value)}/></label><label>{t("products.form.scenarios")}<input value={scenarios} onChange={e=>setScenarios(e.target.value)}/></label></div></div>

    {category?.attributes.map(attribute => <label key={attribute.key}>{attribute.label}{attribute.required && " *"}
      {attribute.type === "boolean" && <input type="checkbox" checked={Boolean(attributes[attribute.key])} onChange={event => setAttribute(attribute.key, event.target.checked)} />}
      {attribute.type === "single_select" && <select aria-label={attribute.label} required={attribute.required} value={String(attributes[attribute.key] ?? "")} onChange={event => setAttribute(attribute.key, event.target.value)}><option value="">{t("products.choose")}</option>{attribute.options.map(option => <option key={option} value={option}>{option}</option>)}</select>}
      {attribute.type === "multi_select" && <select aria-label={attribute.label} multiple required={attribute.required} value={Array.isArray(attributes[attribute.key]) ? attributes[attribute.key] as string[] : []} onChange={event => setAttribute(attribute.key, Array.from(event.target.selectedOptions, option => option.value))}>{attribute.options.map(option => <option key={option} value={option}>{option}</option>)}</select>}
      {attribute.type !== "boolean" && attribute.type !== "single_select" && attribute.type !== "multi_select" && <input aria-label={attribute.label} required={attribute.required} type={attribute.type === "number" ? "number" : "text"} value={String(attributes[attribute.key] ?? "")} onChange={event => setAttribute(attribute.key, attribute.type === "number" ? Number(event.target.value) : event.target.value)} />}
    </label>)}
    <div className="form-section media-section"><div className="section-heading"><span className="step-number">03</span><div><h2>商品主图</h2><p className="text-secondary">请使用单个产品、干净白底的图片。</p></div></div><label>{t("products.form.file")}<input type="file" accept="image/*" onChange={event=>{const file=event.target.files?.[0];if(file){setFilePreview(URL.createObjectURL(file));setCandidateState("idle");void catalogApi.uploadMainImage(file).then(result=>setImageAssetId(result.asset_id))}}}/></label>{filePreview&&<img className="image-preview" src={filePreview} alt={t("products.form.uploadPreview")} />}{imageAssetId && <MediaImage className="image-preview" assetId={imageAssetId} alt={t("products.form.currentImage")} />}<button className="btn" onClick={() => void generate()} disabled={candidateState === "generating"}>{candidateState==="preview"||candidateState==="error"?t("products.form.regenerate"):t("products.form.generate")}</button>{candidateState === "preview" && candidate && <div className="candidate-preview"><img src={candidate.preview_url} alt={t("products.form.aiPreview")} /><button className="btn" onClick={() => setCandidateState("confirmed")}>{t("products.form.confirm")}</button></div>}</div>
    <div className="form-section media-section"><h2>包装图（可选，最多 6 张）</h2><p className="text-secondary">使用白底或中性背景；可上传或以主图为参考生成。</p><input placeholder="视角/要求，例如正面或开盒" value={packagingPrompt} onChange={e=>setPackagingPrompt(e.target.value)} /><label>{t("products.form.file")}<input type="file" accept="image/*" disabled={packagingAssetIds.length >= 6} onChange={event=>{const file=event.target.files?.[0];if(file) void catalogApi.uploadMainImage(file).then(result=>setPackagingAssetIds(ids=>[...ids,result.asset_id]))}}/></label><button className="btn" disabled={!imageAssetId || packagingAssetIds.length >= 6} onClick={()=>void generatePackaging()}>生成包装图</button>{packagingCandidate && <div className="candidate-preview"><img src={packagingCandidate.preview_url} alt="包装图候选"/><button className="btn" onClick={()=>{setPackagingAssetIds(ids=>[...ids, packagingCandidate.asset_id]);setPackagingCandidate(null)}}>确认添加</button></div>}<div className="chip-row">{packagingAssetIds.map((assetId,index)=><span className="chip" key={assetId}>包装图 {index+1}<button type="button" onClick={()=>setPackagingAssetIds(ids=>ids.filter(id=>id!==assetId))}>×</button></span>)}</div></div>
    {saveError && <p role="alert" className="notice notice-error">{saveError}</p>}<div className="editor-actions"><button className="btn" onClick={() => navigate("/products")} disabled={saving}>{t("products.cancel")}</button><button className="btn btn-primary" disabled={saving} onClick={() => void save()}>{saving ? `${t("products.form.save")}…` : t("products.form.save")}</button></div>
  </div><aside className="form-aside card"><span className="eyebrow">{t("products.readyCheck")}</span><h2>{t("products.beforeSave")}</h2><p className="text-secondary">{t("products.beforeSaveHelp")}</p><div className="check-list"><span className={name ? "complete" : ""}>○ {t("products.requiredName")}</span><span className={categoryId ? "complete" : ""}>○ {t("products.requiredCategory")}</span><span className={requiredValid ? "complete" : ""}>○ {t("products.requiredAttributes")}</span><span className={imageAssetId || candidateState === "confirmed" ? "complete" : ""}>○ {t("products.requiredImage")}</span></div></aside></div></section>;
}
