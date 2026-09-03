"""Customer service template service (M6): multi-language response templates.

Provides pre-built, brand-aligned response templates for common customer
service scenarios (shipping delays, returns, refunds, product questions,
etc.) across multiple languages. Templates are deterministic — no LLM
call needed for standard replies, ensuring consistency and zero cost.

Agent access: Customer Manager uses ``get_customer_template`` and
``generate_customer_response`` via whitelist tools.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from uuid import UUID

from app.agents.generic_agent import run_generic_agent

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

DEFAULT_WORKSPACE_ID = UUID("00000000-0000-0000-0000-000000000001")

AGENT_ID = "customer_template"
AGENT_NAME = "Customer Template Generator"
PROMPT_NAME = "CUSTOMER_RESPONSE_V1"
TRIGGER = "api:customer:response"

# Supported languages for customer service templates.
SUPPORTED_LANGUAGES: tuple[str, ...] = ("en", "de", "fr", "es", "it", "zh")

LANGUAGE_NAMES: dict[str, str] = {
    "en": "English",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "zh": "Chinese",
}

# Template categories.
TEMPLATE_CATEGORIES: tuple[str, ...] = (
    "shipping_delay",
    "shipping_update",
    "return_request",
    "refund_processing",
    "product_question",
    "size_guide",
    "order_confirmation",
    "delivery_confirmation",
    "damaged_item",
    "wrong_item",
    "payment_issue",
    "account_help",
    "general_inquiry",
    "apology",
    "follow_up",
)

# Output schema for LLM-generated custom responses.
CUSTOMER_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "subject": {"type": "string", "description": "Email subject line"},
        "greeting": {"type": "string", "description": "Personalized greeting"},
        "body": {"type": "string", "description": "Main response body"},
        "closing": {"type": "string", "description": "Closing and signature"},
        "tone": {"type": "string", "enum": ["empathetic", "professional", "apologetic", "friendly"]},
        "next_steps": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Clear next steps for the customer",
        },
        "escalation_needed": {"type": "boolean", "description": "Whether this should be escalated to a human"},
    },
    "required": ["subject", "greeting", "body", "closing", "tone"],
}


class CustomerTemplateError(Exception):
    """Raised when template generation fails."""


# ============================================
# Deterministic template library
# ============================================

# Template strings use {placeholders} for variable substitution.
_TEMPLATES: dict[str, dict[str, dict[str, str]]] = {
    "shipping_delay": {
        "en": {
            "subject": "Update on your order {order_id}",
            "body": (
                "Dear {customer_name},\n\n"
                "Thank you for your patience. We wanted to update you on your order {order_id}. "
                "Due to {reason}, your delivery is slightly delayed. "
                "We expect it to arrive by {expected_date}.\n\n"
                "We apologize for the inconvenience and appreciate your understanding.\n\n"
                "Best regards,\nNuotao Outdoor Customer Service"
            ),
        },
        "de": {
            "subject": "Aktualisierung zu Ihrer Bestellung {order_id}",
            "body": (
                "Sehr geehrte/r {customer_name},\n\n"
                "Vielen Dank für Ihre Geduld. Wir möchten Sie über Ihre Bestellung {order_id} "
                "auf dem Laufenden halten. Aufgrund von {reason} verzögert sich die Lieferung "
                "geringfügig. Wir erwarten die Ankunft bis zum {expected_date}.\n\n"
                "Wir entschuldigen uns für die Unannehmlichkeiten und danken für Ihr Verständnis.\n\n"
                "Mit freundlichen Grüßen\nNuotao Outdoor Kundenservice"
            ),
        },
        "fr": {
            "subject": "Mise à jour de votre commande {order_id}",
            "body": (
                "Cher/Chère {customer_name},\n\n"
                "Merci pour votre patience. Nous souhaitons vous informer de l'état de votre "
                "commande {order_id}. En raison de {reason}, la livraison est légèrement retardée. "
                "Nous prévoyons une livraison d'ici le {expected_date}.\n\n"
                "Nous nous excusons pour ce désagrément et vous remercions de votre compréhension.\n\n"
                "Cordialement,\nService client Nuotao Outdoor"
            ),
        },
    },
    "return_request": {
        "en": {
            "subject": "Return request for order {order_id}",
            "body": (
                "Dear {customer_name},\n\n"
                "Thank you for contacting us about returning item(s) from order {order_id}. "
                "We're sorry the product didn't meet your expectations.\n\n"
                "To initiate your return, please follow these steps:\n"
                "1. Reply to this email with the item(s) you wish to return and the reason.\n"
                "2. We will provide a prepaid return label within 24 hours.\n"
                "3. Ship the item(s) back within 14 days.\n\n"
                "Once we receive and inspect the items, your refund will be processed within 5-7 business days.\n\n"
                "Best regards,\nNuotao Outdoor Customer Service"
            ),
        },
        "de": {
            "subject": "Rückgabeanfrage für Bestellung {order_id}",
            "body": (
                "Sehr geehrte/r {customer_name},\n\n"
                "Vielen Dank für Ihre Kontaktaufnahme bezüglich der Rückgabe von Artikeln aus "
                "Ihrer Bestellung {order_id}. Es tut uns leid, dass das Produkt nicht Ihren "
                "Erwartungen entsprochen hat.\n\n"
                "So initiieren Sie Ihre Rückgabe:\n"
                "1. Antworten Sie auf diese E-Mail mit den zurückzugebenden Artikeln und dem Grund.\n"
                "2. Wir senden Ihnen innerhalb von 24 Stunden ein vorfrankiertes Rücksendelabel.\n"
                "3. Versenden Sie die Artikel innerhalb von 14 Tagen zurück.\n\n"
                "Nach Erhalt und Prüfung der Artikel wird Ihre Erstattung innerhalb von 5-7 Werktagen bearbeitet.\n\n"
                "Mit freundlichen Grüßen\nNuotao Outdoor Kundenservice"
            ),
        },
    },
    "refund_processing": {
        "en": {
            "subject": "Your refund for order {order_id} has been processed",
            "body": (
                "Dear {customer_name},\n\n"
                "Good news! We've received your returned item(s) from order {order_id} and "
                "your refund of {refund_amount} has been processed.\n\n"
                "The refund will appear on your original payment method within 5-10 business days, "
                "depending on your bank or card issuer.\n\n"
                "Thank you for shopping with Nuotao Outdoor. We hope to serve you again soon.\n\n"
                "Best regards,\nNuotao Outdoor Customer Service"
            ),
        },
    },
    "product_question": {
        "en": {
            "subject": "Re: Your question about {product_name}",
            "body": (
                "Dear {customer_name},\n\n"
                "Thank you for your question about the {product_name}.\n\n"
                "{answer}\n\n"
                "If you have any further questions, please don't hesitate to reach out.\n\n"
                "Best regards,\nNuotao Outdoor Customer Service"
            ),
        },
    },
    "damaged_item": {
        "en": {
            "subject": "We're sorry about your damaged order {order_id}",
            "body": (
                "Dear {customer_name},\n\n"
                "We're truly sorry to hear that your order {order_id} arrived damaged. "
                "This is not the experience we want for our customers.\n\n"
                "To resolve this quickly, please:\n"
                "1. Reply with photos of the damaged item and packaging.\n"
                "2. We will arrange a replacement shipment at no cost to you, or process a full refund.\n\n"
                "We appreciate your patience while we make this right.\n\n"
                "Sincerely,\nNuotao Outdoor Customer Service"
            ),
        },
    },
    "order_confirmation": {
        "en": {
            "subject": "Order confirmation: {order_id}",
            "body": (
                "Dear {customer_name},\n\n"
                "Thank you for your order! We've received your order {order_id} and it's "
                "now being processed.\n\n"
                "Order summary:\n{order_summary}\n\n"
                "You will receive a shipping confirmation email with tracking information "
                "once your order ships.\n\n"
                "Thank you for choosing Nuotao Outdoor!\n\n"
                "Best regards,\nNuotao Outdoor Team"
            ),
        },
    },
    "apology": {
        "en": {
            "subject": "Our sincere apologies",
            "body": (
                "Dear {customer_name},\n\n"
                "We want to sincerely apologize for {issue}. This falls short of the "
                "standard we strive for, and we take full responsibility.\n\n"
                "To make things right, we have {resolution}.\n\n"
                "We value you as a customer and hope to earn back your trust.\n\n"
                "Sincerely,\nNuotao Outdoor Customer Service"
            ),
        },
    },
}


def get_customer_template_status() -> dict[str, Any]:
    """Return service status, supported languages, and template categories."""
    return {
        "service": "customer_template",
        "status": "operational",
        "supported_languages": list(SUPPORTED_LANGUAGES),
        "language_names": LANGUAGE_NAMES,
        "template_categories": list(TEMPLATE_CATEGORIES),
        "available_templates": {
            cat: list(_TEMPLATES.get(cat, {}).keys())
            for cat in TEMPLATE_CATEGORIES
            if cat in _TEMPLATES
        },
        "agent_id": AGENT_ID,
        "prompt_name": PROMPT_NAME,
    }


def get_customer_template(
    category: str,
    language: str = "en",
    variables: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Retrieve and fill a deterministic customer service template.

    Args:
        category: template category (e.g. "shipping_delay", "return_request")
        language: target language code
        variables: dict of placeholder values to substitute

    Returns:
        Filled template dict with subject and body.
    """
    if category not in TEMPLATE_CATEGORIES:
        raise CustomerTemplateError(
            f"unknown template category: {category}; must be one of {TEMPLATE_CATEGORIES}"
        )
    if language not in SUPPORTED_LANGUAGES:
        raise CustomerTemplateError(
            f"unsupported language: {language}; must be one of {SUPPORTED_LANGUAGES}"
        )

    lang_templates = _TEMPLATES.get(category, {})
    template = lang_templates.get(language) or lang_templates.get("en")

    if not template:
        raise CustomerTemplateError(
            f"no template available for category={category}, language={language} "
            f"(and no English fallback)"
        )

    vars_dict = variables or {}
    filled = {
        "category": category,
        "language": language,
        "language_name": LANGUAGE_NAMES.get(language, language),
        "subject": template["subject"].format(**vars_dict),
        "body": template["body"].format(**vars_dict),
        "is_fallback": language not in lang_templates,
    }
    return filled


def list_available_templates(language: str | None = None) -> dict[str, Any]:
    """List all available templates, optionally filtered by language."""
    result: dict[str, Any] = {}
    for category in TEMPLATE_CATEGORIES:
        langs = list(_TEMPLATES.get(category, {}).keys())
        if language:
            if language in langs or "en" in langs:
                result[category] = {
                    "available_languages": langs,
                    "has_native": language in langs,
                    "has_english_fallback": "en" in langs,
                }
        else:
            result[category] = {"available_languages": langs}
    return {"templates": result, "total_categories": len(TEMPLATE_CATEGORIES)}


async def generate_customer_response(
    session: AsyncSession,
    *,
    workspace_id: UUID | None = None,
    customer_name: str,
    customer_message: str,
    order_id: str | None = None,
    product_name: str | None = None,
    language: str = "en",
    tone: str = "empathetic",
    context: dict[str, Any] | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """Generate a custom customer service response using the LLM gateway.

    Use this for non-standard inquiries that don't fit a deterministic template.
    The LLM output is validated against the response schema; failures raise
    CustomerTemplateError (the caller should fall back to a template).
    """
    if language not in SUPPORTED_LANGUAGES:
        raise CustomerTemplateError(
            f"unsupported language: {language}; must be one of {SUPPORTED_LANGUAGES}"
        )

    ws = workspace_id or DEFAULT_WORKSPACE_ID

    agent_context: dict[str, Any] = {
        "customer_name": customer_name,
        "customer_message": customer_message,
        "order_id": order_id,
        "product_name": product_name,
        "language": language,
        "language_name": LANGUAGE_NAMES.get(language, language),
        "tone": tone,
        "brand": "Nuotao Outdoor",
        "market": "outdoor gear DTC",
    }
    if context:
        agent_context["additional_context"] = context

    result = await run_generic_agent(
        session,
        workspace_id=ws,
        agent_id=AGENT_ID,
        agent_name=AGENT_NAME,
        trigger=TRIGGER,
        context=agent_context,
        prompt_name=PROMPT_NAME,
        output_schema=CUSTOMER_RESPONSE_SCHEMA,
        system_instruction=(
            f"You are a professional customer service representative for Nuotao Outdoor, "
            f"an outdoor gear DTC brand. Respond to the customer in {LANGUAGE_NAMES.get(language, language)}. "
            f"Tone: {tone}. Be empathetic, clear, and solution-oriented. "
            f"Never promise refunds or discounts beyond standard policy. "
            f"Respond ONLY with a valid JSON object matching the schema."
        ),
        temperature=0.3,
        task_type="customer_response",
        trace_id=trace_id,
    )

    if result.error or not result.output:
        raise CustomerTemplateError(f"response generation failed: {result.error or 'no output'}")

    return {
        "customer_name": customer_name,
        "language": language,
        "response": result.output,
        "agent_run_id": str(result.agent_run.id) if result.agent_run else None,
    }
