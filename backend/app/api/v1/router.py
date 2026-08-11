"""API v1 router aggregating all endpoint routers."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    agents,
    calibration,
    events,
    health,
    knowledge,
    marketing,
    orders,
    product_intelligence,
    products,
    prompts,
    rules,
    webhooks,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(events.router)
api_router.include_router(rules.router)
api_router.include_router(products.router)
api_router.include_router(webhooks.router)
api_router.include_router(orders.router)
api_router.include_router(product_intelligence.product_router)
api_router.include_router(product_intelligence.decision_router)
api_router.include_router(agents.router)
api_router.include_router(agents.evaluation_router)
api_router.include_router(prompts.router)
api_router.include_router(calibration.router)
api_router.include_router(knowledge.router)
api_router.include_router(marketing.router)
