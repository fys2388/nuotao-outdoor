/**
 * AI Agent 分析 API 客户端
 * 连接后端 /agent-analysis 端点
 */

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000/api/v1";

export interface AgentAnalysisRequest {
  agent_type: "product" | "marketing" | "supply_chain" | "customer" | "business";
  context: Record<string, any>;
  temperature?: number;
}

export interface AgentAnalysisResponse {
  success: boolean;
  agent_type: string;
  agent_name: string;
  elapsed_seconds: number;
  result?: Record<string, any>;
  error?: string;
  token_usage?: Record<string, any>;
}

export interface AgentInfo {
  type: string;
  name: string;
  name_en: string;
  description: string;
}

/**
 * 运行 AI Agent 分析
 */
export async function analyzeWithAgent(
  request: AgentAnalysisRequest
): Promise<AgentAnalysisResponse> {
  try {
    const response = await fetch(`${API_BASE}/agent-analysis/analyze`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      const errorText = await response.text();
      return {
        success: false,
        agent_type: request.agent_type,
        agent_name: "",
        elapsed_seconds: 0,
        error: `HTTP ${response.status}: ${errorText}`,
      };
    }

    const data = await response.json();
    return data as AgentAnalysisResponse;
  } catch (error) {
    return {
      success: false,
      agent_type: request.agent_type,
      agent_name: "",
      elapsed_seconds: 0,
      error: error instanceof Error ? error.message : "Network error",
    };
  }
}

/**
 * 获取支持的 Agent 列表
 */
export async function listAgents(): Promise<AgentInfo[]> {
  try {
    const response = await fetch(`${API_BASE}/agent-analysis/agents`);
    if (!response.ok) {
      return [];
    }
    const data = await response.json();
    return data.agents || [];
  } catch {
    return [];
  }
}

/**
 * 批量运行多个 Agent 分析
 */
export async function batchAnalyze(
  requests: AgentAnalysisRequest[]
): Promise<AgentAnalysisResponse[]> {
  try {
    const response = await fetch(`${API_BASE}/agent-analysis/analyze/batch`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify(requests),
    });

    if (!response.ok) {
      return [];
    }

    const data = await response.json();
    return data.results || [];
  } catch {
    return [];
  }
}
