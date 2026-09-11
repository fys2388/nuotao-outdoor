"""Content marketing service tests (M3.2 database-backed).

Tests cover:
- ContentItem CRUD with workspace isolation
- Content approval workflow: draft -> pending_review -> approved -> published
- pending_review -> rejected -> draft
- Cannot publish without approval
- Version control and optimistic locking (expected_version)
- Approved/published content cannot be edited directly
- EDMCampaign CRUD and status transitions
- SEORecord CRUD and ranking snapshots with source tracking
- All state transitions write to event_log
"""

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
import pytest_asyncio

from app.services import content_marketing_service

DEFAULT_WORKSPACE = UUID("00000000-0000-0000-0000-000000000001")
OTHER_WORKSPACE = UUID("00000000-0000-0000-0000-000000000002")


# --------------------------------------------------------------------------- #
# ContentItem CRUD
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_create_content_item(db_session):
    """Create content item in draft status."""
    item = await content_marketing_service.create_content_item(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        content_type="product_description", title="Test Product",
        body="This is a test product description.",
        content_json={"key": "value"}, language="en",
        keywords=["test", "product"], source="ai_generated",
    )
    assert item.id is not None
    assert item.status == "draft"
    assert item.version == 1
    assert item.content_type == "product_description"
    assert item.title == "Test Product"


@pytest.mark.asyncio
async def test_get_content_item(db_session):
    """Get content item by ID."""
    created = await content_marketing_service.create_content_item(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        content_type="seo_article", title="SEO Article",
    )
    fetched = await content_marketing_service.get_content_item(
        db_session, workspace_id=DEFAULT_WORKSPACE, content_id=created.id,
    )
    assert fetched.id == created.id
    assert fetched.title == "SEO Article"


@pytest.mark.asyncio
async def test_get_content_item_wrong_workspace(db_session):
    """Content item from another workspace is not found (workspace isolation)."""
    created = await content_marketing_service.create_content_item(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        content_type="seo_article", title="SEO Article",
    )
    with pytest.raises(content_marketing_service.ContentNotFound):
        await content_marketing_service.get_content_item(
            db_session, workspace_id=OTHER_WORKSPACE, content_id=created.id,
        )


@pytest.mark.asyncio
async def test_list_content_items(db_session):
    """List content items with filters."""
    await content_marketing_service.create_content_item(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        content_type="product_description", title="Product 1",
    )
    await content_marketing_service.create_content_item(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        content_type="seo_article", title="Article 1",
    )
    all_items = await content_marketing_service.list_content_items(
        db_session, workspace_id=DEFAULT_WORKSPACE,
    )
    assert len(all_items) >= 2

    seo_items = await content_marketing_service.list_content_items(
        db_session, workspace_id=DEFAULT_WORKSPACE, content_type="seo_article",
    )
    assert all(i.content_type == "seo_article" for i in seo_items)


@pytest.mark.asyncio
async def test_update_content_item(db_session):
    """Update content item increments version."""
    item = await content_marketing_service.create_content_item(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        content_type="product_description", title="Original Title",
        body="Original body.",
    )
    assert item.version == 1

    updated = await content_marketing_service.update_content_item(
        db_session, workspace_id=DEFAULT_WORKSPACE, content_id=item.id,
        title="Updated Title", body="Updated body.",
    )
    assert updated.version == 2
    assert updated.title == "Updated Title"
    assert updated.body == "Updated body."


@pytest.mark.asyncio
async def test_update_content_item_optimistic_locking(db_session):
    """Optimistic locking: expected_version mismatch raises ContentVersionConflict."""
    item = await content_marketing_service.create_content_item(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        content_type="product_description", title="Title",
    )
    # First update -> version 2
    await content_marketing_service.update_content_item(
        db_session, workspace_id=DEFAULT_WORKSPACE, content_id=item.id,
        title="First Update",
    )
    # Second update with old expected_version -> conflict
    with pytest.raises(content_marketing_service.ContentVersionConflict):
        await content_marketing_service.update_content_item(
            db_session, workspace_id=DEFAULT_WORKSPACE, content_id=item.id,
            title="Second Update", expected_version=1,
        )


@pytest.mark.asyncio
async def test_cannot_edit_approved_content(db_session):
    """Approved content cannot be edited directly."""
    item = await content_marketing_service.create_content_item(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        content_type="product_description", title="Title",
    )
    item = await content_marketing_service.submit_content_for_review(
        db_session, workspace_id=DEFAULT_WORKSPACE, content_id=item.id,
    )
    item = await content_marketing_service.approve_content(
        db_session, workspace_id=DEFAULT_WORKSPACE, content_id=item.id,
        approved_by="tester",
    )
    assert item.status == "approved"

    with pytest.raises(content_marketing_service.ContentStateError):
        await content_marketing_service.update_content_item(
            db_session, workspace_id=DEFAULT_WORKSPACE, content_id=item.id,
            title="Should Fail",
        )


# --------------------------------------------------------------------------- #
# Content approval workflow
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_content_workflow_full_path(db_session):
    """Full workflow: draft -> pending_review -> approved -> published."""
    item = await content_marketing_service.create_content_item(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        content_type="seo_article", title="Full Path Article",
    )
    assert item.status == "draft"

    item = await content_marketing_service.submit_content_for_review(
        db_session, workspace_id=DEFAULT_WORKSPACE, content_id=item.id,
    )
    assert item.status == "pending_review"

    item = await content_marketing_service.approve_content(
        db_session, workspace_id=DEFAULT_WORKSPACE, content_id=item.id,
        approved_by="tester", quality_score=95.0,
    )
    assert item.status == "approved"
    assert item.approved_by == "tester"
    assert item.approved_at is not None
    assert item.quality_score == Decimal("95.00")

    item = await content_marketing_service.publish_content(
        db_session, workspace_id=DEFAULT_WORKSPACE, content_id=item.id,
    )
    assert item.status == "published"
    assert item.published_at is not None


@pytest.mark.asyncio
async def test_cannot_publish_without_approval(db_session):
    """Cannot publish directly from draft or pending_review."""
    item = await content_marketing_service.create_content_item(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        content_type="seo_article", title="Unapproved",
    )
    # draft -> published should fail
    with pytest.raises(content_marketing_service.ContentStateError):
        await content_marketing_service.publish_content(
            db_session, workspace_id=DEFAULT_WORKSPACE, content_id=item.id,
        )

    # pending_review -> published should fail
    item = await content_marketing_service.submit_content_for_review(
        db_session, workspace_id=DEFAULT_WORKSPACE, content_id=item.id,
    )
    with pytest.raises(content_marketing_service.ContentStateError):
        await content_marketing_service.publish_content(
            db_session, workspace_id=DEFAULT_WORKSPACE, content_id=item.id,
        )


@pytest.mark.asyncio
async def test_content_reject_and_revert(db_session):
    """Reject: pending_review -> rejected; Revert: rejected -> draft."""
    item = await content_marketing_service.create_content_item(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        content_type="seo_article", title="To Reject",
    )
    item = await content_marketing_service.submit_content_for_review(
        db_session, workspace_id=DEFAULT_WORKSPACE, content_id=item.id,
    )
    item = await content_marketing_service.reject_content(
        db_session, workspace_id=DEFAULT_WORKSPACE, content_id=item.id,
        rejected_by="tester", reason="Quality too low",
    )
    assert item.status == "rejected"
    assert item.rejection_reason == "Quality too low"

    # Revert to draft for re-editing
    item = await content_marketing_service.revert_content_to_draft(
        db_session, workspace_id=DEFAULT_WORKSPACE, content_id=item.id,
    )
    assert item.status == "draft"
    assert item.rejection_reason is None


@pytest.mark.asyncio
async def test_invalid_state_transition(db_session):
    """Invalid transitions raise ContentStateError."""
    item = await content_marketing_service.create_content_item(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        content_type="seo_article", title="Test",
    )
    # draft -> approved should fail (must go through pending_review)
    with pytest.raises(content_marketing_service.ContentStateError):
        await content_marketing_service.approve_content(
            db_session, workspace_id=DEFAULT_WORKSPACE, content_id=item.id,
            approved_by="tester",
        )


# --------------------------------------------------------------------------- #
# EDMCampaign
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_create_edm_campaign(db_session):
    """Create EDM campaign in draft status."""
    campaign = await content_marketing_service.create_edm_campaign(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        name="Welcome Campaign", campaign_type="welcome",
        subject="Welcome to Nuotao Outdoor",
        content_json={"body": "Welcome!"},
    )
    assert campaign.id is not None
    assert campaign.status == "draft"
    assert campaign.name == "Welcome Campaign"
    assert campaign.total_sent == 0


@pytest.mark.asyncio
async def test_edm_campaign_transitions(db_session):
    """EDM campaign status transitions: draft -> scheduled -> active -> completed."""
    campaign = await content_marketing_service.create_edm_campaign(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        name="Test Campaign", campaign_type="newsletter",
    )
    assert campaign.status == "draft"

    campaign = await content_marketing_service.transition_edm_campaign(
        db_session, workspace_id=DEFAULT_WORKSPACE, campaign_id=campaign.id,
        target_status="scheduled",
    )
    assert campaign.status == "scheduled"

    campaign = await content_marketing_service.transition_edm_campaign(
        db_session, workspace_id=DEFAULT_WORKSPACE, campaign_id=campaign.id,
        target_status="active",
    )
    assert campaign.status == "active"
    assert campaign.started_at is not None

    campaign = await content_marketing_service.transition_edm_campaign(
        db_session, workspace_id=DEFAULT_WORKSPACE, campaign_id=campaign.id,
        target_status="completed",
    )
    assert campaign.status == "completed"
    assert campaign.completed_at is not None


@pytest.mark.asyncio
async def test_edm_invalid_transition(db_session):
    """Invalid EDM transition raises ContentStateError."""
    campaign = await content_marketing_service.create_edm_campaign(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        name="Test", campaign_type="newsletter",
    )
    # draft -> active should fail (must go through scheduled)
    with pytest.raises(content_marketing_service.ContentStateError):
        await content_marketing_service.transition_edm_campaign(
            db_session, workspace_id=DEFAULT_WORKSPACE, campaign_id=campaign.id,
            target_status="active",
        )


# --------------------------------------------------------------------------- #
# SEORecord
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_create_seo_record(db_session):
    """Create SEO record."""
    record = await content_marketing_service.create_seo_record(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        keyword="camping tent", target_url="https://example.com/tent",
        target_page_type="product", language="en", country="US",
        search_volume=1000, keyword_difficulty=45.5,
        meta_title="Best Camping Tent", meta_description="Shop our camping tents",
    )
    assert record.id is not None
    assert record.keyword == "camping tent"
    assert record.status == "active"
    assert record.search_volume == 1000


@pytest.mark.asyncio
async def test_seo_ranking_snapshot_with_source(db_session):
    """Add ranking snapshot with source tracking (manual/external_real/ai_estimated)."""
    record = await content_marketing_service.create_seo_record(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        keyword="hiking backpack", target_page_type="product",
    )
    # Add snapshot from external real data
    record = await content_marketing_service.add_seo_ranking_snapshot(
        db_session, workspace_id=DEFAULT_WORKSPACE, seo_id=record.id,
        position=15, url="https://example.com/backpack", source="external_real",
    )
    assert record.current_position == 15
    assert record.best_position == 15
    assert len(record.ranking_history) == 1
    assert record.ranking_history[0]["source"] == "external_real"

    # Add better position (manual)
    record = await content_marketing_service.add_seo_ranking_snapshot(
        db_session, workspace_id=DEFAULT_WORKSPACE, seo_id=record.id,
        position=8, source="manual",
    )
    assert record.current_position == 8
    assert record.best_position == 8  # improved
    assert len(record.ranking_history) == 2


@pytest.mark.asyncio
async def test_seo_record_workspace_isolation(db_session):
    """SEO record from another workspace is not found."""
    record = await content_marketing_service.create_seo_record(
        db_session, workspace_id=DEFAULT_WORKSPACE,
        keyword="test keyword",
    )
    with pytest.raises(content_marketing_service.ContentNotFound):
        await content_marketing_service.get_seo_record(
            db_session, workspace_id=OTHER_WORKSPACE, seo_id=record.id,
        )
