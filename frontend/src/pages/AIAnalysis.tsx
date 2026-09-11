import { useState } from "react";
import { genericAgentApi, GenericAgentResponse } from "../api/client";

interface AgentConfig {
  key: string;
  name: string;
  description: string;
  icon: string;
  defaultContext: string;
}

const agents: AgentConfig[] = [
  {
    key: "marketing-manager",
    name: "营销经理",
    description: "营销活动策划、内容创意、渠道推荐、ROI 预估",
    icon: "📣",
    defaultContext: JSON.stringify(
      {
        product: "户外帐篷",
        target_audience: "欧美露营爱好者",
        budget: 5000,
        season: "夏季",
        current_channels: ["Facebook", "Instagram"],
      },
      null,
      2
    ),
  },
  {
    key: "supply-chain-manager",
    name: "供应链经理",
    description: "供应商选择、成本优化、库存规划、物流建议",
    icon: "🚚",
    defaultContext: JSON.stringify(
      {
        product: "户外帐篷",
        current_supplier: "深圳某工厂",
        cost_price: 45,
        monthly_demand: 500,
        lead_time_days: 30,
        target_market: "欧美",
      },
      null,
      2
    ),
  },
  {
    key: "customer-service-manager",
    name: "客服经理",
    description: "客服回复建议、满意度提升、升级处理、趋势分析",
    icon: "💬",
    defaultContext: JSON.stringify(
      {
        recent_tickets: 15,
        common_issues: ["物流延迟", "产品质量", "退货退款"],
        satisfaction_score: 4.2,
        response_time_hours: 6,
      },
      null,
      2
    ),
  },
  {
    key: "business-analyst",
    name: "商业分析师",
    description: "财务分析、KPI 评估、趋势预测、风险因素、行动建议",
    icon: "📈",
    defaultContext: JSON.stringify(
      {
        monthly_revenue: 25000,
        monthly_cost: 18000,
        profit_margin: 0.28,
        top_products: ["帐篷", "睡袋", "登山杖"],
        growth_rate: 0.15,
        market_trend: "户外用品需求持续增长",
      },
      null,
      2
    ),
  },
];

export function AIAnalysis() {
  const [selectedAgent, setSelectedAgent] = useState<AgentConfig>(agents[0]);
  const [context, setContext] = useState(agents[0].defaultContext);
  const [result, setResult] = useState<GenericAgentResponse | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleAgentSelect = (agent: AgentConfig) => {
    setSelectedAgent(agent);
    setContext(agent.defaultContext);
    setResult(null);
    setError(null);
  };

  const handleAnalyze = async () => {
    setAnalyzing(true);
    setError(null);
    setResult(null);

    try {
      const contextObj = JSON.parse(context);
      const res = await genericAgentApi.analyze(selectedAgent.key, {
        context: contextObj,
        dry_run: false,
        temperature: 0.3,
      });

      if (res.error) {
        setError(res.error);
      } else if (res.data) {
        setResult(res.data);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "解析 JSON 失败，请检查输入格式");
    }

    setAnalyzing(false);
  };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "280px 1fr", gap: "1rem" }}>
      {/* Agent Selection */}
      <div style={{ background: "#fff", borderRadius: "0.75rem", padding: "1rem", boxShadow: "0 1px 3px rgba(0,0,0,0.1)" }}>
        <h3 style={{ margin: "0 0 1rem 0", fontSize: "0.95rem", color: "#333" }}>选择 AI Agent</h3>
        <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
          {agents.map((agent) => (
            <div
              key={agent.key}
              onClick={() => handleAgentSelect(agent)}
              style={{
                padding: "0.75rem",
                borderRadius: "0.5rem",
                cursor: "pointer",
                background: selectedAgent.key === agent.key ? "#e3f2fd" : "#f9f9f9",
                border: selectedAgent.key === agent.key ? "1px solid #2196f3" : "1px solid transparent",
                transition: "all 0.15s",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.25rem" }}>
                <span style={{ fontSize: "1.2rem" }}>{agent.icon}</span>
                <span style={{ fontSize: "0.85rem", fontWeight: 500, color: "#333" }}>{agent.name}</span>
              </div>
              <div style={{ fontSize: "0.7rem", color: "#999", lineHeight: 1.4 }}>{agent.description}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Analysis Panel */}
      <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
        {/* Context Input */}
        <div style={{ background: "#fff", borderRadius: "0.75rem", padding: "1.5rem", boxShadow: "0 1px 3px rgba(0,0,0,0.1)" }}>
          <h3 style={{ margin: "0 0 1rem 0", fontSize: "0.95rem", color: "#333" }}>
            {selectedAgent.icon} {selectedAgent.name} - 分析上下文
          </h3>
          <p style={{ fontSize: "0.8rem", color: "#666", margin: "0 0 1rem 0" }}>{selectedAgent.description}</p>
          <textarea
            value={context}
            onChange={(e) => setContext(e.target.value)}
            style={{
              width: "100%",
              minHeight: 200,
              padding: "0.75rem",
              border: "1px solid #ddd",
              borderRadius: "0.5rem",
              fontFamily: "monospace",
              fontSize: "0.8rem",
              resize: "vertical",
            }}
            placeholder="输入 JSON 格式的分析上下文..."
          />
          <div style={{ display: "flex", gap: "0.5rem", marginTop: "1rem" }}>
            <button
              onClick={handleAnalyze}
              disabled={analyzing}
              style={{
                padding: "0.6rem 1.5rem",
                background: analyzing ? "#ccc" : "#2196f3",
                color: "#fff",
                border: "none",
                borderRadius: "0.5rem",
                fontSize: "0.85rem",
                cursor: analyzing ? "not-allowed" : "pointer",
              }}
            >
              {analyzing ? "AI 分析中..." : "🚀 开始 AI 分析"}
            </button>
            <button
              onClick={() => setContext(selectedAgent.defaultContext)}
              style={{
                padding: "0.6rem 1.5rem",
                background: "#f5f5f5",
                color: "#666",
                border: "1px solid #ddd",
                borderRadius: "0.5rem",
                fontSize: "0.85rem",
                cursor: "pointer",
              }}
            >
              重置示例
            </button>
          </div>
          {error && (
            <div style={{ marginTop: "1rem", padding: "0.75rem", background: "#ffebee", color: "#c62828", borderRadius: "0.5rem", fontSize: "0.8rem" }}>
              错误: {error}
            </div>
          )}
        </div>

        {/* Analysis Result */}
        {result && (
          <div style={{ background: "#fff", borderRadius: "0.75rem", padding: "1.5rem", boxShadow: "0 1px 3px rgba(0,0,0,0.1)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
              <h3 style={{ margin: 0, fontSize: "0.95rem", color: "#333" }}>AI 分析结果</h3>
              <span
                style={{
                  background: result.status === "completed" ? "#e8f5e9" : "#ffebee",
                  color: result.status === "completed" ? "#2e7d32" : "#c62828",
                  padding: "0.25rem 0.75rem",
                  borderRadius: "1rem",
                  fontSize: "0.75rem",
                  fontWeight: 500,
                }}
              >
                {result.status}
              </span>
            </div>
            {result.agent_run_id && (
              <div style={{ fontSize: "0.75rem", color: "#999", marginBottom: "1rem" }}>
                运行 ID: {result.agent_run_id}
              </div>
            )}
            {result.output && (
              <pre
                style={{
                  background: "#f9f9f9",
                  padding: "1rem",
                  borderRadius: "0.5rem",
                  fontSize: "0.8rem",
                  overflowX: "auto",
                  maxHeight: 400,
                  overflowY: "auto",
                }}
              >
                {JSON.stringify(result.output, null, 2)}
              </pre>
            )}
            {result.error && (
              <div style={{ padding: "0.75rem", background: "#ffebee", color: "#c62828", borderRadius: "0.5rem", fontSize: "0.8rem" }}>
                {result.error}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
