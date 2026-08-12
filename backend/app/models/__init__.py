"""ORM models package - importing it registers all models on Base.metadata."""

from app.models.agent import AiAgentRun
from app.models.agent_operations import AgentAlert, AgentApproval
from app.models.agent_runtime import (
    AgentEvaluation,
    AgentExecution,
    AgentMemory,
    AgentRegistry,
    AgentTask,
    AgentTool,
)
from app.models.agent_runtime_hardening import (
    AgentBudgetPolicy,
    AgentExecutionPolicy,
    AgentMetric,
    AgentRetryPolicy,
    AgentTaskAttempt,
)
from app.models.connector import BusinessRecommendation, ConnectorRun
from app.models.customer import (
    CustomerInteraction,
    CustomerKnowledgeEntry,
    CustomerProfile,
    ProductReview,
    RefundCase,
)
from app.models.customer_learning import (
    CustomerAiEvaluation,
    CustomerCalibrationRun,
    CustomerPatternRun,
)
from app.models.event import EventLog
from app.models.marketing import (
    Campaign,
    CreativeAsset,
    CustomerFeedback,
    MarketingExperiment,
)
from app.models.marketing_learning import (
    CampaignAiEvaluation,
    CreativeAnalysisRun,
    MarketingCalibrationRun,
    MarketingKnowledgeEntry,
)
from app.models.order import Order, OrderItem
from app.models.product import Product, ProductCost
from app.models.product_intelligence import (
    ConfidenceCalibration,
    ProductAiEvaluation,
    ProductAnalysisRun,
    ProductCostSnapshot,
    ProductDecision,
    ProductExperiment,
    ProductKnowledgeEntry,
    ProductScore,
    ProductScoreCalibrationRun,
    ProductScoreEvidence,
    ProductSource,
    SourcingCandidate,
)
from app.models.prompt import Prompt
from app.models.rule import Rule, RuleExecutionLog
from app.models.supplier import Supplier
from app.models.supply_chain import (
    InventorySnapshot,
    LogisticsEvent,
    PurchaseOrder,
    PurchaseOrderItem,
    ShipmentRecord,
    SupplierProfile,
    SupplyChainKnowledgeEntry,
)
from app.models.supply_chain_learning import (
    LogisticsAiEvaluation,
    LogisticsPatternRun,
    SupplierAiEvaluation,
    SupplierPatternRun,
    SupplyChainCalibrationRun,
)
from app.models.workspace import Workspace

__all__ = [
    "AiAgentRun",
    "AgentAlert",
    "AgentApproval",
    "AgentEvaluation",
    "AgentExecution",
    "AgentMemory",
    "AgentRegistry",
    "AgentTask",
    "AgentTool",
    "AgentBudgetPolicy",
    "AgentExecutionPolicy",
    "AgentMetric",
    "AgentRetryPolicy",
    "AgentTaskAttempt",
    "Order",
    "OrderItem",
    "EventLog",
    "Campaign",
    "CreativeAsset",
    "CustomerFeedback",
    "MarketingExperiment",
    "CustomerKnowledgeEntry",
    "CustomerInteraction",
    "CustomerProfile",
    "ProductReview",
    "RefundCase",
    "CustomerAiEvaluation",
    "CustomerCalibrationRun",
    "CustomerPatternRun",
    "CampaignAiEvaluation",
    "CreativeAnalysisRun",
    "MarketingCalibrationRun",
    "MarketingKnowledgeEntry",
    "Product",
    "ProductCost",
    "ConfidenceCalibration",
    "ProductAiEvaluation",
    "ProductAnalysisRun",
    "ProductCostSnapshot",
    "ProductDecision",
    "ProductExperiment",
    "ProductKnowledgeEntry",
    "ProductScore",
    "ProductScoreCalibrationRun",
    "ProductScoreEvidence",
    "ProductSource",
    "SourcingCandidate",
    "Prompt",
    "Rule",
    "RuleExecutionLog",
    "Supplier",
    "InventorySnapshot",
    "LogisticsEvent",
    "PurchaseOrder",
    "PurchaseOrderItem",
    "ShipmentRecord",
    "SupplierProfile",
    "SupplyChainKnowledgeEntry",
    "LogisticsAiEvaluation",
    "LogisticsPatternRun",
    "SupplierAiEvaluation",
    "SupplierPatternRun",
    "SupplyChainCalibrationRun",
    "BusinessRecommendation",
    "ConnectorRun",
    "Workspace",
]
