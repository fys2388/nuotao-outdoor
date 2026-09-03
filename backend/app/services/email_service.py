"""
邮件通知服务
支持订单确认、发货通知、退款通知等邮件发送
支持 SMTP 真实发送和模拟发送（本地开发）
"""
from __future__ import annotations

import json
import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# 邮件存储目录（模拟发送时保存邮件内容）
EMAIL_STORAGE_DIR = Path("data/emails")
EMAIL_STORAGE_DIR.mkdir(parents=True, exist_ok=True)


class EmailService:
    """邮件服务"""

    def __init__(self):
        self.settings = get_settings()
        self.smtp_host = getattr(self.settings, "smtp_host", None)
        self.smtp_port = getattr(self.settings, "smtp_port", 587)
        self.smtp_username = getattr(self.settings, "smtp_username", None)
        self.smtp_password = getattr(self.settings, "smtp_password", None)
        self.from_email = getattr(self.settings, "from_email", "noreply@nuotaooutdoor.com")
        self.from_name = getattr(self.settings, "from_name", "Nuotao Outdoor")

        # 判断是否使用模拟发送
        self.use_mock = not all([
            self.smtp_host,
            self.smtp_username,
            self.smtp_password,
        ])

        if self.use_mock:
            logger.info("Email service running in MOCK mode (SMTP not configured)")
        else:
            logger.info("Email service running in SMTP mode: host=%s, port=%d", self.smtp_host, self.smtp_port)

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str | None = None,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        发送邮件

        Args:
            to_email: 收件人邮箱
            subject: 邮件主题
            html_content: HTML 内容
            text_content: 纯文本内容（可选）
            cc: 抄送
            bcc: 密送
            metadata: 元数据

        Returns:
            发送结果
        """
        start_time = datetime.utcnow()
        email_id = f"EMAIL-{int(start_time.timestamp())}-{to_email.split('@')[0][:8].upper()}"

        result = {
            "email_id": email_id,
            "to": to_email,
            "subject": subject,
            "from": f"{self.from_name} <{self.from_email}>",
            "sent_at": start_time.isoformat(),
            "mode": "mock" if self.use_mock else "smtp",
            "success": False,
            "metadata": metadata or {},
        }

        try:
            if self.use_mock:
                # 模拟发送：保存到文件
                await self._mock_send(email_id, to_email, subject, html_content, text_content, metadata)
                result["success"] = True
                result["mock_file"] = str(EMAIL_STORAGE_DIR / f"{email_id}.json")
                logger.info("Mock email sent: id=%s, to=%s, subject=%s", email_id, to_email, subject)
            else:
                # 真实 SMTP 发送
                await self._smtp_send(to_email, subject, html_content, text_content, cc, bcc)
                result["success"] = True
                logger.info("SMTP email sent: id=%s, to=%s, subject=%s", email_id, to_email, subject)

        except Exception as e:
            result["error"] = str(e)
            logger.exception("Email send failed: id=%s, to=%s, error=%s", email_id, to_email, str(e))

        # 计算发送时间
        result["duration_ms"] = int((datetime.utcnow() - start_time).total_seconds() * 1000)

        return result

    async def _mock_send(
        self,
        email_id: str,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str | None,
        metadata: dict[str, Any] | None,
    ) -> None:
        """模拟发送：保存到文件"""
        email_data = {
            "email_id": email_id,
            "to": to_email,
            "from": f"{self.from_name} <{self.from_email}>",
            "subject": subject,
            "html_content": html_content,
            "text_content": text_content,
            "metadata": metadata or {},
            "sent_at": datetime.utcnow().isoformat(),
        }

        file_path = EMAIL_STORAGE_DIR / f"{email_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(email_data, f, ensure_ascii=False, indent=2)

    async def _smtp_send(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: str | None,
        cc: list[str] | None,
        bcc: list[str] | None,
    ) -> None:
        """真实 SMTP 发送"""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{self.from_name} <{self.from_email}>"
        msg["To"] = to_email

        if cc:
            msg["Cc"] = ", ".join(cc)
        if bcc:
            msg["Bcc"] = ", ".join(bcc)

        if text_content:
            msg.attach(MIMEText(text_content, "plain", "utf-8"))
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        recipients = [to_email]
        if cc:
            recipients.extend(cc)
        if bcc:
            recipients.extend(bcc)

        with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=30) as server:
            server.starttls()
            server.login(self.smtp_username, self.smtp_password)
            server.sendmail(self.from_email, recipients, msg.as_string())


# ============================================
# 邮件模板
# ============================================

def render_order_confirmation_email(order: dict[str, Any]) -> tuple[str, str, str]:
    """
    渲染订单确认邮件

    Returns:
        (subject, html_content, text_content)
    """
    order_id = order.get("id", "N/A")
    order_number = order.get("number", order_id)
    total = order.get("total", "0.00")
    currency = order.get("currency", "USD")
    status = order.get("status", "pending")
    date_created = order.get("date_created", datetime.utcnow().isoformat())

    # 订单商品
    line_items = order.get("line_items", [])
    items_html = ""
    items_text = ""
    for item in line_items:
        name = item.get("name", "Unknown")
        quantity = item.get("quantity", 1)
        price = item.get("price", item.get("unit_price", "0.00"))
        total_item = item.get("total", "0.00")
        items_html += f"""
        <tr>
            <td style="padding: 10px; border-bottom: 1px solid #eee;">{name}</td>
            <td style="padding: 10px; border-bottom: 1px solid #eee; text-align: center;">{quantity}</td>
            <td style="padding: 10px; border-bottom: 1px solid #eee; text-align: right;">{currency} {price}</td>
            <td style="padding: 10px; border-bottom: 1px solid #eee; text-align: right;">{currency} {total_item}</td>
        </tr>"""
        items_text += f"- {name} x{quantity}: {currency} {total_item}\n"

    subject = f"Order Confirmation - #{order_number}"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: #2c3e50; color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0; }}
            .content {{ padding: 20px; background: #f9f9f9; }}
            .order-details {{ background: white; padding: 20px; border-radius: 5px; margin-top: 20px; }}
            table {{ width: 100%; border-collapse: collapse; }}
            th {{ background: #2c3e50; color: white; padding: 10px; text-align: left; }}
            .total {{ font-size: 18px; font-weight: bold; text-align: right; margin-top: 20px; }}
            .footer {{ text-align: center; padding: 20px; color: #999; font-size: 12px; }}
            .btn {{ display: inline-block; background: #3498db; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-top: 20px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Nuotao Outdoor</h1>
            <p>Your Adventure Starts Here</p>
        </div>
        <div class="content">
            <h2>Thank You for Your Order!</h2>
            <p>Dear Customer,</p>
            <p>We've received your order and it's being processed. Here are your order details:</p>

            <div class="order-details">
                <h3>Order #{order_number}</h3>
                <p><strong>Date:</strong> {date_created}</p>
                <p><strong>Status:</strong> {status.capitalize()}</p>

                <table>
                    <thead>
                        <tr>
                            <th>Product</th>
                            <th>Qty</th>
                            <th>Price</th>
                            <th>Total</th>
                        </tr>
                    </thead>
                    <tbody>
                        {items_html}
                    </tbody>
                </table>

                <div class="total">
                    Order Total: {currency} {total}
                </div>
            </div>

            <p>You will receive another email when your order ships with tracking information.</p>
            <p>If you have any questions, please contact our customer service at support@nuotaooutdoor.com.</p>

            <a href="https://nuotaooutdoor.com/my-account/orders/{order_id}" class="btn">View Your Order</a>
        </div>
        <div class="footer">
            <p>© 2026 Nuotao Outdoor. All rights reserved.</p>
            <p>123 Outdoor Street, Adventure City, AC 12345</p>
        </div>
    </body>
    </html>
    """

    text_content = f"""
NUOTAO OUTDOOR - ORDER CONFIRMATION
=====================================

Thank you for your order!

Order #{order_number}
Date: {date_created}
Status: {status.capitalize()}

Order Items:
{items_text}
Order Total: {currency} {total}

You will receive another email when your order ships with tracking information.

If you have any questions, please contact our customer service at support@nuotaooutdoor.com.

© 2026 Nuotao Outdoor. All rights reserved.
    """

    return subject, html_content, text_content


def render_shipping_confirmation_email(order: dict[str, Any], tracking_info: dict[str, Any] | None = None) -> tuple[str, str, str]:
    """
    渲染发货确认邮件

    Returns:
        (subject, html_content, text_content)
    """
    order_id = order.get("id", "N/A")
    order_number = order.get("number", order_id)
    total = order.get("total", "0.00")
    currency = order.get("currency", "USD")

    tracking_number = tracking_info.get("tracking_number", "N/A") if tracking_info else "N/A"
    tracking_url = tracking_info.get("tracking_url", "") if tracking_info else ""
    carrier = tracking_info.get("carrier", "Standard Shipping") if tracking_info else "Standard Shipping"
    estimated_delivery = tracking_info.get("estimated_delivery", "7-14 business days") if tracking_info else "7-14 business days"

    subject = f"Your Order #{order_number} Has Shipped!"

    tracking_link_html = f'<a href="{tracking_url}" class="btn">Track Your Package</a>' if tracking_url else f'<p><strong>Tracking Number:</strong> {tracking_number}</p>'

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background: #27ae60; color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0; }}
            .content {{ padding: 20px; background: #f9f9f9; }}
            .shipping-details {{ background: white; padding: 20px; border-radius: 5px; margin-top: 20px; }}
            .btn {{ display: inline-block; background: #3498db; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; margin-top: 20px; }}
            .footer {{ text-align: center; padding: 20px; color: #999; font-size: 12px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>📦 Your Order Has Shipped!</h1>
        </div>
        <div class="content">
            <h2>Great News!</h2>
            <p>Dear Customer,</p>
            <p>Your order #{order_number} has been shipped and is on its way to you!</p>

            <div class="shipping-details">
                <h3>Shipping Details</h3>
                <p><strong>Carrier:</strong> {carrier}</p>
                <p><strong>Tracking Number:</strong> {tracking_number}</p>
                <p><strong>Estimated Delivery:</strong> {estimated_delivery}</p>
                {tracking_link_html}
            </div>

            <p style="margin-top: 20px;">If you have any questions about your shipment, please contact our customer service at support@nuotaooutdoor.com.</p>

            <p>Thank you for choosing Nuotao Outdoor. We hope you enjoy your adventure gear!</p>
        </div>
        <div class="footer">
            <p>© 2026 Nuotao Outdoor. All rights reserved.</p>
        </div>
    </body>
    </html>
    """

    text_content = f"""
NUOTAO OUTDOOR - YOUR ORDER HAS SHIPPED!
==========================================

Great News!

Your order #{order_number} has been shipped and is on its way to you!

Shipping Details:
- Carrier: {carrier}
- Tracking Number: {tracking_number}
- Estimated Delivery: {estimated_delivery}
{f"- Tracking URL: {tracking_url}" if tracking_url else ""}

If you have any questions about your shipment, please contact our customer service at support@nuotaooutdoor.com.

Thank you for choosing Nuotao Outdoor!

© 2026 Nuotao Outdoor. All rights reserved.
    """

    return subject, html_content, text_content


def render_order_cancelled_email(order: dict[str, Any]) -> tuple[str, str, str]:
    """渲染订单取消邮件"""
    order_id = order.get("id", "N/A")
    order_number = order.get("number", order_id)
    total = order.get("total", "0.00")
    currency = order.get("currency", "USD")

    subject = f"Order #{order_number} Cancelled"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head><meta charset="utf-8"><style>body {{ font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; }} .header {{ background: #e74c3c; color: white; padding: 20px; text-align: center; }} .content {{ padding: 20px; background: #f9f9f9; }} .footer {{ text-align: center; padding: 20px; color: #999; font-size: 12px; }}</style></head>
    <body>
        <div class="header"><h1>Order Cancelled</h1></div>
        <div class="content">
            <h2>Order #{order_number} Has Been Cancelled</h2>
            <p>Dear Customer,</p>
            <p>Your order #{order_number} has been cancelled. If you did not request this cancellation, please contact our customer service immediately.</p>
            <p><strong>Order Total:</strong> {currency} {total}</p>
            <p>If payment was already processed, a refund will be issued within 5-7 business days.</p>
            <p>For any questions, please contact support@nuotaooutdoor.com.</p>
        </div>
        <div class="footer"><p>© 2026 Nuotao Outdoor. All rights reserved.</p></div>
    </body>
    </html>
    """

    text_content = f"""
ORDER #{order_number} CANCELLED
================================

Your order #{order_number} has been cancelled.

Order Total: {currency} {total}

If payment was already processed, a refund will be issued within 5-7 business days.

For any questions, please contact support@nuotaooutdoor.com.

© 2026 Nuotao Outdoor.
    """

    return subject, html_content, text_content


# 全局邮件服务实例
_email_service: EmailService | None = None


def get_email_service() -> EmailService:
    """获取邮件服务单例"""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service
