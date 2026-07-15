import { useState, useEffect, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import api from "../api/client";

const TYPES = [
  { value: "promo", label: "Promotional Video", desc: "Cinematic product showcase with script, AI images, and voiceover." },
  { value: "viral", label: "Viral Remix", desc: "Analyze a trending video and remake it with your product." },
  { value: "personify", label: "Personification", desc: "Your product as a character, speaking directly to the audience." },
];

export default function CreateTaskPage() {
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
        product_id: productId,
        type,
        image_count: imageCount,
        viral_url: type === "viral" ? viralUrl : undefined,
      });
      navigate(`/tasks/${data.id}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <h1 className="mb-6">New Video</h1>

      <form onSubmit={handleSubmit}>
        <div className="card mb-6">
          <h3 className="mb-6">Product</h3>
          <div className="form-group">
            <label className="form-label">Select product</label>
            <select className="select" value={productId} onChange={e => setProductId(e.target.value)} required>
              <option value="">Choose a product...</option>
              {products.map((p: any) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
            {products.length === 0 && <p className="text-muted text-sm mt-3">No products yet. Create one via the API first.</p>}
          </div>
        </div>

        <div className="card mb-6">
          <h3 className="mb-6">Video Type</h3>
          <div className="flex flex-col gap-3">
            {TYPES.map(t => (
              <label
                key={t.value}
                className="card"
                style={{
                  cursor: "pointer",
                  borderColor: type === t.value ? "var(--accent)" : "var(--border)",
                  background: type === t.value ? "var(--accent-glow)" : "var(--surface)",
                  transition: "all 0.15s",
                }}
              >
                <input type="radio" name="type" value={t.value} checked={type === t.value} onChange={e => setType(e.target.value)} style={{ display: "none" }} />
                <strong>{t.label}</strong>
                <p className="text-secondary text-sm mt-3">{t.desc}</p>
              </label>
            ))}
          </div>

          {type === "promo" && (
            <div className="form-group mt-6">
              <label className="form-label">Number of AI images</label>
              <input className="input" type="number" value={imageCount} min={1} max={16} onChange={e => setImageCount(+e.target.value)} style={{ maxWidth: 120 }} />
            </div>
          )}

          {type === "viral" && (
            <div className="form-group mt-6">
              <label className="form-label">Trending video URL</label>
              <input className="input" type="url" placeholder="https://www.tiktok.com/@user/video/..." value={viralUrl} onChange={e => setViralUrl(e.target.value)} required />
            </div>
          )}
        </div>

        <button className="btn btn-primary btn-lg" type="submit" disabled={loading || !productId}>
          {loading ? "Creating..." : "Generate Video"}
        </button>
      </form>
    </div>
  );
}
