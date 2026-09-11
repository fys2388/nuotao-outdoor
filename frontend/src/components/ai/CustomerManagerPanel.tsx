import { AgentPanel, AnalysisResult } from "./AgentPanel";
import { analyzeWithAgent } from "../../api/agentAnalysis";

const DEFAULT_CONTEXT = JSON.stringify(
  {
    customer: {
      name: "John Smith",
      email: "john.smith@example.com",
      total_orders: 5,
      total_spent: 425.5,
      last_order_date: "2026-08-15",
      customer_since: "2025-03-10",
    },
    recent_tickets: [
      { id: "T-001", subject: "Shipping delay", status: "open", priority: "high", created: "2026-08-28" },
      { id: "T-002", subject: "Product question", status: "resolved", priority: "low", created: "2026-08-20" },
    ],
    feedback: [
      { rating: 4, comment: "Great product, but shipping was slow.", date: "2026-08-25" },
      { rating: 5, comment: "Excellent quality, will buy again!", date: "2026-07-10" },
    ],
    support_metrics: {
      avg_response_time_hours: 4.5,
      resolution_rate: 85,
      customer_satisfaction: 4.2,
    },
  },
  null,
  2
);

export function CustomerManagerPanel() {
  const handleAnalyze = async (contextStr: string): Promise<AnalysisResult | null> => {
    try {
      const context = JSON.parse(contextStr);
      const response = await analyzeWithAgent({
        agent_type: "customer",
        context,
        temperature: 0.3,
      });
      if (!response.success || !response.result) {
        throw new Error(response.error || "Analysis failed");
      }
      return response.result as AnalysisResult;
    } catch (error) {
      console.error("Customer manager error:", error);
      return null;
    }
  };

  return (
    <AgentPanel
      agentName="客户经理"
      agentColor="#7b1fa2"
      defaultContext={DEFAULT_CONTEXT}
      onAnalyze={handleAnalyze}
      resultKeys={[
        { key: "sentiment_analysis", label: "情感分析", type: "object" },
        { key: "ticket_prioritization", label: "工单优先级", type: "list" },
        { key: "response_draft", label: "回复草稿", type: "text" },
        { key: "churn_risk", label: "流失风险", type: "object" },
        { key: "feedback_insights", label: "反馈洞察", type: "list" },
        { key: "recommendations", label: "客户体验建议", type: "list" },
      ]}
    />
  );
}
