"""Register all built-in worker executors in one place."""

from app.worker.agent_worker import register_executor
from app.worker.b2b_agent_executor import b2b_agent_executor
from app.worker.product_analyst_executor import product_analyst_executor


def register_builtin_executors() -> None:
    """Bind every built-in agent to its production executor."""
    register_executor("product_analyst", product_analyst_executor)
    for agent_id in (
        "b2b_sales_agent",
        "b2b_quotation_agent",
        "b2b_collection_agent",
    ):
        register_executor(agent_id, b2b_agent_executor)
