"""Unit tests for M6 extra modules: listing localization + customer templates."""

from __future__ import annotations

import pytest
from uuid import UUID

from app.services.listing_localization_service import (
    ListingLocalizationError,
    get_listing_localization_status,
    SUPPORTED_LANGUAGES,
    LANGUAGE_NAMES,
)
from app.services.customer_template_service import (
    CustomerTemplateError,
    get_customer_template,
    get_customer_template_status,
    list_available_templates,
    SUPPORTED_LANGUAGES as CS_LANGUAGES,
    TEMPLATE_CATEGORIES,
)

DEFAULT_WORKSPACE = UUID("00000000-0000-0000-0000-000000000001")


# ============================================
# Listing Localization Tests
# ============================================


class TestListingLocalization:
    def test_service_status(self):
        status = get_listing_localization_status()
        assert status["service"] == "listing_localization"
        assert status["status"] == "operational"
        assert "en" in status["supported_languages"]
        assert "de" in status["supported_languages"]
        assert status["agent_id"] == "listing_localizer"

    def test_supported_languages(self):
        assert "en" in SUPPORTED_LANGUAGES
        assert "de" in SUPPORTED_LANGUAGES
        assert "fr" in SUPPORTED_LANGUAGES
        assert "es" in SUPPORTED_LANGUAGES
        assert "it" in SUPPORTED_LANGUAGES
        assert len(SUPPORTED_LANGUAGES) == 5

    def test_language_names(self):
        assert LANGUAGE_NAMES["en"] == "English"
        assert LANGUAGE_NAMES["de"] == "German"
        assert LANGUAGE_NAMES["fr"] == "French"

    @pytest.mark.asyncio
    async def test_localize_invalid_language(self, db_session):
        from app.services.listing_localization_service import localize_listing
        with pytest.raises(ListingLocalizationError, match="unsupported language"):
            await localize_listing(
                db_session,
                product_name="Test",
                source_listing={"title": "test"},
                target_language="xx",
            )


# ============================================
# Customer Template Tests
# ============================================


class TestCustomerTemplates:
    def test_service_status(self):
        status = get_customer_template_status()
        assert status["service"] == "customer_template"
        assert status["status"] == "operational"
        assert len(status["supported_languages"]) >= 5
        assert len(status["template_categories"]) == 15
        assert "shipping_delay" in status["template_categories"]
        assert "return_request" in status["template_categories"]

    def test_supported_languages(self):
        assert "en" in CS_LANGUAGES
        assert "de" in CS_LANGUAGES
        assert "zh" in CS_LANGUAGES

    def test_template_categories(self):
        assert "shipping_delay" in TEMPLATE_CATEGORIES
        assert "return_request" in TEMPLATE_CATEGORIES
        assert "refund_processing" in TEMPLATE_CATEGORIES
        assert "damaged_item" in TEMPLATE_CATEGORIES
        assert "order_confirmation" in TEMPLATE_CATEGORIES
        assert "apology" in TEMPLATE_CATEGORIES

    def test_get_template_english(self):
        result = get_customer_template(
            category="shipping_delay",
            language="en",
            variables={
                "customer_name": "John Doe",
                "order_id": "ORD-001",
                "reason": "weather conditions",
                "expected_date": "2026-09-15",
            },
        )
        assert result["category"] == "shipping_delay"
        assert result["language"] == "en"
        assert "John Doe" in result["body"]
        assert "ORD-001" in result["body"]
        assert "weather conditions" in result["body"]
        assert "2026-09-15" in result["body"]
        assert result["is_fallback"] is False

    def test_get_template_german(self):
        result = get_customer_template(
            category="shipping_delay",
            language="de",
            variables={
                "customer_name": "Hans Mueller",
                "order_id": "ORD-002",
                "reason": "Wetterbedingungen",
                "expected_date": "15.09.2026",
            },
        )
        assert result["language"] == "de"
        assert "Hans Mueller" in result["body"]
        assert "ORD-002" in result["body"]
        assert result["is_fallback"] is False

    def test_get_template_french(self):
        result = get_customer_template(
            category="shipping_delay",
            language="fr",
            variables={
                "customer_name": "Marie Dupont",
                "order_id": "ORD-003",
                "reason": "conditions météorologiques",
                "expected_date": "15/09/2026",
            },
        )
        assert result["language"] == "fr"
        assert "Marie Dupont" in result["body"]
        assert result["is_fallback"] is False

    def test_get_template_english_fallback(self):
        # refund_processing only has English, so German should fall back
        result = get_customer_template(
            category="refund_processing",
            language="de",
            variables={
                "customer_name": "Hans",
                "order_id": "ORD-100",
                "refund_amount": "€50.00",
            },
        )
        assert result["language"] == "de"
        assert result["is_fallback"] is True
        assert "Hans" in result["body"]
        assert "ORD-100" in result["body"]

    def test_get_template_return_request(self):
        result = get_customer_template(
            category="return_request",
            language="en",
            variables={"customer_name": "Jane", "order_id": "ORD-200"},
        )
        assert "Jane" in result["body"]
        assert "ORD-200" in result["body"]
        assert "return" in result["body"].lower()

    def test_get_template_damaged_item(self):
        result = get_customer_template(
            category="damaged_item",
            language="en",
            variables={"customer_name": "Bob", "order_id": "ORD-300"},
        )
        assert "Bob" in result["body"]
        assert "damaged" in result["body"].lower()

    def test_get_template_invalid_category(self):
        with pytest.raises(CustomerTemplateError, match="unknown template category"):
            get_customer_template(category="nonexistent", language="en")

    def test_get_template_invalid_language(self):
        with pytest.raises(CustomerTemplateError, match="unsupported language"):
            get_customer_template(category="shipping_delay", language="xx")

    def test_list_available_templates_all(self):
        result = list_available_templates()
        assert "templates" in result
        assert result["total_categories"] == 15
        assert "shipping_delay" in result["templates"]

    def test_list_available_templates_by_language(self):
        result = list_available_templates(language="de")
        assert "templates" in result
        # shipping_delay has German
        assert result["templates"]["shipping_delay"]["has_native"] is True
        # refund_processing only has English
        assert result["templates"]["refund_processing"]["has_native"] is False
        assert result["templates"]["refund_processing"]["has_english_fallback"] is True

    def test_template_subject_filled(self):
        result = get_customer_template(
            category="shipping_delay",
            language="en",
            variables={"customer_name": "X", "order_id": "ORD-999", "reason": "Y", "expected_date": "Z"},
        )
        assert "ORD-999" in result["subject"]

    def test_all_templates_have_english(self):
        """Every template category that exists must have an English version."""
        for category in TEMPLATE_CATEGORIES:
            # Only test categories that actually have templates defined
            result = list_available_templates(language="en")
            if category in result["templates"]:
                info = result["templates"][category]
                assert info["has_english_fallback"] is True or info["has_native"] is True
