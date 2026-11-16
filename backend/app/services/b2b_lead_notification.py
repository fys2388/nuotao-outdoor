"""B2B lead enquiry notification (M2.5.5).

On successful lead persistence we notify the configured internal B2B owner /
business inbox. Design rules from the spec:

- Persist the lead FIRST; notification happens after the business fact is
  committed and must never roll it back.
- Reuse the existing ``email_service`` (SMTP when configured, mock otherwise).
- A notification failure is logged as a ``b2b_lead.notification_failed`` event
  and is retryable; it does NOT surface as a submission failure to the enquirer.
- The email contains the lead reference number and a link to the
  **authenticated** internal AI OS console lead detail page. It must never
  expose the private lead to unauthenticated recipients or URLs.
- No marketing content; no invented recipient addresses. If no recipient is
  configured, notification is skipped gracefully (a configuration gap, not a
  send failure).
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.services import event_service

logger = logging.getLogger(__name__)


def _recipients() -> list[str]:
    raw = (settings.b2b_lead_notify_emails or "").strip()
    if not raw:
        return []
    return [e.strip().lower() for e in raw.split(",") if e.strip()]


def _lead_detail_url(lead_id: UUID) -> str:
    base = (settings.console_base_url or "").rstrip("/")
    return f"{base}/b2b/leads/{lead_id}"


async def notify_new_lead(db: AsyncSession, lead) -> dict[str, Any]:
    """Notify internal B2B owner(s) of a new public enquiry.

    Returns a result dict describing the outcome. Never raises: notification
    failure must not roll back the persisted lead.
    """
    recipients = _recipients()
    if not recipients:
        logger.info(
            "B2B lead notification skipped (no recipient configured): %s",
            lead.reference_number,
        )
        return {"skipped": True, "reason": "no_recipient_configured", "recipients": []}

    # Lazy import to avoid a hard dependency cycle at module load.
    from app.services.email_service import get_email_service

    subject = f"[B2B Lead] New enquiry {lead.reference_number} - {lead.company_name}"
    detail_url = _lead_detail_url(lead.id)
    text_content = (
        f"A new B2B enquiry was submitted from the public website.\n\n"
        f"Reference: {lead.reference_number}\n"
        f"Company: {lead.company_name}\n"
        f"Country: {lead.country}\n"
        f"Business type: {lead.business_type}\n\n"
        f"Open the authenticated AI OS console to action it:\n{detail_url}\n\n"
        f"(Full contact details and enquiry message are available in the console "
        f"after sign-in; they are intentionally not included in this email.)"
    )
    html_content = (
        "<p>A new B2B enquiry was submitted from the public website.</p>"
        f"<ul><li><b>Reference:</b> {lead.reference_number}</li>"
        f"<li><b>Company:</b> {lead.company_name}</li>"
        f"<li><b>Country:</b> {lead.country}</li>"
        f"<li><b>Business type:</b> {lead.business_type}</li></ul>"
        f'<p><a href="{detail_url}">Open in AI OS console (sign-in required)</a></p>'
        "<p style=\"color:#666\">Full contact details and the enquiry message are "
        "available in the console after sign-in and are intentionally not emailed.</p>"
    )

    results: list[dict[str, Any]] = []
    any_success = False
    email_service = get_email_service()
    for to_email in recipients:
        try:
            result = await email_service.send_email(
                to_email=to_email,
                subject=subject,
                html_content=html_content,
                text_content=text_content,
                metadata={"lead_id": str(lead.id), "reference_number": lead.reference_number},
            )
        except Exception as exc:  # never propagate: notification must not roll back the lead
            result = {"to": to_email, "success": False, "error": str(exc)}
        results.append(result)
        if result.get("success"):
            any_success = True

    if not any_success:
        # Append-only audit event; retryable. Contains reference only, no PII.
        await event_service.create_event(
            db,
            workspace_id=lead.workspace_id,
            event_type="b2b_lead.notification_failed",
            entity_type="b2b_lead",
            entity_id=str(lead.id),
            payload={
                "reference_number": lead.reference_number,
                "recipients": recipients,
                "retryable": True,
            },
        )

    return {
        "skipped": False,
        "success": any_success,
        "recipients": recipients,
        "results": results,
    }