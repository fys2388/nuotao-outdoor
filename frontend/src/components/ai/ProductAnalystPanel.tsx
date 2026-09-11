import { AgentPanel, AnalysisResult } from "./AgentPanel";
import { analyzeWithAgent } from "../../api/agentAnalysis";

const DEFAULT_CONTEXT = JSON.stringify(
  {
    product: {
      name: "Premium Outdoor Camping Tent - 4 Person",
      sku: "NT-TENT-001",
      price: 79.99,
      cost: 35.0,
      stock_quantity: 50,
      category: "Camping Tents",
    },
    sales_data: {
      units_sold_30d: 120,
      revenue_30d: 9598.8,
      units_sold_90d: 350,
      revenue_90d: 27996.5,
      conversion_rate: 3.2,
      return_rate: 5.1,
    },
    competitors: [
      { name: "Competitor A", price: 89.99, rating: 4.5 },
      { name: "Competitor B", price: 69.99, rating: 4.2 },
      { name: "Competitor C", price: 99.99, rating: 4.7 },
    ],
  },
  null,
  2
);

export function ProductAnalystPanel() {
  const handleAnalyze = async (contextStr: string): Promise<AnalysisResult | null> => {
    try {
      const context = JSON.parse(contextStr);

      const response = await analyzeWithAgent({
        agent_type: "product",
        context,
        temperature: 0.3,
      });

      if (!response.success || !response.result) {
        throw new Error(response.error || "Analysis failed");
      }

      return response.result as AnalysisResult;
    } catch (error) {
      console.error("Product analyst error:", error);
      return null;
    }
  };

  return (
    <AgentPanel
      agentName="产品分析师"
      agentColor="#1976d2"
      defaultContext={DEFAULT_CONTEXT}
      onAnalyze={handleAnalyze}
      resultKeys={[
        { key: "performance_score", label: "性能评分", type: "number" },
        { key: "pricing_recommendation", label: "定价建议", type: "object" },
        { key: "competitive_position", label: "竞争定位", type: "text" },
        { key: "inventory_advice", label: "库存建议", type: "text" },
        { key: "actionable_insights", label: "可执行建议", type: "list" },
      ]}
    />
  );
}
