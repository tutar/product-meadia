import api from "./client";

export type AttributeType = "text" | "number" | "single_select" | "multi_select" | "boolean";
export interface CategoryAttribute { id?: string; key: string; label: string; type: AttributeType; required: boolean; options: string[]; sort_order: number }
export interface Category { id: string; name: string; description: string | null; template_version: number; product_count?: number; attributes: CategoryAttribute[] }
export interface CategoryAttributeInput { key: string; label: string; type: AttributeType; required: boolean; options: string[]; sort_order: number }
export interface CategoryInput { name: string; description: string | null; attributes: CategoryAttributeInput[]; template_version?: number }

export const catalogApi = {
  async listCategories(): Promise<Category[]> { const { data } = await api.get<Category[] | { items: Category[] }>("/categories"); return Array.isArray(data) ? data : data.items; },
  async createCategory(input: CategoryInput): Promise<Category> { return (await api.post<Category>("/categories", input)).data; },
  async updateCategory(id: string, input: CategoryInput): Promise<Category> { return (await api.put<Category>(`/categories/${id}`, input)).data; },
  async deleteCategory(id: string): Promise<void> { await api.delete(`/categories/${id}`); },
};
