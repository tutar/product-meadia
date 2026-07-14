import { useState, useEffect, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import api from "../api/client";

export default function CreateTaskPage() {
  const [products, setProducts] = useState<any[]>([]);
  const [productId, setProductId] = useState("");
  const [type, setType] = useState("promo");
  const [imageCount, setImageCount] = useState(4);
  const [viralUrl, setViralUrl] = useState("");
  const navigate = useNavigate();

  useEffect(() => {
    api.get("/products").then((r) => setProducts(r.data.items)).catch(() => {});
  }, []);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const { data } = await api.post("/tasks", {
      product_id: productId,
      type,
      image_count: imageCount,
      viral_url: type === "viral" ? viralUrl : undefined,
    });
    navigate(`/tasks/${data.id}`);
  };

  return (
    <div style={{ maxWidth: 600, margin: "40px auto" }}>
      <h1>Create Video Task</h1>
      <form onSubmit={handleSubmit}>
        <div>
          <select value={productId} onChange={(e) => setProductId(e.target.value)} required>
            <option value="">Select product</option>
            {products.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </div>
        <div>
          <select value={type} onChange={(e) => setType(e.target.value)}>
            <option value="promo">Promotional Video</option>
            <option value="viral">Viral Remix</option>
            <option value="personify">Personification Video</option>
          </select>
        </div>
        {type === "promo" && (
          <div>
            <label>Image count: </label>
            <input type="number" value={imageCount} min={1} max={16} onChange={(e) => setImageCount(+e.target.value)} />
          </div>
        )}
        {type === "viral" && (
          <div>
            <input type="url" placeholder="Viral video URL" value={viralUrl} onChange={(e) => setViralUrl(e.target.value)} required />
          </div>
        )}
        <button type="submit">Create Task</button>
      </form>
    </div>
  );
}
