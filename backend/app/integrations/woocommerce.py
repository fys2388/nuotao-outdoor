"""WooCommerce read-only connector (M4.3).

Synchronizes orders, products and customers from WooCommerce into the OS
through the existing services, keeping every write idempotent:

- orders    -> ``order_service.ingest_order()``  (unique external_order_id)
- products  -> product master upsert by SKU      (unique workspace + sku)
- customers -> customer profile upsert           (unique customer_reference_id)

**PII policy**: customer records are reduced to a deterministic reference
hash - names, emails and addresses are never persisted anywhere. Live sync
uses WooCommerce REST v3 (Basic auth with consumer key/secret) when ``data``
is omitted.
"""

import hashlib
import logging
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.base import Connector, ConnectorError, SyncSummary
from app.models.customer import CustomerProfile
from app.models.product import Product
from app.schemas.customer import CustomerProfileCreate, CustomerProfileUpdate
from app.schemas.order import WebhookOrderPayload
from app.services import customer, event_service, order_service

logger = logging.getLogger(__name__)

WOOCOMMERCE_KINDS: tuple[str, ...] = ("orders", "products", "customers")

# WooCommerce status values that map to an active product.
_ACTIVE_STATUSES: set[str] = {"publish", "active"}


def _reference_hash(identity: str) -> str:
    """Deterministic non-PII customer reference derived from an identity."""
    return hashlib.sha256(identity.strip().lower().encode("utf-8")).hexdigest()[:40]


def _as_str(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _as_decimal(value: Any, default: str = "0") -> str:
    text = _as_str(value)
    return text or default


class WooCommerceConnector(Connector):
    """Read-only WooCommerce connector: orders / products / customers."""

    name: str = "woocommerce"

    def validate(self, source: Any) -> list[str]:
        """Check the source shape: either a pushed batch or live REST config."""
        if not isinstance(source, dict):
            return ["source must be an object with 'kind', 'data' or REST config"]
        issues: list[str] = []
        kind = _as_str(source.get("kind") or "orders").lower()
        if kind not in WOOCOMMERCE_KINDS:
            issues.append(f"kind must be one of: {', '.join(WOOCOMMERCE_KINDS)}")
        if source.get("data") is not None and not isinstance(source["data"], list):
            issues.append("data must be a list of records")
        if source.get("data") is None:
            for key in ("base_url", "consumer_key", "consumer_secret"):
                if not _as_str(source.get(key)):
                    issues.append(f"{key} is required when data is omitted")
        return issues

    def transform(self, raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Normalize raw WooCommerce records into internal (kind-tagged) dicts."""
        normalized: list[dict[str, Any]] = []
        for record in raw:
            if not isinstance(record, dict):
                raise ConnectorError("each record must be an object")
            kind = _as_str(record.get("kind") or record.get("entity")).lower()
            if kind not in WOOCOMMERCE_KINDS:
                raise ConnectorError(f"unknown WooCommerce record kind '{kind}'")
            data = record["data"] if isinstance(record.get("data"), dict) else record
            if kind == "orders":
                normalized.append(self._transform_order(data))
            elif kind == "products":
                normalized.append(self._transform_product(data))
            else:
                normalized.append(self._transform_customer(data))
        return normalized

    def _transform_order(self, record: dict[str, Any]) -> dict[str, Any]:
        order_id = record.get("id")
        if order_id is None:
            raise ConnectorError("order record requires 'id'")
        shipping = record.get("shipping") if isinstance(record.get("shipping"), dict) else {}
        line_items = record.get("line_items") if isinstance(record.get("line_items"), list) else []
        return {
            "kind": "orders",
            "id": int(order_id),
            "status": _as_str(record.get("status")),
            "currency": _as_str(record.get("currency"), "USD"),
            "payment_method": _as_str(record.get("payment_method")) or None,
            "payment_method_title": _as_str(record.get("payment_method_title")) or None,
            "total": _as_decimal(record.get("total")),
            "subtotal": _as_decimal(record.get("subtotal")),
            "shipping_total": _as_decimal(record.get("shipping_total")),
            "discount_total": _as_decimal(record.get("discount_total")),
            "tax_total": _as_decimal(record.get("tax_total")),
            "shipping": {"country": _as_str(shipping.get("country")) or None},
            "line_items": [
                {
                    "id": item.get("id"),
                    "name": _as_str(item.get("name")),
                    "sku": _as_str(item.get("sku")) or None,
                    "quantity": int(item.get("quantity") or 1),
                    "total": _as_decimal(item.get("total")),
                }
                for item in line_items
                if isinstance(item, dict)
            ],
        }

    def _transform_product(self, record: dict[str, Any]) -> dict[str, Any]:
        sku = _as_str(record.get("sku"))
        name = _as_str(record.get("name"))
        if not sku or not name:
            raise ConnectorError("product record requires 'sku' and 'name'")
        categories = record.get("categories") if isinstance(record.get("categories"), list) else []
        category = ""
        for item in categories:
            if isinstance(item, dict) and _as_str(item.get("name")):
                category = _as_str(item["name"])
                break
        weight_text = _as_str(record.get("weight") or record.get("weight_kg"))
        weight_kg = None
        if weight_text:
            try:
                weight_kg = str(float(weight_text))
            except ValueError:
                weight_kg = None
        status = "active" if _as_str(record.get("status")).lower() in _ACTIVE_STATUSES else "draft"
        return {
            "kind": "products",
            "sku": sku,
            "name": name,
            "description": _as_str(record.get("description")) or None,
            "category": category or None,
            "brand": _as_str(record.get("brand")) or None,
            "source_url": _as_str(record.get("permalink")) or None,
            "status": status,
            "weight_kg": weight_kg,
            "target_market": _as_str(record.get("target_market"), "US"),
        }

    def _transform_customer(self, record: dict[str, Any]) -> dict[str, Any]:
        identity = _as_str(record.get("id") or record.get("email"))
        if not identity:
            raise ConnectorError("customer record requires 'id' or 'email' for reference")
        billing = record.get("billing") if isinstance(record.get("billing"), dict) else {}
        return {
            "kind": "customers",
            "reference_id": _reference_hash(identity),
            "country": _as_str(billing.get("country") or record.get("country")) or None,
            "language": _as_str(record.get("language")) or None,
            "segment": _as_str(record.get("segment")) or None,
            "total_orders": int(record.get("orders_count") or record.get("total_orders") or 0),
            "total_revenue": _as_decimal(record.get("total_spent") or record.get("total_revenue")),
        }

    async def sync(
        self,
        session: AsyncSession,
        *,
        workspace_id: UUID,
        source: Any,
        trace_id: str | None,
    ) -> SyncSummary:
        """Fetch (or accept a pushed batch), transform and persist records."""
        if not isinstance(source, dict):
            raise ConnectorError("source must be an object")
        kind = _as_str(source.get("kind") or "orders").lower()
        raw = source.get("data")
        if raw is None:
            raw = await self._fetch(source, kind)
        if not isinstance(raw, list):
            raise ConnectorError("data must be a list of records")
        records = self.transform(raw)

        summary = SyncSummary()
        for record in records:
            kind = record.pop("kind")
            if kind == "orders":
                created = await self._sync_order(
                    session, workspace_id=workspace_id, record=record, trace_id=trace_id
                )
            elif kind == "products":
                created = await self._sync_product(
                    session, workspace_id=workspace_id, record=record, trace_id=trace_id
                )
            else:
                created = await self._sync_customer(
                    session, workspace_id=workspace_id, record=record, trace_id=trace_id
                )
            summary.records_count += 1
            if created is True:
                summary.created_count += 1
            elif created is False:
                summary.updated_count += 1
            else:
                summary.skipped_count += 1
        logger.info(
            "woocommerce sync %s records=%s trace=%s", kind, summary.records_count, trace_id
        )
        return summary

    async def _sync_order(
        self, session: AsyncSession, *, workspace_id: UUID, record: dict, trace_id: str | None
    ) -> bool | None:
        """Ingest one order via order_service (idempotent); None = duplicate."""
        payload = WebhookOrderPayload(**record)
        response = await order_service.ingest_order(
            session, payload, workspace_id=workspace_id, trace_id=trace_id or ""
        )
        if response.status == "created":
            return True
        if response.status == "duplicate":
            return None
        return None

    async def _sync_product(
        self, session: AsyncSession, *, workspace_id: UUID, record: dict, trace_id: str | None
    ) -> bool | None:
        """Upsert one product master record by (workspace, sku)."""
        sku = record["sku"]
        existing = (
            await session.execute(
                select(Product).where(
                    Product.workspace_id == workspace_id,
                    Product.sku == sku,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            product = Product(
                workspace_id=workspace_id,
                sku=sku,
                name=record["name"],
                description=record.get("description"),
                category=record.get("category"),
                brand=record.get("brand"),
                status=record.get("status") or "draft",
                source="woocommerce",
                source_url=record.get("source_url"),
                weight_kg=record.get("weight_kg"),
                target_market=record.get("target_market") or "US",
            )
            session.add(product)
            await session.flush()
            await event_service.create_event(
                session,
                workspace_id=workspace_id,
                event_type="product.created",
                entity_type="product",
                entity_id=str(product.id),
                payload={"sku": sku, "source": "woocommerce"},
                trace_id=trace_id,
            )
            return True
        existing.name = record["name"]
        existing.description = record.get("description")
        existing.category = record.get("category")
        existing.brand = record.get("brand")
        existing.status = record.get("status") or existing.status
        existing.source_url = record.get("source_url")
        existing.weight_kg = record.get("weight_kg")
        existing.target_market = record.get("target_market") or existing.target_market
        await session.flush()
        await event_service.create_event(
            session,
            workspace_id=workspace_id,
            event_type="product.updated",
            entity_type="product",
            entity_id=str(existing.id),
            payload={"sku": sku, "source": "woocommerce"},
            trace_id=trace_id,
        )
        return False

    async def _sync_customer(
        self, session: AsyncSession, *, workspace_id: UUID, record: dict, trace_id: str | None
    ) -> bool | None:
        """Upsert one non-PII customer profile by reference hash."""
        reference_id = record["reference_id"]
        existing = (
            await session.execute(
                select(CustomerProfile).where(
                    CustomerProfile.workspace_id == workspace_id,
                    CustomerProfile.customer_reference_id == reference_id,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            profile = await customer.create_profile(
                session,
                workspace_id=workspace_id,
                data=CustomerProfileCreate(
                    customer_reference_id=reference_id,
                    country=record.get("country"),
                    language=record.get("language"),
                    segment=record.get("segment"),
                    total_orders=record.get("total_orders") or 0,
                    total_revenue=record.get("total_revenue") or "0",
                ),
                trace_id=trace_id,
            )
            logger.info("customer profile %s created from woocommerce", profile.id)
            return True
        await customer.update_profile(
            session,
            workspace_id=workspace_id,
            profile_id=existing.id,
            data=CustomerProfileUpdate(
                country=record.get("country"),
                language=record.get("language"),
                segment=record.get("segment"),
                total_orders=record.get("total_orders"),
                total_revenue=record.get("total_revenue"),
            ),
            trace_id=trace_id,
        )
        return False

    async def _fetch(self, source: dict, kind: str) -> list[dict[str, Any]]:
        """Live fetch from the WooCommerce REST API (v3, Basic auth)."""
        base_url = _as_str(source.get("base_url")).rstrip("/")
        auth = (_as_str(source.get("consumer_key")), _as_str(source.get("consumer_secret")))
        timeout = float(source.get("timeout_seconds") or 30)
        url = f"{base_url}/wp-json/wc/v3/{kind}"
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(
                    url, auth=auth, params={"per_page": source.get("per_page", 100)}
                )
        except httpx.HTTPError as exc:
            raise ConnectorError(f"woocommerce {kind} fetch failed: {exc}") from exc
        if response.status_code >= 400:
            raise ConnectorError(f"woocommerce {kind} fetch failed: HTTP {response.status_code}")
        return response.json()
