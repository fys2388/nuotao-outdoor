"""
支付网关集成
支持Stripe、PayPal，以及通过WooCommerce API获取支付状态
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 支付网关配置（从环境变量读取）
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID", "")
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET", "")
PAYPAL_MODE = os.getenv("PAYPAL_MODE", "sandbox")  # sandbox or live

PAYMENT_GATEWAY = os.getenv("PAYMENT_GATEWAY", "woocommerce")  # stripe/paypal/woocommerce


def get_payment_config() -> dict[str, Any]:
    """获取支付网关配置状态"""
    return {
        "active_gateway": PAYMENT_GATEWAY,
        "stripe": {
            "configured": bool(STRIPE_SECRET_KEY),
            "publishable_key": STRIPE_PUBLISHABLE_KEY[:8] + "..." if STRIPE_PUBLISHABLE_KEY else "",
            "webhook_configured": bool(STRIPE_WEBHOOK_SECRET),
        },
        "paypal": {
            "configured": bool(PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET),
            "client_id": PAYPAL_CLIENT_ID[:8] + "..." if PAYPAL_CLIENT_ID else "",
            "mode": PAYPAL_MODE,
        },
        "woocommerce": {
            "configured": True,
            "description": "通过WooCommerce API获取支付状态",
        },
        "supported_currencies": ["USD", "EUR", "GBP", "CNY"],
        "supported_methods": ["credit_card", "paypal", "apple_pay", "google_pay"],
    }


def create_payment_intent(
    amount: float,
    currency: str = "USD",
    order_id: str = "",
    customer_email: str = "",
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """创建支付意图（Stripe模式）"""
    if not STRIPE_SECRET_KEY:
        return {
            "success": False,
            "error": "Stripe未配置，请设置STRIPE_SECRET_KEY环境变量",
            "action_required": "配置Stripe API密钥",
        }

    try:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY

        intent = stripe.PaymentIntent.create(
            amount=int(amount * 100),  # 转换为分
            currency=currency.lower(),
            metadata={
                "order_id": order_id,
                "customer_email": customer_email,
                **(metadata or {}),
            },
        )

        return {
            "success": True,
            "payment_intent_id": intent.id,
            "client_secret": intent.client_secret,
            "amount": amount,
            "currency": currency,
            "status": intent.status,
        }
    except ImportError:
        return {
            "success": False,
            "error": "stripe库未安装，请运行: pip install stripe",
        }
    except Exception as e:
        logger.error("Create payment intent failed: %s", str(e))
        return {
            "success": False,
            "error": str(e),
        }


def create_paypal_order(
    amount: float,
    currency: str = "USD",
    order_id: str = "",
    return_url: str = "",
    cancel_url: str = "",
) -> dict[str, Any]:
    """创建PayPal订单"""
    if not PAYPAL_CLIENT_ID or not PAYPAL_CLIENT_SECRET:
        return {
            "success": False,
            "error": "PayPal未配置，请设置PAYPAL_CLIENT_ID和PAYPAL_CLIENT_SECRET环境变量",
            "action_required": "配置PayPal API密钥",
        }

    try:
        import requests

        base_url = "https://api-m.sandbox.paypal.com" if PAYPAL_MODE == "sandbox" else "https://api-m.paypal.com"

        # 获取access token
        auth_response = requests.post(
            f"{base_url}/v1/oauth2/token",
            auth=(PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET),
            data={"grant_type": "client_credentials"},
            timeout=30,
        )
        auth_response.raise_for_status()
        access_token = auth_response.json()["access_token"]

        # 创建订单
        order_response = requests.post(
            f"{base_url}/v2/checkout/orders",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={
                "intent": "CAPTURE",
                "purchase_units": [{
                    "amount": {
                        "currency_code": currency,
                        "value": str(amount),
                    },
                    "custom_id": order_id,
                }],
                "application_context": {
                    "return_url": return_url,
                    "cancel_url": cancel_url,
                },
            },
            timeout=30,
        )
        order_response.raise_for_status()
        order_data = order_response.json()

        return {
            "success": True,
            "order_id": order_data["id"],
            "status": order_data["status"],
            "approval_url": next(
                (link["href"] for link in order_data["links"] if link["rel"] == "approve"),
                None,
            ),
        }
    except Exception as e:
        logger.error("Create PayPal order failed: %s", str(e))
        return {
            "success": False,
            "error": str(e),
        }


def verify_stripe_webhook(payload: bytes, signature: str) -> dict[str, Any]:
    """验证Stripe Webhook"""
    if not STRIPE_WEBHOOK_SECRET:
        return {
            "success": False,
            "error": "Stripe Webhook未配置",
        }

    try:
        import stripe
        event = stripe.Webhook.construct_event(
            payload, signature, STRIPE_WEBHOOK_SECRET
        )
        return {
            "success": True,
            "event_type": event["type"],
            "data": event["data"]["object"],
        }
    except Exception as e:
        logger.error("Verify Stripe webhook failed: %s", str(e))
        return {
            "success": False,
            "error": str(e),
        }


def get_payment_status(order_id: str) -> dict[str, Any]:
    """获取订单支付状态（通过WooCommerce API）"""
    try:
        from app.integrations.woocommerce import get_woocommerce_order

        order = get_woocommerce_order(order_id)
        if order:
            return {
                "success": True,
                "order_id": order_id,
                "status": order.get("status", "unknown"),
                "payment_method": order.get("payment_method", ""),
                "payment_method_title": order.get("payment_method_title", ""),
                "total": order.get("total", "0"),
                "currency": order.get("currency", "USD"),
                "date_paid": order.get("date_paid", ""),
            }
    except Exception as e:
        logger.error("Get payment status failed: %s", str(e))

    return {
        "success": False,
        "order_id": order_id,
        "error": "无法获取支付状态，请检查WooCommerce连接",
    }
