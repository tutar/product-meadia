import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import api from "../api/client";
import { modelConfigurationsApi } from "../api/modelConfigurations";
import type { ModelConfiguration, ModelStage, ProviderModelCatalogEntry, StageModelDefault } from "../api/modelConfigurations";

const STAGES: Array<[ModelStage, string]> = [
  ["creative_planning", "Creative planning"], ["scriptwriting", "Scriptwriting"],
  ["keyframe_image", "Keyframe images"], ["clip_video", "Video clips"],
  ["voice_generation", "Voice generation"], ["viral_analysis", "Viral analysis / transcription"],
];

export default function PreferencesPage() {
  const { t } = useTranslation();
  const [script, setScript] = useState(false);
  const [images, setImages] = useState(false);
  const [saving, setSaving] = useState(false);
  const [catalog, setCatalog] = useState<ProviderModelCatalogEntry[]>([]);
  const [configurations, setConfigurations] = useState<ModelConfiguration[]>([]);
  const [defaults, setDefaults] = useState<StageModelDefault[]>([]);
  const [catalogModelId, setCatalogModelId] = useState("");
  const [credential, setCredential] = useState("");
  const [replacementCredentials, setReplacementCredentials] = useState<Record<string, string>>({});
  const [modelError, setModelError] = useState("");

  const loadModels = async () => {
    const [nextCatalog, nextConfigurations, nextDefaults] = await Promise.all([
      modelConfigurationsApi.listCatalog(), modelConfigurationsApi.list(), modelConfigurationsApi.listDefaults(),
    ]);
    setCatalog(nextCatalog); setConfigurations(nextConfigurations); setDefaults(nextDefaults);
    setCatalogModelId(current => current || nextCatalog[0]?.id || "");
  };

  useEffect(() => {
    api.get("/auth/preferences").then(({ data }) => {
      setScript(Boolean(data.auto_approve_script));
      setImages(Boolean(data.auto_approve_images));
    });
  }, []);
  useEffect(() => { void loadModels().catch(() => setModelError("Unable to load model configurations.")); }, []);

  const save = async () => {
    setSaving(true);
    try { await api.put("/auth/preferences", { auto_approve_script: script, auto_approve_images: images }); }
    finally { setSaving(false); }
  };

  const addConfiguration = async () => {
    setModelError("");
    try {
      await modelConfigurationsApi.create({ catalog_model_id: catalogModelId, credential });
      setCredential(""); await loadModels();
    } catch { setModelError("Unable to save the model configuration. The credential was not retained in this page."); }
  };
  const selectDefault = async (stage: ModelStage, id: string) => {
    setModelError("");
    try { await modelConfigurationsApi.setDefault(stage, id); await loadModels(); }
    catch { setModelError("Only verified, capability-compatible configurations can be selected."); }
  };
  const rotateCredential = async (id: string) => {
    const replacement = replacementCredentials[id];
    if (!replacement) return;
    setModelError("");
    try { await modelConfigurationsApi.update(id, { credential: replacement }); setReplacementCredentials(current => ({ ...current, [id]: "" })); await loadModels(); }
    catch { setModelError("Unable to rotate the credential."); }
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
    <section className="card mt-6" aria-labelledby="model-configurations-heading">
      <h2 id="model-configurations-heading">Model configurations</h2>
      <p className="text-secondary">Credentials are encrypted server-side and are never shown again.</p>
      {modelError && <p role="alert">{modelError}</p>}
      <div className="flex" style={{ gap: 8, flexWrap: "wrap" }}>
        <label>Catalog model<select aria-label="Catalog model" value={catalogModelId} onChange={event => setCatalogModelId(event.target.value)}>
          {catalog.map(model => <option key={model.id} value={model.id}>{model.provider} / {model.display_name}</option>)}
        </select></label>
        <label>BYOK<input aria-label="Provider credential" type="password" value={credential} onChange={event => setCredential(event.target.value)} autoComplete="off" /></label>
        <button className="btn btn-primary" type="button" disabled={!catalogModelId || !credential} onClick={() => void addConfiguration()}>Add configuration</button>
      </div>
      <ul aria-label="Model configurations">
        {configurations.map(configuration => <li key={configuration.id} className="flex items-center justify-between" style={{ gap: 8, marginTop: 12 }}>
          <span><strong>{configuration.provider} / {configuration.display_name}</strong> <small className="text-secondary">{configuration.verification_status}</small>{configuration.verification_error && <small role="status"> — {configuration.verification_error}</small>}</span>
          <span className="flex" style={{ gap: 8 }}>
            {configuration.verification_status === "unverified" && <button type="button" onClick={() => void modelConfigurationsApi.verify(configuration.id).then(loadModels).catch(() => setModelError("Verification failed."))}>Verify</button>}
            {configuration.verification_status !== "revoked" && <button type="button" onClick={() => void modelConfigurationsApi.revoke(configuration.id).then(loadModels).catch(() => setModelError("Unable to revoke configuration."))}>Revoke</button>}
            <button type="button" onClick={() => void modelConfigurationsApi.remove(configuration.id).then(loadModels).catch(() => setModelError("Referenced configurations cannot be deleted."))}>Delete</button>
          </span>
          {configuration.verification_status !== "revoked" && <span className="flex" style={{ gap: 8 }}>
            <input aria-label={`New credential for ${configuration.display_name}`} type="password" value={replacementCredentials[configuration.id] || ""} onChange={event => setReplacementCredentials(current => ({ ...current, [configuration.id]: event.target.value }))} autoComplete="off" />
            <button type="button" disabled={!replacementCredentials[configuration.id]} onClick={() => void rotateCredential(configuration.id)}>Rotate credential</button>
          </span>}
        </li>)}
      </ul>
      <h3>Stage defaults</h3>
      {STAGES.map(([stage, label]) => {
        const selected = defaults.find(item => item.stage === stage)?.model_configuration_id || "";
        const eligible = configurations.filter(item => item.verification_status === "verified" && item.capabilities.includes(stage));
        return <label key={stage} className="flex items-center justify-between" style={{ gap: 8, marginTop: 8 }}>{label}
          <select aria-label={`${label} default`} value={selected} onChange={event => void selectDefault(stage, event.target.value)}>
            <option value="">No default</option>{eligible.map(item => <option key={item.id} value={item.id}>{item.provider} / {item.display_name}</option>)}
          </select>
        </label>;
      })}
    </section>
  </section>;
}
