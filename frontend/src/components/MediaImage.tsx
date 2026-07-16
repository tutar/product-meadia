import { useEffect, useState, type ImgHTMLAttributes } from "react";
import api from "../api/client";

export default function MediaImage({ assetId, ...props }: { assetId?: string | null } & ImgHTMLAttributes<HTMLImageElement>) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    if (!assetId) { setUrl(""); return; }
    void api.get(`/media/${assetId}/access`).then(response => setUrl(response.data.url));
  }, [assetId]);
  return url ? <img {...props} src={url} /> : null;
}
