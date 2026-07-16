import api from "./client";

export type AttributeType = "text" | "number" | "single_select" | "multi_select" | "boolean";
export interface CategoryAttribute { id?: string; key: string; label: string; type: AttributeType; required: boolean; options: string[]; sort_order: number }
export interface Category { id: string; name: string; description: string | null; template_version: number; product_count?: number; attributes: CategoryAttribute[] }
export interface CategoryAttributeInput { key: string; label: string; type: AttributeType; required: boolean; options: string[]; sort_order: number }
export interface CategoryInput { name: string; description: string | null; attributes: CategoryAttributeInput[]; template_version?: number }
export interface Product { id: string; category_id: string; category?: Category; name: string; description: string | null; selling_points: string[]; scenarios: string[]; attributes: Record<string, unknown>; main_image_url: string; main_image_source: "upload" | "ai"; category_template_version: number; task_count?: number }
export interface InitializationStatus { status: "pending" | "completed" | "failed"; sample_version: number; attempts: number; error_message?: string | null }
export interface ProductListParams { name?: string; category_id?: string; page?: number; page_size?: number; sort?: "name" | "-name" | "created_at" | "-created_at" | "updated_at" | "-updated_at" }
export interface ProductDraft { category_id: string; category_template_version: number; name: string; description: string | null; selling_points: string[]; scenarios: string[]; attributes: Record<string, unknown>; main_image_url?: string; main_image_candidate_id?: string }
export interface MainImageCandidate { candidate_id: string; preview_url: string; expires_at: string }

export const catalogApi = {
  async listCategories(): Promise<Category[]> { const { data } = await api.get<Category[] | { items: Category[] }>("/categories"); return Array.isArray(data) ? data : data.items; },
  async createCategory(input: CategoryInput): Promise<Category> { return (await api.post<Category>("/categories", input)).data; },
  async updateCategory(id: string, input: CategoryInput): Promise<Category> { return (await api.put<Category>(`/categories/${id}`, input)).data; },
  async deleteCategory(id: string): Promise<void> { await api.delete(`/categories/${id}`); },
  async listProducts(params?: ProductListParams): Promise<{ items: Product[]; total: number }> { return (await api.get("/products", { params })).data; },
  async getProduct(id: string): Promise<Product> { return (await api.get<Product>(`/products/${id}`)).data; },
  async createProduct(input: ProductDraft): Promise<Product> { return (await api.post<Product>("/products", input)).data; },
  async updateProduct(id: string, input: ProductDraft): Promise<Product> { return (await api.put<Product>(`/products/${id}`, input)).data; },
  async deleteProduct(id: string): Promise<void> { await api.delete(`/products/${id}`); },
  async generateMainImage(input: ProductDraft): Promise<MainImageCandidate> { return (await api.post<MainImageCandidate>("/products/main-image/generate", input)).data; },
  async getInitializationStatus(): Promise<InitializationStatus> { return (await api.get<InitializationStatus>("/initialization-status")).data; },
};
