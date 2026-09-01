/**
 * API client for Nuotao AI OS backend.
 * Wraps fetch calls to the backend API.
 */

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000/api/v1";

export interface ApiResponse<T> {
  data?: T;
  error?: string;
  status: number;
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<ApiResponse<T>> {
  const url = `${API_BASE}${path}`;
  const defaultHeaders = {
    "Content-Type": "application/json",
    ...options.headers,
  };

  try {
    const response = await fetch(url, { ...options, headers: defaultHeaders });
    const text = await response.text();
    const data = text ? JSON.parse(text) : null;

    if (!response.ok) {
      return {
        status: response.status,
        error: data?.detail || data?.message || `HTTP ${response.status}`,
      };
    }

    return { status: response.status, data };
  } catch (error) {
    return {
      status: 0,
      error: error instanceof Error ? error.message : "Network error",
    };
  }
}

// Health
export const healthApi = {
  healthz: () => request<{ status: string }>("/healthz"),
  readyz: () =>
    request<{
      status: string;
      checks: { database: string; redis: string };
    }>("/readyz"),
};

// Products
export interface Product {
  id: string;
  workspace_id: string;
  sku: string;
  name: string;
  description?: string;
  category?: string;
  brand?: string;
  status: string;
  candidate_status?: string;
  source?: string;
  source_url?: string;
  cost_price?: number;
  sale_price?: number;
  created_at?: string;
  updated_at?: string;
}

export const productApi = {
  list: () => request<Product[]>("/products"),
  get: (id: string) => request<Product>(`/products/${id}`),
};

// Agents
export interface Agent {
  id: string;
  workspace_id: string;
  agent_id: string;
  name: string;
  domain: string;
  version: string;
  status: string;
  model_provider: string;
  model_name: string;
  prompt_version: string;
  permission_level: string;
  description?: string;
  created_at?: string;
  updated_at?: string;
}

export const agentApi = {
  list: () => request<Agent[]>("/agent-registry"),
  get: (id: string) => request<Agent>(`/agent-registry/${id}`),
};

// Generic Agent Analysis
export interface GenericAgentRequest {
  context: Record<string, unknown>;
  dry_run?: boolean;
  temperature?: number;
}

export interface GenericAgentResponse {
  agent_run_id?: number;
  status: string;
  output?: Record<string, unknown>;
  error?: string;
  dry_run: boolean;
}

export const genericAgentApi = {
  analyze: (
    agentKey: string,
    body: GenericAgentRequest
  ) =>
    request<GenericAgentResponse>(
      `/agents/${agentKey}/analyze`,
      {
        method: "POST",
        body: JSON.stringify(body),
      }
    ),
};

// Product Analyst
export interface ProductAnalysisResult {
  analysis_run_id: string;
  provider: string;
  model: string;
  prompt_version: string;
  decision_proposal_id?: string;
  decision?: string;
  confidence?: number;
  recommended_price?: number;
  max_cac?: number;
  test_quantity?: number;
  test_days?: number;
  tokens?: Record<string, number>;
  estimated_cost?: number;
  latency_ms?: number;
  trace_id?: string;
  status: string;
  approval_status?: string;
}

export const productAnalystApi = {
  analyze: (productId: string) =>
    request<ProductAnalysisResult>(
      `/agents/product-analyst/analyze/${productId}`,
      { method: "POST" }
    ),
  runs: (productId: string) =>
    request<unknown[]>(`/agents/product-analyst/runs/${productId}`),
};

// Events
export interface Event {
  id: string;
  workspace_id: string;
  event_type: string;
  entity_type: string;
  entity_id: string;
  payload?: Record<string, unknown>;
  actor?: string;
  trace_id?: string;
  created_at?: string;
}

export const eventApi = {
  list: (limit = 20) => request<Event[]>(`/events?limit=${limit}`),
};

// Rules
export interface Rule {
  id: string;
  workspace_id: string;
  rule_id: string;
  name: string;
  group: string;
  rule_type: string;
  version: string;
  status: string;
  description?: string;
  created_at?: string;
}

export const ruleApi = {
  list: () => request<Rule[]>("/rules"),
};
