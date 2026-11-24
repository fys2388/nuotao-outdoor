"""Synthetic raw exports mimicking the §2 read-only SELECT outputs (7 groups).

All values are fabricated for logic testing only; they are NOT production data.
Headers match the plan §2 column sets (subset used by the scripts/tests).
"""

from __future__ import annotations

import csv
from pathlib import Path

BASE = Path(__file__).resolve().parent
RAW = BASE / "raw"
RAW.mkdir(parents=True, exist_ok=True)

# G4: every workspace-scoped table in the schema carries workspace_id. The
# synthetic exports expose it so the workspace-consistency check can run.
WORKSPACE_ID = "ws-test-1"
WORKSPACE_FILES = {
    "orders.csv",
    "orders_lines.csv",
    "tax.csv",
    "payments.csv",
    "refunds.csv",
    "order_marketing.csv",
}


def _dump(name: str, fieldnames: list[str], rows: list[dict]) -> None:
    if name in WORKSPACE_FILES:
        fieldnames = ["workspace_id", *fieldnames]
        rows = [{"workspace_id": WORKSPACE_ID, **row} for row in rows]
    with (RAW / name).open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, restval="")
        writer.writeheader()
        writer.writerows(rows)


ORDER_COLUMNS = [
    "order_pk",
    "external_order_id",
    "customer_account_id",
    "customer_reference_id",
    "currency",
    "subtotal",
    "shipping_total",
    "discount_total",
    "tax_total",
    "total",
    "payment_fee",
    "refunded_amount",
    "advertising_cost",
    "profit_snapshot",
    "rule_results",
    "received_at",
    "created_at",
    "updated_at",
    "trace_id",
    # PII columns that a raw export might still carry (must be stripped):
    "billing_email",
    "billing_first_name",
    "billing_last_name",
    "billing_address_1",
    "billing_city",
    "billing_phone",
    "billing_country",
    "shipping_address_1",
    "shipping_city",
    "shipping_postcode",
    "card_number",
    "first_name",
    "last_name",
    "display_name",
    "customer_number",
    "email",
    "phone",
]

ORDERS = [
    {
        "order_pk": "o-001",
        "external_order_id": "WC-1001",
        "customer_account_id": "ca-9001",
        "customer_reference_id": "ref-7001",
        "currency": "USD",
        "subtotal": "90.00",
        "shipping_total": "5.00",
        "discount_total": "0.00",
        "tax_total": "8.00",
        "total": "103.00",
        "payment_fee": "3.78",
        "refunded_amount": "0.00",
        "advertising_cost": "1.20",
        "profit_snapshot": '{"revenue": "103.00", "product_cost": "20.00", "cost_details": {"SKU-1": "10.00"}, "payment_fee": "3.78", "cost_status": "KNOWN", "revenue_excl_tax": "95.00"}',
        "rule_results": '{"profit_rule": {"passed": true}}',
        "received_at": "2026-08-15T09:00:00Z",
        "created_at": "2026-08-15T09:00:01Z",
        "updated_at": "2026-08-15T09:05:00Z",
        "trace_id": "tr-001",
        "billing_email": "jdoe@example.com",
        "billing_first_name": "John",
        "billing_last_name": "Doe",
        "billing_address_1": "123 Anywhere St",
        "billing_city": "Springfield",
        "billing_phone": "+1-555-0101",
        "billing_country": "US",
        "shipping_address_1": "123 Anywhere St",
        "shipping_city": "Springfield",
        "shipping_postcode": "62701",
        "card_number": "4242424242424242",
        "first_name": "John",
        "last_name": "Doe",
        "display_name": "John Doe",
        "customer_number": "CUST-1001",
        "email": "jdoe@example.com",
        "phone": "+1-555-0101",
    },
    {
        "order_pk": "o-002",
        "external_order_id": "WC-1002",
        "customer_account_id": "ca-9002",
        "currency": "USD",
        "subtotal": "50.00",
        "shipping_total": "0.00",
        "discount_total": "5.00",
        "tax_total": "4.50",
        "total": "49.50",
        "payment_fee": "2.07",
        "refunded_amount": "25.00",
        "advertising_cost": "",
        "profit_snapshot": '{"revenue": "49.50", "product_cost": "30.00", "cost_status": "ESTIMATED", "revenue_excl_tax": "45.00"}',
        "received_at": "2026-08-20T10:30:00Z",
        "created_at": "2026-08-20T10:30:01Z",
        "updated_at": "2026-08-20T11:00:00Z",
        "trace_id": "tr-002",
    },
    {
        "order_pk": "o-003",
        "external_order_id": "WC-1003",
        "customer_account_id": "ca-9003",
        "customer_reference_id": "ref-7003",
        "currency": "USD",
        "subtotal": "120.00",
        "shipping_total": "12.00",
        "discount_total": "0.00",
        "tax_total": "0.00",
        "total": "132.00",
        "payment_fee": "4.43",
        "refunded_amount": "0.00",
        "advertising_cost": "3.50",
        "profit_snapshot": '{"revenue": "132.00", "product_cost": "55.00", "cost_status": "KNOWN", "revenue_excl_tax": "132.00"}',
        "rule_results": '{"profit_rule": {"passed": false}}',
        "received_at": "2026-09-01T08:15:00Z",
        "created_at": "2026-09-01T08:15:01Z",
        "updated_at": "2026-09-01T09:00:00Z",
        "trace_id": "tr-003",
    },
]

LINE_COLUMNS = [
    "line_pk",
    "order_pk",
    "external_item_id",
    "product_id",
    "sku",
    "name",
    "quantity",
    "unit_price",
    "line_total",
    "wc_variation_id",
    "variation_sku",
    "identity_state",
    "cost_snapshot_id",
    "cost_snapshot_version",
    "pricing_rule_version",
    "pricing_engine_version",
    "evidence_grade",
]

LINES = [
    {
        "line_pk": "l-001",
        "order_pk": "o-001",
        "product_id": "P-01",
        "sku": "SKU-1",
        "name": "Camping Lantern",
        "quantity": "1",
        "unit_price": "90.00",
        "line_total": "90.00",
        "identity_state": "UNKNOWN_LEGACY",
    },
    {
        "line_pk": "l-002",
        "order_pk": "o-002",
        "product_id": "P-02",
        "sku": "SKU-3",
        "name": "Trekking Poles",
        "quantity": "1",
        "unit_price": "50.00",
        "line_total": "50.00",
        "identity_state": "UNKNOWN_LEGACY",
    },
    {
        "line_pk": "l-003",
        "order_pk": "o-003",
        "product_id": "P-03",
        "sku": "SKU-4",
        "name": "Folding Chair",
        "quantity": "2",
        "unit_price": "60.00",
        "line_total": "120.00",
        "wc_variation_id": "101",
        "variation_sku": "SKU-4-GRAY",
        "identity_state": "VARIATION",
        "cost_snapshot_id": "s-003",
        "cost_snapshot_version": "v2",
    },
    {
        "line_pk": "l-004",
        "order_pk": "o-003",
        "product_id": "P-03",
        "sku": "SKU-5",
        "name": "Water Bottle",
        "quantity": "1",
        "unit_price": "30.00",
        "line_total": "30.00",
        "identity_state": "UNKNOWN_LEGACY",
    },
]

SNAPSHOT_COLUMNS = [
    "snapshot_pk",
    "product_id",
    "variation_id",
    "variation_sku",
    "currency",
    "purchase_cost",
    "domestic_shipping",
    "first_leg_shipping",
    "last_leg_shipping",
    "international_shipping",
    "packaging",
    "tax_estimate",
    "handling",
    "total_landed_cost",
    "version",
    "payment_fee",
    "marketing_amortization",
    "after_sales_loss",
    "total_cost",
    "weight_kg",
    "source",
    "valid_from",
    "created_at",
    "trace_id",
]

SNAPSHOTS = [
    {
        "snapshot_pk": "s-001",
        "product_id": "P-01",
        "currency": "USD",
        "purchase_cost": "15.00",
        "domestic_shipping": "0.70",
        "first_leg_shipping": "6.30",
        "last_leg_shipping": "10.00",
        "international_shipping": "0.00",
        "packaging": "1.20",
        "tax_estimate": "0.00",
        "handling": "0.50",
        "total_landed_cost": "33.70",
        "version": "v1",
        "total_cost": "28.80",
        "weight_kg": "0.80",
        "source": "cost_prefill",
        "valid_from": "2026-08-01T00:00:00Z",
        "created_at": "2026-08-01T00:00:00Z",
        "trace_id": "tr-s1",
    },
    {
        "snapshot_pk": "s-002",
        "product_id": "P-02",
        "currency": "USD",
        "purchase_cost": "20.00",
        "total_landed_cost": "38.70",
        "version": "v1",
        "total_cost": "33.80",
        "weight_kg": "1.00",
        "source": "cost_prefill",
        "valid_from": "2026-08-01T00:00:00Z",
        "created_at": "2026-08-01T00:00:00Z",
        "trace_id": "tr-s2",
    },
    {
        "snapshot_pk": "s-003",
        "product_id": "P-03",
        "variation_id": "101",
        "variation_sku": "SKU-4-GRAY",
        "currency": "USD",
        "purchase_cost": "10.00",
        "total_landed_cost": "28.70",
        "version": "v2",
        "total_cost": "24.70",
        "weight_kg": "0.90",
        "source": "supplier_quote",
        "valid_from": "2026-08-25T00:00:00Z",
        "created_at": "2026-08-25T00:00:00Z",
        "trace_id": "tr-s3",
    },
    {
        "snapshot_pk": "s-004",
        "product_id": "P-01",
        "currency": "USD",
        "purchase_cost": "14.00",
        "total_landed_cost": "32.70",
        "version": "v2",
        "total_cost": "27.80",
        "weight_kg": "0.80",
        "source": "cost_prefill",
        "valid_from": "2026-09-05T00:00:00Z",
        "created_at": "2026-09-05T00:00:00Z",
        "trace_id": "tr-s4",
    },
]

PAYMENT_COLUMNS = [
    "order_pk",
    "payment_method",
    "payment_status",
    "currency",
    "total",
    "payment_fee",
    "refunded_amount",
    "received_at",
]

PAYMENTS = [
    {
        "order_pk": "o-001",
        "payment_method": "stripe",
        "payment_status": "paid",
        "currency": "USD",
        "total": "103.00",
        "payment_fee": "3.78",
        "refunded_amount": "0.00",
        "received_at": "2026-08-15T09:00:00Z",
    },
    {
        "order_pk": "o-002",
        "payment_method": "stripe",
        "payment_status": "paid",
        "currency": "USD",
        "total": "49.50",
        "payment_fee": "2.07",
        "refunded_amount": "25.00",
        "received_at": "2026-08-20T10:30:00Z",
    },
    {
        "order_pk": "o-003",
        "payment_method": "paypal",
        "payment_status": "paid",
        "currency": "USD",
        "total": "132.00",
        "payment_fee": "4.43",
        "refunded_amount": "0.00",
        "received_at": "2026-09-01T08:15:00Z",
    },
]

REFUND_COLUMNS = [
    "refund_pk",
    "order_pk",
    "status",
    "refund_type",
    "requested_amount",
    "approved_amount",
    "executed_amount",
    "payment_provider",
    "payment_refund_id",
    "woocommerce_refund_id",
    "executed_at",
    "created_at",
]

REFUNDS = [
    {
        "refund_pk": "r-001",
        "order_pk": "o-002",
        "status": "succeeded",
        "refund_type": "partial",
        "requested_amount": "25.00",
        "approved_amount": "25.00",
        "executed_amount": "25.00",
        "payment_provider": "stripe",
        "payment_refund_id": "stripe_ref_abc123",
        "executed_at": "2026-08-25T12:00:00Z",
        "created_at": "2026-08-24T09:00:00Z",
    },
    {
        "refund_pk": "r-002",
        "order_pk": "o-003",
        "status": "processing",
        "refund_type": "full",
        "requested_amount": "132.00",
        "approved_amount": "132.00",
        "payment_provider": "stripe",
        "payment_refund_id": "stripe_ref_xyz789",
        "created_at": "2026-09-09T08:00:00Z",
    },
]

SHIPMENT_COLUMNS = [
    "shipment_pk",
    "carrier",
    "origin",
    "destination",
    "tracking_number",
    "status",
    "ship_date",
    "delivery_time_days",
    "actual_cost",
    "actual_cost_currency",
    "created_at",
]

SHIPMENTS = [
    {
        "shipment_pk": "sh-001",
        "carrier": "YTO",
        "origin": "Guangzhou",
        "destination": "US-CA",
        "tracking_number": "TRK-778899",
        "status": "in_transit",
        "ship_date": "2026-08-16",
        "delivery_time_days": "7",
        "actual_cost": "22.50",
        "actual_cost_currency": "USD",
        "created_at": "2026-08-16T04:00:00Z",
    },
]

EVENT_COLUMNS = [
    "event_pk",
    "shipment_id",
    "event_type",
    "location",
    "description",
    "occurred_at",
]
EVENTS = [
    {
        "event_pk": "e-001",
        "shipment_id": "sh-001",
        "event_type": "picked_up",
        "location": "Guangzhou",
        "description": "Pickup completed",
        "occurred_at": "2026-08-16T05:00:00Z",
    },
    {
        "event_pk": "e-002",
        "shipment_id": "sh-001",
        "event_type": "departed",
        "location": "Guangzhou",
        "description": "Export customs cleared",
        "occurred_at": "2026-08-17T12:00:00Z",
    },
]

CAMPAIGN_COLUMNS = [
    "campaign_pk",
    "platform",
    "campaign_id",
    "name",
    "product_id",
    "currency",
    "spend",
    "impressions",
    "clicks",
    "conversion",
    "revenue",
    "roas",
    "started_at",
    "ended_at",
]

CAMPAIGNS = [
    {
        "campaign_pk": "c-001",
        "platform": "meta",
        "campaign_id": "meta-cmp-8842",
        "name": "August US DTC campaign",
        "product_id": "P-01",
        "currency": "USD",
        "spend": "350.00",
        "impressions": "12000",
        "clicks": "610",
        "conversion": "42",
        "revenue": "860.00",
        "roas": "2.46",
        "started_at": "2026-08-01T00:00:00Z",
        "ended_at": "2026-08-31T23:59:59Z",
    },
    {
        "campaign_pk": "c-002",
        "platform": "google",
        "campaign_id": "goog-cmp-119",
        "name": "Headlamp search",
        "product_id": "P-03",
        "currency": "USD",
        "spend": "120.00",
        "impressions": "4500",
        "clicks": "230",
        "conversion": "15",
        "revenue": "380.00",
        "roas": "3.17",
        "started_at": "2026-09-01T00:00:00Z",
    },
]

PRICE_COLUMNS = [
    "product_pk",
    "sku",
    "price_current",
    "regular_price_current",
    "sale_price_current",
    "wc_product_id",
    "wc_total_sales",
    "created_at",
    "price_modified_at",
    "price_lineage",
    "wc_variation_id",
]

PRICES = [
    {
        "product_pk": "P-01",
        "sku": "SKU-1",
        "price_current": "29.99",
        "regular_price_current": "29.99",
        "wc_product_id": "1001",
        "wc_total_sales": "23",
        "created_at": "2026-07-01T00:00:00Z",
        "price_modified_at": "2026-08-01T00:00:00Z",
        "price_lineage": "LEGACY_NO_PUBLICATION_RECORD",
    },
    {
        "product_pk": "P-03",
        "sku": "SKU-4",
        "price_current": "59.99",
        "regular_price_current": "59.99",
        "sale_price_current": "49.99",
        "wc_product_id": "1003",
        "wc_total_sales": "7",
        "created_at": "2026-07-20T00:00:00Z",
        "price_modified_at": "2026-09-10T00:00:00Z",
        "price_lineage": "LEGACY_NO_PUBLICATION_RECORD",
    },
]

MARKETING_COLUMNS = ["order_pk", "advertising_cost", "missing_reason"]
MARKETING = [
    {"order_pk": "o-001", "advertising_cost": "1.20"},
    {"order_pk": "o-002"},
    {"order_pk": "o-003", "advertising_cost": "3.50"},
]

COST_CURRENT_COLUMNS = [
    "order_pk",
    "product_id",
    "sku",
    "quantity",
    "unit_price",
    "line_total",
    "received_at",
]
COST_CURRENT = [
    {
        "order_pk": "o-001",
        "product_id": "P-01",
        "sku": "SKU-1",
        "quantity": "1",
        "unit_price": "90.00",
        "line_total": "90.00",
        "received_at": "2026-08-15T09:00:00Z",
    },
    {
        "order_pk": "o-002",
        "product_id": "P-02",
        "sku": "SKU-3",
        "quantity": "1",
        "unit_price": "50.00",
        "line_total": "50.00",
        "received_at": "2026-08-20T10:30:00Z",
    },
    {
        "order_pk": "o-003",
        "product_id": "P-03",
        "sku": "SKU-4",
        "quantity": "2",
        "unit_price": "60.00",
        "line_total": "120.00",
        "received_at": "2026-09-01T08:15:00Z",
    },
]

TAX_COLUMNS = [
    "order_pk",
    "external_order_id",
    "currency",
    "subtotal",
    "shipping_total",
    "discount_total",
    "tax_total",
    "total",
    "missing_reason",
    "value_is_zero",
]
TAX = [
    {
        "order_pk": "o-001",
        "external_order_id": "WC-1001",
        "currency": "USD",
        "subtotal": "90.00",
        "shipping_total": "5.00",
        "discount_total": "0.00",
        "tax_total": "8.00",
        "total": "103.00",
    },
    {
        "order_pk": "o-002",
        "external_order_id": "WC-1002",
        "currency": "USD",
        "subtotal": "50.00",
        "shipping_total": "0.00",
        "discount_total": "5.00",
        "tax_total": "4.50",
        "total": "49.50",
    },
    {
        "order_pk": "o-003",
        "external_order_id": "WC-1003",
        "currency": "USD",
        "subtotal": "120.00",
        "shipping_total": "12.00",
        "discount_total": "0.00",
        "tax_total": "0.00",
        "total": "132.00",
    },
]


def build() -> None:
    _dump("orders.csv", ORDER_COLUMNS, ORDERS)
    _dump("orders_lines.csv", LINE_COLUMNS, LINES)
    _dump("tax.csv", TAX_COLUMNS, TAX)
    _dump("cost_snapshots.csv", SNAPSHOT_COLUMNS, SNAPSHOTS)
    _dump("cost_current.csv", COST_CURRENT_COLUMNS, COST_CURRENT)
    _dump("price_history.csv", PRICE_COLUMNS, PRICES)
    _dump("payments.csv", PAYMENT_COLUMNS, PAYMENTS)
    _dump("refunds.csv", REFUND_COLUMNS, REFUNDS)
    _dump("shipments.csv", SHIPMENT_COLUMNS, SHIPMENTS)
    _dump("logistics_events.csv", EVENT_COLUMNS, EVENTS)
    _dump("campaigns.csv", CAMPAIGN_COLUMNS, CAMPAIGNS)
    _dump("order_marketing.csv", MARKETING_COLUMNS, MARKETING)


if __name__ == "__main__":
    build()
    print(f"synthetic fixtures written to {RAW}")
