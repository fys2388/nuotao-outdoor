"""API v1 router aggregating all endpoint routers."""

from fastapi import APIRouter

from app.api.v1.endpoints import events, health, products, rules, webhooks

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(events.router)
api_router.include_router(rules.router)
api_router.include_router(products.router)
api_router.include_router(webhooks.router)
