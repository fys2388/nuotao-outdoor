"""ORM models package - importing it registers all models on Base.metadata."""

from app.models.agent import AiAgentRun
from app.models.event import EventLog
from app.models.order import Order, OrderItem
from app.models.product import Product, ProductCost
from app.models.product_intelligence import (
    ProductAiEvaluation,
    ProductAnalysisRun,
    ProductCostSnapshot,
    ProductDecision,
    ProductExperiment,
    ProductScore,
    ProductScoreEvidence,
    ProductSource,
    SourcingCandidate,
)
from app.models.prompt import Prompt
from app.models.rule import Rule, RuleExecutionLog
from app.models.supplier import Supplier
from app.models.workspace import Workspace

__all__ = [
    "AiAgentRun",
    "Order",
    "OrderItem",
    "EventLog",
    "Product",
    "ProductCost",
    "ProductAiEvaluation",
    "ProductAnalysisRun",
    "ProductCostSnapshot",
    "ProductDecision",
    "ProductExperiment",
    "ProductScore",
    "ProductScoreEvidence",
    "ProductSource",
    "SourcingCandidate",
    "Prompt",
    "Rule",
    "RuleExecutionLog",
    "Supplier",
    "Workspace",
]
