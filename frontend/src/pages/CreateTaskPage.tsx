import { useState, useEffect, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import api from "../api/client";

export default function CreateTaskPage() {
  const { t } = useTranslation();
  const [products, setProducts] = useState<any[]>([]);
  const [productId, setProductId] = useState("");
  const [type, setType] = useState("promo");
  const [imageCount, setImageCount] = useState(4);
  const [viralUrl, setViralUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    api.get("/products").then(r => setProducts(r.data.items)).catch(() => {});
  }, []);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const { data } = await api.post("/tasks", {
        product_id: productId, type,
        image_count: imageCount,
        viral_url: type === "viral" ? viralUrl : undefined,
      });
      navigate(`/tasks/${data.id}`);
    } finally { setLoading(false); }
  };

  const types = [
    { value: "promo", label: t("task.promo"), desc: t("task.promoDesc") },
    { value: "viral", label: t("task.viral"), desc: t("task.viralDesc") },
    { value: "personify", label: t("task.personify"), desc: t("task.personifyDesc") },
  ];

  return (
    <div>
      <h1 className="mb-6">{t("task.newVideo")}</h1>
      <form onSubmit={handleSubmit}>
        <div className="card mb-6">
          <h3 className="mb-6">{t("task.product")}</h3>
          <div className="form-group">
            <label className="form-label">{t("task.selectProduct")}</label>
            <select className="select" value={productId} onChange={e => setProductId(e.target.value)} required>
              <option value="">{t("task.selectProduct")}</option>
              {products.map((p: any) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
            {products.length === 0 && <p className="text-muted text-sm mt-3">{t("task.noProducts")}</p>}
          </div>
        </div>

        <div className="card mb-6">
          <h3 className="mb-6">{t("task.videoType")}</h3>
          <div className="flex flex-col gap-3">
            {types.map(tp => (
              <label key={tp.value} className="card" style={{ cursor: "pointer", borderColor: type === tp.value ? "var(--accent)" : "var(--border)", background: type === tp.value ? "var(--accent-glow)" : "var(--surface)" }}>
                <input type="radio" name="type" value={tp.value} checked={type === tp.value} onChange={e => setType(e.target.value)} style={{ display: "none" }} />
                <strong>{tp.label}</strong>
                <p className="text-secondary text-sm mt-3">{tp.desc}</p>
              </label>
            ))}
          </div>

          {type === "promo" && (
            <div className="form-group mt-6">
              <label className="form-label">{t("task.imageCount")}</label>
              <input className="input" type="number" value={imageCount} min={1} max={16} onChange={e => setImageCount(+e.target.value)} style={{ maxWidth: 120 }} />
            </div>
          )}

          {type === "viral" && (
            <div className="form-group mt-6">
              <label className="form-label">{t("task.viralUrl")}</label>
              <input className="input" type="url" placeholder={t("task.viralUrlPlaceholder")} value={viralUrl} onChange={e => setViralUrl(e.target.value)} required />
            </div>
          )}
        </div>

        <button className="btn btn-primary btn-lg" type="submit" disabled={loading || !productId}>
          {loading ? t("task.creating") : t("task.generate")}
        </button>
      </form>
    </div>
  );
}
