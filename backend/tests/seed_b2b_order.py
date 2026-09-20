"""Seed a delivered B2B order for local Chrome E2E verification."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select

from app.core.database import async_session_factory
from app.models.b2b import B2BOrder, B2BOrderItem
from app.models.product import Product


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--amount", required=True)
    parser.add_argument("--order-number", required=True)
    parser.add_argument("--created-at", required=True)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--product-sku")
    parser.add_argument("--product-name")
    return parser.parse_args()


async def _seed(args: argparse.Namespace) -> dict[str, str]:
    amount = Decimal(args.amount).quantize(Decimal("0.01"))
    created_at = datetime.fromisoformat(args.created_at.replace("Z", "+00:00"))
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)

    workspace_id = UUID(args.workspace_id)
    async with async_session_factory() as session:
        product: Product | None = None
        if args.product_sku:
            product = (
                await session.execute(
                    select(Product).where(
                        Product.workspace_id == workspace_id,
                        Product.sku == args.product_sku,
                    )
                )
            ).scalar_one_or_none()
            if product is None:
                product = Product(
                    workspace_id=workspace_id,
                    sku=args.product_sku,
                    name=args.product_name or args.product_sku,
                    status="active",
                )
                session.add(product)
                await session.flush()

        order = B2BOrder(
            workspace_id=workspace_id,
            order_number=args.order_number,
            agent_id=UUID(args.agent_id),
            business_model="B2B",
            status="delivered",
            payment_status="unpaid",
            subtotal=amount,
            discount_amount=Decimal("0.00"),
            shipping_cost=Decimal("0.00"),
            total=amount,
            currency="USD",
            shipping_address={},
            payment_due_date=created_at.date(),
            notes="Local agreement E2E fixture",
            created_at=created_at,
            updated_at=created_at,
        )
        if product is not None:
            order.items = [
                B2BOrderItem(
                    workspace_id=workspace_id,
                    product_id=product.id,
                    product_name=product.name,
                    sku=product.sku,
                    quantity=10,
                    unit_price=amount / Decimal("10"),
                    subtotal=amount,
                    currency="USD",
                )
            ]
        session.add(order)
        await session.commit()
        await session.refresh(order)
        return {
            "id": str(order.id),
            "order_number": order.order_number,
            "product_id": str(product.id) if product is not None else "",
            "product_sku": product.sku if product is not None else "",
        }


def main() -> None:
    print(json.dumps(asyncio.run(_seed(_arguments())), ensure_ascii=False))


if __name__ == "__main__":
    main()
