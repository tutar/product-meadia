import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import api from "../api/client";

export default function PreferencesPage() {
  const { t } = useTranslation();
  const [script, setScript] = useState(false);
  const [images, setImages] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.get("/auth/preferences").then(({ data }) => {
      setScript(Boolean(data.auto_approve_script));
      setImages(Boolean(data.auto_approve_images));
    });
  }, []);

  const save = async () => {
    setSaving(true);
    try { await api.put("/auth/preferences", { auto_approve_script: script, auto_approve_images: images }); }
    finally { setSaving(false); }
  };

  return <section style={{ maxWidth: 640 }}>
    <h1>{t("preferences.title")}</h1>
    <p className="text-secondary">{t("preferences.description")}</p>
    <div className="card mt-6">
      <label className="flex items-center justify-between" style={{ gap: 16 }}>
        <span><strong>{t("preferences.script")}</strong><small className="text-secondary" style={{ display: "block", marginTop: 4 }}>{t("preferences.scriptHelp")}</small></span>
        <input type="checkbox" checked={script} onChange={event => setScript(event.target.checked)} />
      </label>
      <div className="profile-menu-divider" />
      <label className="flex items-center justify-between" style={{ gap: 16 }}>
        <span><strong>{t("preferences.images")}</strong><small className="text-secondary" style={{ display: "block", marginTop: 4 }}>{t("preferences.imagesHelp")}</small></span>
        <input type="checkbox" checked={images} onChange={event => setImages(event.target.checked)} />
      </label>
      <div className="mt-6"><button className="btn btn-primary" disabled={saving} onClick={() => void save()}>{saving ? t("preferences.saving") : t("preferences.save")}</button></div>
    </div>
  </section>;
}
