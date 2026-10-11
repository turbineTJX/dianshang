export interface User { id: string; email: string; name: string; role: string; balance: number; reserved: number; created_at: string }
export interface Asset { id: string; name: string; kind: string; category: string; tags: string[]; size: number; width?: number; height?: number; source_job?: string; created_at: string; url: string; thumbnail: string }
export interface Operation { id: string; name: string; group: string; capability: string; kind: string; price: number; min_assets: number; max_assets: number; description: string; configured: boolean; provider_name?: string }
export interface Job { id: string; batch_id: string; operation: string; title: string; prompt: string; status: string; cost: number; reserved: number; error: string; progress: number; attempts: number; created_at: string; updated_at: string; inputs: {id: string; role: string}[]; parameters: Record<string, unknown>; result_ids: string[]; remote_id?: string }
export interface Provider { id: string; name: string; adapter: string; base_url: string; model: string; enabled: boolean; has_key: boolean; config: Record<string, unknown>; created_at: string }
export interface ProviderData { providers: Provider[]; bindings: Record<string, string | null>; capabilities: string[]; adapters: string[] }
export interface Stats { assets: number; works: number; active: number; waiting: number; configured: number; total_capabilities: number }
export type Page = 'home' | 'tools' | 'inspiration' | 'products' | 'links' | 'agents' | 'image' | 'model' | 'video' | 'assets' | 'works' | 'jobs' | 'providers' | 'credits' | 'members';
export interface Product { id: string; name: string; asset_ids: string[]; category: string; sku: string; description: string; selling_points: string; variants: string; created_at: string; updated_at: string }
export interface ProductLink { id: string; url: string; title: string; platform: string; product_id?: string; reference_text: string; status: string; created_at: string }
export type AgentMode = 'free' | 'suite' | 'video' | 'replicate' | 'commerce';
export interface PlanStep { title: string; operation: string; prompt: string; count: number; parameters: Record<string, unknown>; unit_price: number; configured: boolean; job_ids?: string[]; jobs: Job[] }
export interface AgentSession { id: string; mode: AgentMode; title: string; brief: string; input_ids: string[]; product_id?: string; link_id?: string; parameters: Record<string, unknown>; steps: PlanStep[]; status: string; plan_source: string; revision: number; estimated_cost: number; result_ids: string[]; created_at: string; messages: {role: string; content: string; created_at: string}[] }
export interface LaunchOptions { prompt?: string; batch?: boolean; mode?: AgentMode; template?: string; productId?: string; linkId?: string }
export type Navigate = (page: Page, operation?: string, assets?: string[], options?: LaunchOptions) => void;
