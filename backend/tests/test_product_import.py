"""Tests for the product CSV import service and API."""

import pytest
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.models.event import EventLog
from app.models.product import Product
from app.schemas.product import ProductImportResult
from app.services import product_service
from sqlalchemy import func, select

WORKSPACE = DEFAULT_WORKSPACE_ID

VALID_CSV = (
    "sku,name,description,category,brand,tags,attributes,source_url,supplier_code\n"
    'SKU-001,Camping Headlamp,USB rechargeable,camping,Nuotao,lamp;light,"{""max_lumens"": 300}",https://1688.com/item/1,\n'
    "SKU-002,Camping Stove Set,,cooking,,stove;pot,{},https://1688.com/item/2,\n"
)


@pytest.mark.asyncio
async def test_import_creates_products_and_events(db_session) -> None:
    """A valid CSV inserts products and publishes per-row events."""
    result = await product_service.import_products(
        db_session, workspace_id=WORKSPACE, csv_content=VALID_CSV
    )
    assert isinstance(result, ProductImportResult)
    assert result.imported == 2
    assert result.updated == 0
    assert result.failed == 0
    assert result.errors == []

    products = (await db_session.execute(select(Product))).scalars().all()
    assert len(products) == 2
    headlamp = next(p for p in products if p.sku == "SKU-001")
    assert headlamp.name == "Camping Headlamp"
    assert headlamp.category == "camping"
    assert headlamp.tags == ["lamp", "light"]
    assert headlamp.attributes == {"max_lumens": 300}
    assert headlamp.status == "draft"
    assert headlamp.source == "csv-import"

    events = (await db_session.execute(select(EventLog))).scalars().all()
    event_types = sorted(e.event_type for e in events)
    assert event_types == [
        "product.created",
        "product.created",
        "product.imported",
    ]


@pytest.mark.asyncio
async def test_import_updates_existing_sku(db_session) -> None:
    """Re-importing an existing sku updates the row instead of duplicating."""
    await product_service.import_products(db_session, workspace_id=WORKSPACE, csv_content=VALID_CSV)
    changed = "sku,name,description,category\nSKU-001,Camping Headlamp Pro,,lighting\n"
    result = await product_service.import_products(
        db_session, workspace_id=WORKSPACE, csv_content=changed
    )
    assert result.imported == 0
    assert result.updated == 1
    assert result.failed == 0

    total = (await db_session.execute(select(func.count()).select_from(Product))).scalar_one()
    assert total == 2
    headlamp = (
        await db_session.execute(select(Product).where(Product.sku == "SKU-001"))
    ).scalar_one()
    assert headlamp.name == "Camping Headlamp Pro"


@pytest.mark.asyncio
async def test_import_reports_bad_rows(db_session) -> None:
    """Rows missing required fields are reported without aborting the import."""
    csv_text = (
        "sku,name,attributes\n"
        "GOOD-1,Valid Product,{}\n"
        ",Missing Name,{}\n"
        "BAD-1,Bad Attributes,not-json\n"
    )
    result = await product_service.import_products(
        db_session, workspace_id=WORKSPACE, csv_content=csv_text
    )
    assert result.imported == 1
    assert result.failed == 2
    assert len(result.errors) == 2
    assert result.errors[0].message.startswith("sku and name are required")
    assert "attributes must be a JSON object" in result.errors[1].message


@pytest.mark.asyncio
async def test_import_unknown_supplier_fails_row(db_session) -> None:
    """A supplier_code that does not exist fails only that row."""
    csv_text = "sku,name,supplier_code\nSKU-9,Product,SUP-MISSING\n"
    result = await product_service.import_products(
        db_session, workspace_id=WORKSPACE, csv_content=csv_text
    )
    assert result.imported == 0
    assert result.failed == 1
    assert "not found" in result.errors[0].message


def test_import_missing_columns_rejected(api_client) -> None:
    """API rejects a CSV missing the required name column with 400."""
    response = api_client.post(
        "/api/v1/products/import",
        files={"file": ("products.csv", b"sku,description", "text/csv")},
    )
    assert response.status_code == 400
    assert "missing required columns: name" in response.json()["detail"]


def test_import_and_list_via_api(api_client) -> None:
    """End-to-end: upload CSV then list the imported products."""
    response = api_client.post(
        "/api/v1/products/import",
        files={"file": ("products.csv", VALID_CSV.encode("utf-8"), "text/csv")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["imported"] == 2
    assert body["failed"] == 0

    listed = api_client.get("/api/v1/products")
    assert listed.status_code == 200
    items = listed.json()
    assert len(items) == 2
    assert {item["sku"] for item in items} == {"SKU-001", "SKU-002"}
