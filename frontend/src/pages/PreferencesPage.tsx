import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import api from "../api/client";
import { modelConfigurationsApi } from "../api/modelConfigurations";
import type { ModelConfiguration, ModelStage, ProviderModelCatalogEntry, StageModelDefault } from "../api/modelConfigurations";

const STAGES: Array<[ModelStage, string]> = [
  ["creative_planning", "creative_planning"], ["scriptwriting", "scriptwriting"],
  ["keyframe_image", "keyframe_image"], ["clip_video", "clip_video"],
  ["voice_generation", "voice_generation"], ["viral_analysis", "viral_analysis"],
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
  const [customModel, setCustomModel] = useState(false);
  const [customName, setCustomName] = useState("");
  const [customApiBase, setCustomApiBase] = useState("");
  const [customModelId, setCustomModelId] = useState("");
  const [customCapabilities, setCustomCapabilities] = useState<ModelStage[]>([]);
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
      const optionalCredential = credential || undefined;
      await modelConfigurationsApi.create(customModel ? { display_name: customName, adapter: "openai_compatible", api_base: customApiBase, model_id: customModelId, capabilities: customCapabilities, credential: optionalCredential } : { catalog_model_id: catalogModelId, credential: optionalCredential });
      setCredential(""); await loadModels();
    } catch { setModelError("Unable to save the model configuration. The credential was not retained in this page."); }
  };
  const toggleCustomCapability = (stage: ModelStage) => setCustomCapabilities(current => current.includes(stage) ? current.filter(item => item !== stage) : [...current, stage]);
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

  return <section className="preferences-page">
    <header className="preferences-header">
      <p className="preferences-eyebrow">{t("modelConfigurations.eyebrow")}</p>
      <h1>{t("preferences.title")}</h1>
      <p className="text-secondary">{t("preferences.description")}</p>
    </header>

    <section className="card preferences-review-panel" aria-labelledby="review-preferences-heading">
      <div className="preferences-section-heading">
        <div><p className="preferences-kicker">{t("preferences.sectionLabel")}</p><h2 id="review-preferences-heading">{t("preferences.reviewTitle")}</h2></div>
        <p>{t("preferences.reviewDescription")}</p>
      </div>
      <div className="preferences-toggle-list">
        <label className="preferences-toggle">
          <span><strong>{t("preferences.script")}</strong><small>{t("preferences.scriptHelp")}</small></span>
          <input type="checkbox" checked={script} onChange={event => setScript(event.target.checked)} />
        </label>
        <label className="preferences-toggle">
          <span><strong>{t("preferences.images")}</strong><small>{t("preferences.imagesHelp")}</small></span>
          <input type="checkbox" checked={images} onChange={event => setImages(event.target.checked)} />
        </label>
      </div>
      <div className="preferences-actions"><button className="btn btn-primary" disabled={saving} onClick={() => void save()}>{saving ? t("preferences.saving") : t("preferences.save")}</button></div>
    </section>

    <section className="card model-console" aria-labelledby="model-configurations-heading">
      <div className="preferences-section-heading">
        <div><p className="preferences-kicker">{t("modelConfigurations.sectionLabel")}</p><h2 id="model-configurations-heading">{t("modelConfigurations.title")}</h2></div>
        <p>{t("modelConfigurations.description")}</p>
      </div>
      {modelError && <p className="notice notice-error" role="alert">{modelError}</p>}

      <div className="model-connection-panel">
        <div><h3>{t("modelConfigurations.addTitle")}</h3><p>{t("modelConfigurations.addDescription")}</p></div>
        <div className="model-connection-fields">
          <button className="btn btn-secondary btn-sm model-mode-toggle" type="button" onClick={() => setCustomModel(current => !current)}>{customModel ? t("modelConfigurations.useTemplate") : t("modelConfigurations.usePrivate")}</button>
          {customModel ? <>
            <label className="model-field"><span>{t("modelConfigurations.privateName")}</span><input className="input" aria-label={t("modelConfigurations.privateName")} value={customName} onChange={event => setCustomName(event.target.value)} /></label>
            <label className="model-field"><span>{t("modelConfigurations.privateEndpoint")}</span><input className="input" aria-label={t("modelConfigurations.privateEndpoint")} value={customApiBase} onChange={event => setCustomApiBase(event.target.value)} /></label>
            <label className="model-field"><span>{t("modelConfigurations.privateModelId")}</span><input className="input" aria-label={t("modelConfigurations.privateModelId")} value={customModelId} onChange={event => setCustomModelId(event.target.value)} /></label>
            <fieldset className="model-capabilities"><legend>{t("modelConfigurations.capabilities")}</legend>{STAGES.map(([stage, label]) => <label key={stage}><input type="checkbox" checked={customCapabilities.includes(stage)} onChange={() => toggleCustomCapability(stage)} />{t(`modelConfigurations.stages.${label}`)}</label>)}</fieldset>
          </> : <label className="model-field"><span>{t("modelConfigurations.catalogModel")}</span><select className="select" aria-label={t("modelConfigurations.catalogModel")} value={catalogModelId} onChange={event => setCatalogModelId(event.target.value)}>
            {catalog.map(model => <option key={model.id} value={model.id}>{model.provider} / {model.display_name}</option>)}
          </select></label>}
          <label className="model-field"><span>{t("modelConfigurations.credential")} <small>{t("modelConfigurations.optional")}</small></span><input className="input" aria-label={t("modelConfigurations.credential")} type="password" value={credential} onChange={event => setCredential(event.target.value)} autoComplete="off" /></label>
          <button className="btn btn-primary" type="button" disabled={customModel ? !customName || !customApiBase || !customModelId || !customCapabilities.length : !catalogModelId} onClick={() => void addConfiguration()}>{t("modelConfigurations.add")}</button>
        </div>
      </div>

      <div className="model-list-heading"><div><h3>{t("modelConfigurations.configuredTitle")}</h3><p>{t("modelConfigurations.configuredDescription")}</p></div></div>
      {configurations.length === 0 ? <p className="model-empty">{t("modelConfigurations.empty")}</p> : <ul className="model-configuration-list" aria-label={t("modelConfigurations.title")}>
        {configurations.map(configuration => <li key={configuration.id} className="model-configuration-row">
          <div className="model-configuration-identity"><strong>{configuration.provider} / {configuration.display_name}</strong><span className={`model-status status-${configuration.verification_status}`}>{t(`modelConfigurations.status.${configuration.verification_status}`)}</span>{configuration.verification_error && <small role="status">{configuration.verification_error}</small>}</div>
          <div className="model-configuration-actions">
            {configuration.verification_status === "unverified" && <button className="btn btn-secondary btn-sm" type="button" onClick={() => void modelConfigurationsApi.verify(configuration.id).then(loadModels).catch(() => setModelError(t("modelConfigurations.errors.verify")))}>{t("modelConfigurations.verify")}</button>}
            {configuration.verification_status !== "revoked" && <button className="btn btn-ghost btn-sm" type="button" onClick={() => void modelConfigurationsApi.revoke(configuration.id).then(loadModels).catch(() => setModelError(t("modelConfigurations.errors.revoke")))}>{t("modelConfigurations.revoke")}</button>}
            <button className="btn btn-ghost btn-sm" type="button" onClick={() => void modelConfigurationsApi.remove(configuration.id).then(loadModels).catch(() => setModelError(t("modelConfigurations.errors.delete")))}>{t("modelConfigurations.delete")}</button>
          </div>
          {configuration.verification_status !== "revoked" && <div className="model-credential-rotation">
            <label className="model-field"><span>{t("modelConfigurations.newCredential")}</span><input className="input" aria-label={t("modelConfigurations.newCredentialFor", { model: configuration.display_name })} type="password" value={replacementCredentials[configuration.id] || ""} onChange={event => setReplacementCredentials(current => ({ ...current, [configuration.id]: event.target.value }))} autoComplete="off" /></label>
            <button className="btn btn-secondary btn-sm" type="button" disabled={!replacementCredentials[configuration.id]} onClick={() => void rotateCredential(configuration.id)}>{t("modelConfigurations.rotate")}</button>
          </div>}
        </li>)}
      </ul>}

      <div className="model-defaults-header"><div><p className="preferences-kicker">{t("modelConfigurations.defaultsLabel")}</p><h3>{t("modelConfigurations.defaultsTitle")}</h3></div><p>{t("modelConfigurations.defaultsDescription")}</p></div>
      <div className="model-defaults-grid">
        {STAGES.map(([stage, label]) => {
          const selected = defaults.find(item => item.stage === stage)?.model_configuration_id || "";
          const eligible = configurations.filter(item => (item.verification_status === "verified" || item.first_use_eligible) && item.capabilities.includes(stage));
          const stageLabel = t(`modelConfigurations.stages.${label}`);
          return <label key={stage} className="model-default-card"><span>{stageLabel}</span>
            <select className="select" aria-label={t("modelConfigurations.defaultFor", { stage: stageLabel })} value={selected} onChange={event => void selectDefault(stage, event.target.value)}>
              <option value="">{t("modelConfigurations.noDefault")}</option>{eligible.map(item => <option key={item.id} value={item.id}>{item.provider} / {item.display_name}</option>)}
            </select>
            <small>{eligible.length ? t("modelConfigurations.eligibleCount", { count: eligible.length }) : t("modelConfigurations.noEligible")}</small>
          </label>;
        })}
      </div>
    </section>
  </section>;
}
