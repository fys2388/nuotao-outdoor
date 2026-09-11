import { useState } from "react";
import { ProductAnalystPanel } from "../components/ai/ProductAnalystPanel";
import { MarketingManagerPanel } from "../components/ai/MarketingManagerPanel";
import { SupplyChainManagerPanel } from "../components/ai/SupplyChainManagerPanel";
import { CustomerManagerPanel } from "../components/ai/CustomerManagerPanel";
import { BusinessAnalystPanel } from "../components/ai/BusinessAnalystPanel";

const AGENTS = [
  {
    id: "product",
    name: "产品分析师",
    nameEn: "Product Analyst",
    icon: "📦",
    color: "#1976d2",
    description: "产品性能分析、定价建议、竞争定位、库存优化",
  },
  {
    id: "marketing",
    name: "营销经理",
    nameEn: "Marketing Manager",
    icon: "📣",
    color: "#388e3c",
    description: "活动 ROI 分析、客户细分、定价策略、营销建议",
  },
  {
    id: "supply",
    name: "供应链经理",
    nameEn: "Supply Chain Manager",
    icon: "🚚",
    color: "#f57c00",
    description: "供应商评估、库存优化、成本分析、风险评估",
  },
  {
    id: "customer",
    name: "客户经理",
    nameEn: "Customer Manager",
    icon: "👤",
    color: "#7b1fa2",
    description: "客户情感分析、工单优先级、回复草稿、流失风险",
  },
  {
    id: "business",
    name: "商业分析师",
    nameEn: "Business Analyst",
    icon: "📊",
    color: "#c62828",
    description: "财务分析、销售趋势、KPI 跟踪、市场机会、风险评估",
  },
];

export function AIConsole() {
  const [activeAgent, setActiveAgent] = useState("product");

  const renderPanel = () => {
    switch (activeAgent) {
      case "product":
        return <ProductAnalystPanel />;
      case "marketing":
        return <MarketingManagerPanel />;
      case "supply":
        return <SupplyChainManagerPanel />;
      case "customer":
        return <CustomerManagerPanel />;
      case "business":
        return <BusinessAnalystPanel />;
      default:
        return <ProductAnalystPanel />;
    }
  };

  return (
    <div style={{ padding: "1.5rem" }}>
      {/* 页面标题 */}
      <div style={{ marginBottom: "1.5rem" }}>
        <h1 style={{ margin: 0, fontSize: "1.5rem", color: "#1a1a1a" }}>
          AI 智能控制台
        </h1>
        <p style={{ margin: "0.5rem 0 0 0", color: "#666", fontSize: "0.9rem" }}>
          5 个 AI 角色协同工作，提供数据驱动的业务分析与建议
        </p>
      </div>

      {/* Agent 选择标签 */}
      <div
        style={{
          display: "flex",
          gap: "0.75rem",
          marginBottom: "1.5rem",
          flexWrap: "wrap",
        }}
      >
        {AGENTS.map((agent) => (
          <button
            key={agent.id}
            onClick={() => setActiveAgent(agent.id)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
              padding: "0.75rem 1.25rem",
              borderRadius: "0.5rem",
              border: activeAgent === agent.id
                ? `2px solid ${agent.color}`
                : "2px solid #e0e0e0",
              background: activeAgent === agent.id ? "#fff" : "#fafafa",
              cursor: "pointer",
              transition: "all 0.2s",
              boxShadow: activeAgent === agent.id
                ? `0 2px 8px ${agent.color}33`
                : "none",
            }}
          >
            <span style={{ fontSize: "1.25rem" }}>{agent.icon}</span>
            <div style={{ textAlign: "left" }}>
              <div
                style={{
                  fontSize: "0.85rem",
                  fontWeight: 600,
                  color: activeAgent === agent.id ? agent.color : "#333",
                }}
              >
                {agent.name}
              </div>
              <div style={{ fontSize: "0.7rem", color: "#999" }}>
                {agent.nameEn}
              </div>
            </div>
          </button>
        ))}
      </div>

      {/* 当前 Agent 描述 */}
      {AGENTS.find((a) => a.id === activeAgent) && (
        <div
          style={{
            padding: "1rem 1.25rem",
            background: "#f5f5f5",
            borderRadius: "0.5rem",
            marginBottom: "1.5rem",
            borderLeft: `4px solid ${AGENTS.find((a) => a.id === activeAgent)?.color}`,
          }}
        >
          <div style={{ fontSize: "0.85rem", color: "#555" }}>
            <strong>{AGENTS.find((a) => a.id === activeAgent)?.name}：</strong>
            {AGENTS.find((a) => a.id === activeAgent)?.description}
          </div>
        </div>
      )}

      {/* Agent 面板内容 */}
      {renderPanel()}
    </div>
  );
}
