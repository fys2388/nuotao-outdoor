"""AI agent definitions and tools.

Five AI roles for Nuotao Outdoor AI OS:
- Product Analyst: product analysis and recommendations
- Marketing Manager: marketing strategy and campaign analysis
- Supply Chain Manager: supplier, inventory, and logistics optimization
- Customer Manager: customer service, experience, and feedback analysis
- Business Analyst: financial, sales, and business intelligence

All agents are strictly "analyse + suggest + audit" - they never execute
business actions. All data access goes through the services layer.
"""

from app.agents.business_analyst import (
    BusinessAnalysisResult,
    analyze_business,
    analyze_profitability,
    generate_business_report,
)
from app.agents.customer_manager import (
    CustomerAnalysisResult,
    analyze_customer,
    analyze_customer_feedback,
    draft_customer_response,
)
from app.agents.generic_agent import GenericAgentResult, run_generic_agent
from app.agents.marketing_manager import (
    MarketingAnalysisResult,
    analyze_campaign,
    analyze_customer_segments,
    analyze_marketing,
)
from app.agents.product_analyst import (
    ProductAnalysisResult,
    ProductAnalystError,
    analyze_product,
)
from app.agents.supply_chain_manager import (
    SupplyChainAnalysisResult,
    analyze_inventory_optimization,
    analyze_supplier_performance,
    analyze_supply_chain,
)

__all__ = [
    # Product Analyst
    "ProductAnalystError",
    "ProductAnalysisResult",
    "analyze_product",
    # Marketing Manager
    "MarketingAnalysisResult",
    "analyze_marketing",
    "analyze_campaign",
    "analyze_customer_segments",
    # Supply Chain Manager
    "SupplyChainAnalysisResult",
    "analyze_supply_chain",
    "analyze_supplier_performance",
    "analyze_inventory_optimization",
    # Customer Manager
    "CustomerAnalysisResult",
    "analyze_customer",
    "draft_customer_response",
    "analyze_customer_feedback",
    # Business Analyst
    "BusinessAnalysisResult",
    "analyze_business",
    "generate_business_report",
    "analyze_profitability",
    # Generic
    "GenericAgentResult",
    "run_generic_agent",
]
