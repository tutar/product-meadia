import api from "./client";

export type ModelStage = "creative_planning" | "scriptwriting" | "keyframe_image" | "clip_video" | "voice_generation" | "viral_analysis";

export interface ProviderModelCatalogEntry {
  id: string; provider: string; model_id: string; display_name: string;
  capabilities: ModelStage[]; constraints: Record<string, unknown>;
  capability_revision: number; platform_default_available: boolean; is_available: boolean;
}
export interface ModelConfiguration {
  id: string; catalog_model_id: string | null; adapter: string; api_base: string | null; provider: string; model_id: string; display_name: string;
  capabilities: ModelStage[]; constraints: Record<string, unknown>; revision: number; uses_platform_default: boolean;
  verification_status: "unverified" | "verified" | "unavailable" | "revoked";
  verification_error: string | null; first_use_eligible?: boolean; verified_at: string | null; revoked_at: string | null;
  created_at: string; updated_at: string;
}
export interface StageModelDefault { stage: ModelStage; model_configuration_id: string }

export const modelConfigurationsApi = {
  listCatalog: async (capability?: ModelStage) => (await api.get<ProviderModelCatalogEntry[]>("/provider-model-catalog", { params: capability ? { capability } : undefined })).data,
  list: async () => (await api.get<ModelConfiguration[]>("/model-configurations")).data,
  create: async (input: { catalog_model_id?: string; display_name?: string; adapter?: string; api_base?: string; model_id?: string; capabilities?: ModelStage[]; constraints?: Record<string, unknown>; credential: string }) => (await api.post<ModelConfiguration>("/model-configurations", input)).data,
  update: async (id: string, input: { display_name?: string; adapter?: string; api_base?: string; model_id?: string; capabilities?: ModelStage[]; constraints?: Record<string, unknown>; credential?: string }) => (await api.patch<ModelConfiguration>(`/model-configurations/${id}`, input)).data,
  verify: async (id: string) => (await api.post<ModelConfiguration>(`/model-configurations/${id}/verify`)).data,
  revoke: async (id: string) => (await api.post<ModelConfiguration>(`/model-configurations/${id}/revoke`)).data,
  remove: async (id: string) => { await api.delete(`/model-configurations/${id}`); },
  listDefaults: async () => (await api.get<StageModelDefault[]>("/stage-model-defaults")).data,
  setDefault: async (stage: ModelStage, model_configuration_id: string) => (await api.put<StageModelDefault>(`/stage-model-defaults/${stage}`, { model_configuration_id })).data,
};
