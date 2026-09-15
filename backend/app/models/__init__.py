"""ORM models package - importing it registers all models on Base.metadata."""

from app.models.activity_plan import ActivityPlan
from app.models.agent import AiAgentRun
from app.models.agent_operations import AgentAlert, AgentApproval
from app.models.agent_platform import AgentApprovalRole, AgentApprovalSla, AgentVersion
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
from app.models.agent_suggestion import AgentSuggestion
from app.models.b2b import (
    B2BAgent,
    B2BOrder,
    B2BOrderItem,
    B2BPriceBook,
    B2BPriceTier,
    B2BPriceVersion,
    B2BProductPrice,
)
from app.models.b2b_agreements import (
    B2BAgentAgreement,
    B2BRebateAccrual,
    B2BRebateTier,
)
from app.models.b2b_finance import B2BInvoice, B2BReceipt, B2BReceivableEntry
from app.models.b2b_fulfillment import B2BFulfillment, B2BFulfillmentItem
from app.models.b2b_credit import (
    B2BCreditInsuranceClaim,
    B2BCreditInsurancePolicy,
    B2BCreditPolicy,
    B2BCreditRiskAssessment,
    B2BCreditStatusEvent,
)
from app.models.b2b_sales import B2BRFQ, B2BContract, B2BQuote, B2BQuoteItem, B2BRFQItem
from app.models.business_alert import BusinessAlert
from app.models.connector import BusinessRecommendation, ConnectorRun
from app.models.consolidation import Brand, CommerceAttribution, LegalEntity
from app.models.content_marketing import ContentItem, EDMCampaign, SEORecord
from app.models.currency import ExchangeRate
from app.models.customer import (
    CustomerAccount,
    CustomerInteraction,
    CustomerKnowledgeEntry,
    CustomerProfile,
    ProductReview,
    RefundCase,
)
from app.models.customer_identity import (
    CustomerAccountMerge,
    CustomerConsentEvent,
    CustomerIdentityLink,
    DataSubjectRequest,
    DataSubjectRequestAction,
)
from app.models.customer_learning import (
    CustomerAiEvaluation,
    CustomerCalibrationRun,
    CustomerPatternRun,
)
from app.models.edm_subscription import EDMSendLog, EmailSubscription
from app.models.event import EventLog
from app.models.growth_memory import GrowthMemory
from app.models.identity import WorkspaceIdentityLink
from app.models.image_gen import ImageGenerationTask
from app.models.influencer import Influencer, InfluencerCollaboration
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
    WooCommerceDraft,
)
from app.models.prompt import Prompt
from app.models.rule import Rule, RuleExecutionLog
from app.models.settlement import Settlement
from app.models.strategy_version import StrategyVersion
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
    "ActivityPlan",
    "AgentAlert",
    "AgentApproval",
    "AgentApprovalRole",
    "AgentApprovalSla",
    "AgentBudgetPolicy",
    "AgentEvaluation",
    "AgentExecution",
    "AgentExecutionPolicy",
    "AgentMemory",
    "AgentMetric",
    "AgentRegistry",
    "AgentRetryPolicy",
    "AgentTask",
    "AgentTaskAttempt",
    "AgentTool",
    "AgentVersion",
    "AiAgentRun",
    "B2BAgent",
    "B2BAgentAgreement",
    "B2BOrder",
    "B2BOrderItem",
    "B2BContract",
    "B2BCreditInsuranceClaim",
    "B2BCreditInsurancePolicy",
    "B2BCreditPolicy",
    "B2BCreditRiskAssessment",
    "B2BCreditStatusEvent",
    "B2BFulfillment",
    "B2BFulfillmentItem",
    "B2BInvoice",
    "B2BPriceBook",
    "B2BPriceTier",
    "B2BPriceVersion",
    "B2BProductPrice",
    "B2BQuote",
    "B2BQuoteItem",
    "B2BReceivableEntry",
    "B2BRebateAccrual",
    "B2BRebateTier",
    "B2BReceipt",
    "B2BRFQ",
    "B2BRFQItem",
    "BusinessRecommendation",
    "Brand",
    "Campaign",
    "CampaignAiEvaluation",
    "ConfidenceCalibration",
    "ConnectorRun",
    "CommerceAttribution",
    "ContentItem",
    "CreativeAnalysisRun",
    "CreativeAsset",
    "CustomerAiEvaluation",
    "CustomerAccount",
    "CustomerAccountMerge",
    "CustomerCalibrationRun",
    "CustomerConsentEvent",
    "CustomerFeedback",
    "CustomerIdentityLink",
    "CustomerInteraction",
    "CustomerKnowledgeEntry",
    "CustomerPatternRun",
    "CustomerProfile",
    "DataSubjectRequest",
    "DataSubjectRequestAction",
    "EDMCampaign",
    "EventLog",
    "ExchangeRate",
    "ImageGenerationTask",
    "Influencer",
    "InfluencerCollaboration",
    "LegalEntity",
    "InventorySnapshot",
    "LogisticsAiEvaluation",
    "LogisticsEvent",
    "LogisticsPatternRun",
    "MarketingCalibrationRun",
    "MarketingExperiment",
    "MarketingKnowledgeEntry",
    "Order",
    "OrderItem",
    "Product",
    "ProductAiEvaluation",
    "ProductAnalysisRun",
    "ProductCost",
    "ProductCostSnapshot",
    "ProductDecision",
    "ProductExperiment",
    "ProductKnowledgeEntry",
    "ProductReview",
    "ProductScore",
    "ProductScoreCalibrationRun",
    "ProductScoreEvidence",
    "ProductSource",
    "Prompt",
    "PurchaseOrder",
    "PurchaseOrderItem",
    "RefundCase",
    "Rule",
    "RuleExecutionLog",
    "SEORecord",
    "Settlement",
    "ShipmentRecord",
    "SourcingCandidate",
    "Supplier",
    "SupplierAiEvaluation",
    "SupplierPatternRun",
    "SupplierProfile",
    "SupplyChainCalibrationRun",
    "SupplyChainKnowledgeEntry",
    "WooCommerceDraft",
    "Workspace",
    "WorkspaceIdentityLink",
]
