import { AgentPanel, AnalysisResult } from "./AgentPanel";
import { analyzeWithAgent } from "../../api/agentAnalysis";

const DEFAULT_CONTEXT = JSON.stringify(
  {
    financials: {
      revenue_month: 85000,
      revenue_last_month: 78000,
      revenue_growth: 8.97,
      gross_margin: 52.5,
      net_margin: 18.3,
      operating_expenses: 25000,
      marketing_spend: 8500,
    },
    sales: {
      total_orders: 995,
      avg_order_value: 85.43,
      units_sold: 1850,
      top_category: "Camping Tents",
      top_product_revenue: 12500,
    },
    kpis: {
      customer_acquisition_cost: 42.5,
      customer_lifetime_value: 285.0,
      ltv_cac_ratio: 6.7,
      repeat_purchase_rate: 22.5,
      inventory_turnover: 4.5,
    },
    market: {
      total_market_size: 50000000,
      market_share: 0.17,
      industry_growth: 12.5,
      competitors_count: 25,
    },
  },
  null,
  2
);

export function BusinessAnalystPanel() {
  const handleAnalyze = async (contextStr: string): Promise<AnalysisResult | null> => {
    try {
      const context = JSON.parse(contextStr);
      const response = await analyzeWithAgent({
        agent_type: "business",
        context,
        temperature: 0.3,
      });
      if (!response.success || !response.result) {
        throw new Error(response.error || "Analysis failed");
      }
      return response.result as AnalysisResult;
    } catch (error) {
      console.error("Business analyst error:", error);
      return null;
    }
  };

  return (
    <AgentPanel
      agentName="商业分析师"
      agentColor="#c62828"
      defaultContext={DEFAULT_CONTEXT}
      onAnalyze={handleAnalyze}
      resultKeys={[
        { key: "financial_analysis", label: "财务分析", type: "object" },
        { key: "sales_analysis", label: "销售分析", type: "object" },
        { key: "kpi_dashboard", label: "KPI 仪表盘", type: "object" },
        { key: "market_opportunities", label: "市场机会", type: "list" },
        { key: "risk_assessment", label: "风险评估", type: "list" },
        { key: "profitability_analysis", label: "盈利能力分析", type: "object" },
        { key: "recommendations", label: "业务建议", type: "list" },
      ]}
    />
  );
}
