import { AgentPanel, AnalysisResult } from "./AgentPanel";
import { analyzeWithAgent } from "../../api/agentAnalysis";

const DEFAULT_CONTEXT = JSON.stringify(
  {
    suppliers: [
      { name: "Supplier A", on_time_delivery: 95.2, quality_rate: 98.5, lead_time_days: 25, unit_cost: 35.0 },
      { name: "Supplier B", on_time_delivery: 88.5, quality_rate: 95.0, lead_time_days: 18, unit_cost: 38.5 },
      { name: "Supplier C", on_time_delivery: 92.0, quality_rate: 97.2, lead_time_days: 30, unit_cost: 32.0 },
    ],
    inventory: {
      total_skus: 19,
      total_units: 1850,
      inventory_value: 45000,
      turnover_rate: 4.5,
      stockout_rate: 3.2,
      overstock_skus: 3,
    },
    logistics: {
      avg_shipping_time_days: 7,
      shipping_cost_per_order: 12.5,
      warehouse_utilization: 78,
    },
  },
  null,
  2
);

export function SupplyChainManagerPanel() {
  const handleAnalyze = async (contextStr: string): Promise<AnalysisResult | null> => {
    try {
      const context = JSON.parse(contextStr);
      const response = await analyzeWithAgent({
        agent_type: "supply_chain",
        context,
        temperature: 0.3,
      });
      if (!response.success || !response.result) {
        throw new Error(response.error || "Analysis failed");
      }
      return response.result as AnalysisResult;
    } catch (error) {
      console.error("Supply chain manager error:", error);
      return null;
    }
  };

  return (
    <AgentPanel
      agentName="供应链经理"
      agentColor="#f57c00"
      defaultContext={DEFAULT_CONTEXT}
      onAnalyze={handleAnalyze}
      resultKeys={[
        { key: "supplier_performance", label: "供应商绩效", type: "list" },
        { key: "inventory_optimization", label: "库存优化", type: "object" },
        { key: "cost_analysis", label: "成本分析", type: "object" },
        { key: "risk_assessment", label: "风险评估", type: "list" },
        { key: "recommendations", label: "优化建议", type: "list" },
      ]}
    />
  );
}
