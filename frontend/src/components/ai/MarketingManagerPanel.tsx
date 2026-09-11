import { AgentPanel, AnalysisResult } from "./AgentPanel";
import { analyzeWithAgent } from "../../api/agentAnalysis";

const DEFAULT_CONTEXT = JSON.stringify(
  {
    campaigns: [
      { name: "Summer Sale", spend: 5000, revenue: 25000, conversions: 150 },
      { name: "Email Marketing", spend: 500, revenue: 8000, conversions: 80 },
      { name: "Google Ads", spend: 3000, revenue: 12000, conversions: 90 },
    ],
    customer_data: {
      total_customers: 2500,
      new_customers_30d: 180,
      repeat_purchase_rate: 22.5,
      avg_order_value: 85.5,
    },
    market_trends: {
      camping_gear_growth: 15.2,
      outdoor_apparel_growth: 8.7,
      season: "Summer",
    },
  },
  null,
  2
);

export function MarketingManagerPanel() {
  const handleAnalyze = async (contextStr: string): Promise<AnalysisResult | null> => {
    try {
      const context = JSON.parse(contextStr);
      const response = await analyzeWithAgent({
        agent_type: "marketing",
        context,
        temperature: 0.3,
      });
      if (!response.success || !response.result) {
        throw new Error(response.error || "Analysis failed");
      }
      return response.result as AnalysisResult;
    } catch (error) {
      console.error("Marketing manager error:", error);
      return null;
    }
  };

  return (
    <AgentPanel
      agentName="营销经理"
      agentColor="#388e3c"
      defaultContext={DEFAULT_CONTEXT}
      onAnalyze={handleAnalyze}
      resultKeys={[
        { key: "campaign_analysis", label: "活动分析", type: "object" },
        { key: "customer_segments", label: "客户细分", type: "list" },
        { key: "pricing_suggestions", label: "定价建议", type: "list" },
        { key: "marketing_recommendations", label: "营销建议", type: "list" },
      ]}
    />
  );
}
