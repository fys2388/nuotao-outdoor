"""Unit tests for M6 e-commerce capabilities: image generation, activity planner, influencer.

Covers:
- Image generation service: task CRUD, budget guard, mock backend generation, approve/reject
- Activity planner service: plan CRUD, approval flow, status validation
- Influencer service: influencer CRUD, collaboration CRUD, matching algorithm
"""

from __future__ import annotations

import pytest
from uuid import UUID, uuid4
from decimal import Decimal

from app.models.image_gen import ImageGenerationTask, USE_CASES
from app.models.activity_plan import ActivityPlan, ACTIVITY_TYPES, PLAN_STATUSES
from app.models.influencer import Influencer, InfluencerCollaboration, INFLUENCER_PLATFORMS
from app.services.image_generation_service import (
    ImageGenServiceError,
    approve_image,
    create_generation_task,
    execute_generation_task,
    generate_image_and_save,
    get_image_gen_status,
    get_monthly_spend,
    get_task,
    list_tasks,
    reject_image,
)
from app.services.activity_planner_service import (
    ActivityPlannerError,
    approve_plan,
    get_activity_planner_status,
    get_plan,
    list_plans,
    reject_plan,
)
from app.services.influencer_service import (
    InfluencerServiceError,
    create_collaboration,
    create_influencer,
    delete_influencer,
    get_influencer,
    get_influencer_status,
    list_collaborations,
    list_influencers,
    match_influencers,
    update_collaboration_status,
    update_influencer,
)
from app.integrations.image_gen import (
    BACKEND_PRICING,
    FALLBACK_CHAIN,
    generate_image,
    get_model_cost,
    list_available_models,
)

DEFAULT_WORKSPACE = UUID("00000000-0000-0000-0000-000000000001")


# ============================================
# Image Generation Integration Tests
# ============================================


class TestImageGenIntegration:
    """Tests for the pluggable image generation gateway."""

    def test_list_available_models(self):
        models = list_available_models()
        assert len(models) >= 4
        model_names = [m["model"] for m in models]
        assert "wan2.7-image" in model_names
        assert "mock" in model_names

    def test_model_cost(self):
        assert get_model_cost("wan2.7-image") == 0.08
        assert get_model_cost("qwen-image-3.0") == 0.18
        assert get_model_cost("mock") == 0.0
        assert get_model_cost("nonexistent") == 0.0

    def test_pricing_table_structure(self):
        for model, info in BACKEND_PRICING.items():
            assert "cost_cny" in info
            assert "provider" in info
            assert "quality" in info
            assert info["cost_cny"] >= 0

    @pytest.mark.asyncio
    async def test_mock_backend_generation(self):
        result = await generate_image(
            prompt="A red hiking backpack",
            model="mock",
            width=512,
            height=512,
        )
        assert result.model == "mock"
        assert result.cost_cny == 0.0
        assert result.image_b64 is not None
        assert len(result.image_b64) > 0
        assert result.raw_response.get("mock") is True

    @pytest.mark.asyncio
    async def test_fallback_chain_contains_mock(self):
        assert "mock" in FALLBACK_CHAIN


# ============================================
# Image Generation Service Tests
# ============================================


class TestImageGenerationService:
    """Tests for the image generation service layer."""

    def test_service_status(self):
        status = get_image_gen_status()
        assert status["service"] == "image_generation"
        assert status["status"] == "operational"
        assert status["default_model"] == "wan2.7-image"
        assert len(status["available_models"]) >= 4
        assert "main_image" in status["use_cases"]

    @pytest.mark.asyncio
    async def test_create_task(self, db_session):
        task = await create_generation_task(
            db_session,
            workspace_id=DEFAULT_WORKSPACE,
            prompt="A blue tent",
            use_case="main_image",
            model="mock",
        )
        assert task.id is not None
        assert task.prompt == "A blue tent"
        assert task.use_case == "main_image"
        assert task.status == "pending"
        assert task.requested_model == "mock"

    @pytest.mark.asyncio
    async def test_create_task_invalid_use_case(self, db_session):
        with pytest.raises(ImageGenServiceError):
            await create_generation_task(
                db_session,
                workspace_id=DEFAULT_WORKSPACE,
                prompt="test",
                use_case="invalid_case",
            )

    @pytest.mark.asyncio
    async def test_execute_task_with_mock(self, db_session):
        task = await create_generation_task(
            db_session,
            workspace_id=DEFAULT_WORKSPACE,
            prompt="A green sleeping bag",
            use_case="detail_image",
            model="mock",
        )
        executed = await execute_generation_task(
            db_session,
            task_id=task.id,
            workspace_id=DEFAULT_WORKSPACE,
        )
        assert executed.status == "generated"
        assert executed.actual_model == "mock"
        assert executed.cost_cny == Decimal("0")
        assert executed.image_path is not None or executed.image_url is not None

    @pytest.mark.asyncio
    async def test_generate_and_save(self, db_session):
        task = await generate_image_and_save(
            db_session,
            workspace_id=DEFAULT_WORKSPACE,
            prompt="A yellow hiking pole",
            use_case="marketing_image",
            model="mock",
        )
        assert task.status == "generated"
        result = await get_task(db_session, task_id=task.id, workspace_id=DEFAULT_WORKSPACE)
        assert result is not None
        assert result["status"] == "generated"

    @pytest.mark.asyncio
    async def test_approve_image(self, db_session):
        task = await generate_image_and_save(
            db_session,
            workspace_id=DEFAULT_WORKSPACE,
            prompt="test",
            model="mock",
        )
        approved = await approve_image(
            db_session,
            task_id=task.id,
            approved_by="test_user",
            workspace_id=DEFAULT_WORKSPACE,
        )
        assert approved.status == "approved"
        assert approved.approved_by == "test_user"
        assert approved.approved_at is not None

    @pytest.mark.asyncio
    async def test_reject_image(self, db_session):
        task = await generate_image_and_save(
            db_session,
            workspace_id=DEFAULT_WORKSPACE,
            prompt="test",
            model="mock",
        )
        rejected = await reject_image(
            db_session,
            task_id=task.id,
            workspace_id=DEFAULT_WORKSPACE,
        )
        assert rejected.status == "rejected"

    @pytest.mark.asyncio
    async def test_list_tasks(self, db_session):
        await generate_image_and_save(db_session, workspace_id=DEFAULT_WORKSPACE, prompt="task1", model="mock")
        await generate_image_and_save(db_session, workspace_id=DEFAULT_WORKSPACE, prompt="task2", model="mock")
        result = await list_tasks(db_session, workspace_id=DEFAULT_WORKSPACE, limit=10)
        assert result["total"] >= 2

    @pytest.mark.asyncio
    async def test_monthly_spend(self, db_session):
        await generate_image_and_save(db_session, workspace_id=DEFAULT_WORKSPACE, prompt="test", model="mock")
        spend = await get_monthly_spend(db_session, workspace_id=DEFAULT_WORKSPACE)
        assert spend >= Decimal("0")


# ============================================
# Activity Planner Service Tests
# ============================================


class TestActivityPlannerService:
    """Tests for the activity planner service layer (LLM calls mocked)."""

    def test_service_status(self):
        status = get_activity_planner_status()
        assert status["service"] == "activity_planner"
        assert status["status"] == "operational"
        assert len(status["activity_types"]) >= 5
        assert "big_promotion" in status["activity_types"]

    def test_activity_types_constants(self):
        assert "big_promotion" in ACTIVITY_TYPES
        assert "new_launch" in ACTIVITY_TYPES
        assert "clearance" in ACTIVITY_TYPES
        assert "seasonal" in ACTIVITY_TYPES

    def test_plan_statuses_constants(self):
        assert "draft" in PLAN_STATUSES
        assert "approved" in PLAN_STATUSES
        assert "rejected" in PLAN_STATUSES
        assert "executing" in PLAN_STATUSES

    @pytest.mark.asyncio
    async def test_approve_plan(self, db_session):
        plan = ActivityPlan(
            id=uuid4(),
            workspace_id=DEFAULT_WORKSPACE,
            name="Test Plan",
            activity_type="seasonal",
            budget_total=Decimal("1000.00"),
            plan_json={"summary": "test"},
        )
        db_session.add(plan)
        await db_session.flush()

        result = await approve_plan(
            db_session,
            plan_id=plan.id,
            approved_by="test_user",
            workspace_id=DEFAULT_WORKSPACE,
        )
        assert result["approval_status"] == "approved"
        assert result["approved_by"] == "test_user"

    @pytest.mark.asyncio
    async def test_reject_plan(self, db_session):
        plan = ActivityPlan(
            id=uuid4(),
            workspace_id=DEFAULT_WORKSPACE,
            name="Test Plan",
            activity_type="clearance",
            budget_total=Decimal("500.00"),
            plan_json={"summary": "test"},
        )
        db_session.add(plan)
        await db_session.flush()

        result = await reject_plan(
            db_session,
            plan_id=plan.id,
            reject_reason="Not enough budget",
            workspace_id=DEFAULT_WORKSPACE,
        )
        assert result["approval_status"] == "rejected"
        assert result["reject_reason"] == "Not enough budget"

    @pytest.mark.asyncio
    async def test_get_plan_not_found(self, db_session):
        result = await get_plan(db_session, plan_id=uuid4(), workspace_id=DEFAULT_WORKSPACE)
        assert result is None

    @pytest.mark.asyncio
    async def test_list_plans(self, db_session):
        for i in range(3):
            plan = ActivityPlan(
                id=uuid4(),
                workspace_id=DEFAULT_WORKSPACE,
                name=f"Plan {i}",
                activity_type="other",
                budget_total=Decimal("100.00"),
                plan_json={"summary": f"test {i}"},
            )
            db_session.add(plan)
        await db_session.flush()

        result = await list_plans(db_session, workspace_id=DEFAULT_WORKSPACE, limit=10)
        assert result["total"] >= 3

    @pytest.mark.asyncio
    async def test_approve_nonexistent_plan(self, db_session):
        with pytest.raises(ActivityPlannerError):
            await approve_plan(db_session, plan_id=uuid4(), approved_by="test", workspace_id=DEFAULT_WORKSPACE)


# ============================================
# Influencer Service Tests
# ============================================


class TestInfluencerService:
    """Tests for the influencer / KOL service layer."""

    def test_service_status(self):
        status = get_influencer_status()
        assert status["service"] == "influencer"
        assert status["status"] == "operational"
        assert "instagram" in status["platforms"]
        assert "product_seeding" in status["collab_types"]

    def test_platforms_constants(self):
        assert "instagram" in INFLUENCER_PLATFORMS
        assert "tiktok" in INFLUENCER_PLATFORMS
        assert "youtube" in INFLUENCER_PLATFORMS

    @pytest.mark.asyncio
    async def test_create_influencer(self, db_session):
        result = await create_influencer(
            db_session,
            workspace_id=DEFAULT_WORKSPACE,
            name="Test Creator",
            platform="instagram",
            handle="@testcreator",
            followers=50000,
            engagement_rate=3.5,
            category="outdoor",
            region="US",
        )
        assert result["id"] is not None
        assert result["name"] == "Test Creator"
        assert result["platform"] == "instagram"
        assert result["followers"] == 50000
        assert result["engagement_rate"] == 3.5

    @pytest.mark.asyncio
    async def test_create_influencer_invalid_platform(self, db_session):
        with pytest.raises(InfluencerServiceError):
            await create_influencer(
                db_session,
                workspace_id=DEFAULT_WORKSPACE,
                name="Test",
                platform="invalid_platform",
            )

    @pytest.mark.asyncio
    async def test_update_influencer(self, db_session):
        created = await create_influencer(
            db_session,
            workspace_id=DEFAULT_WORKSPACE,
            name="Old Name",
            platform="tiktok",
            followers=1000,
        )
        updated = await update_influencer(
            db_session,
            influencer_id=UUID(created["id"]),
            workspace_id=DEFAULT_WORKSPACE,
            name="New Name",
            followers=5000,
        )
        assert updated["name"] == "New Name"
        assert updated["followers"] == 5000

    @pytest.mark.asyncio
    async def test_delete_influencer(self, db_session):
        created = await create_influencer(
            db_session,
            workspace_id=DEFAULT_WORKSPACE,
            name="To Delete",
            platform="youtube",
        )
        result = await delete_influencer(
            db_session,
            influencer_id=UUID(created["id"]),
            workspace_id=DEFAULT_WORKSPACE,
        )
        assert result["deleted"] is True
        assert result["status"] == "inactive"

    @pytest.mark.asyncio
    async def test_list_influencers(self, db_session):
        for i in range(3):
            await create_influencer(
                db_session,
                workspace_id=DEFAULT_WORKSPACE,
                name=f"Creator {i}",
                platform="instagram",
                followers=1000 * (i + 1),
                category="outdoor",
            )
        result = await list_influencers(db_session, workspace_id=DEFAULT_WORKSPACE, limit=10)
        assert result["total"] >= 3

    @pytest.mark.asyncio
    async def test_list_influencers_filter_by_platform(self, db_session):
        await create_influencer(db_session, workspace_id=DEFAULT_WORKSPACE, name="IG User", platform="instagram")
        await create_influencer(db_session, workspace_id=DEFAULT_WORKSPACE, name="TT User", platform="tiktok")
        result = await list_influencers(db_session, workspace_id=DEFAULT_WORKSPACE, platform="instagram")
        for inf in result["influencers"]:
            assert inf["platform"] == "instagram"

    @pytest.mark.asyncio
    async def test_match_influencers(self, db_session):
        # Create test influencers
        await create_influencer(
            db_session, workspace_id=DEFAULT_WORKSPACE,
            name="Outdoor Pro", platform="instagram", followers=100000,
            engagement_rate=5.0, category="outdoor gear", region="US",
        )
        await create_influencer(
            db_session, workspace_id=DEFAULT_WORKSPACE,
            name="Fashion Vlogger", platform="youtube", followers=50000,
            engagement_rate=2.0, category="fashion", region="UK",
        )
        await create_influencer(
            db_session, workspace_id=DEFAULT_WORKSPACE,
            name="Hiking Fan", platform="tiktok", followers=200000,
            engagement_rate=8.0, category="outdoor hiking", region="US",
        )

        result = await match_influencers(
            db_session,
            workspace_id=DEFAULT_WORKSPACE,
            product_category="outdoor",
            target_region="US",
            limit=5,
        )
        assert result["candidates_evaluated"] >= 2
        assert len(result["matches"]) >= 2
        # Top match should have the highest score
        scores = [m["match_score"] for m in result["matches"]]
        assert scores == sorted(scores, reverse=True)
        # Each match should have reasons
        for m in result["matches"]:
            assert len(m["match_reasons"]) > 0

    @pytest.mark.asyncio
    async def test_create_collaboration(self, db_session):
        inf = await create_influencer(
            db_session, workspace_id=DEFAULT_WORKSPACE,
            name="Collab Creator", platform="instagram", followers=10000,
        )
        collab = await create_collaboration(
            db_session,
            workspace_id=DEFAULT_WORKSPACE,
            influencer_id=UUID(inf["id"]),
            collab_type="product_seeding",
            compensation_amount=0,
            content_requirements="Post 1 reel + 3 stories",
        )
        assert collab["id"] is not None
        assert collab["collab_type"] == "product_seeding"
        assert collab["status"] == "prospecting"

    @pytest.mark.asyncio
    async def test_update_collaboration_status(self, db_session):
        inf = await create_influencer(
            db_session, workspace_id=DEFAULT_WORKSPACE,
            name="Status Test", platform="instagram", followers=5000,
        )
        collab = await create_collaboration(
            db_session, workspace_id=DEFAULT_WORKSPACE,
            influencer_id=UUID(inf["id"]), collab_type="sponsored_post",
            compensation_amount=500,
        )
        updated = await update_collaboration_status(
            db_session,
            collaboration_id=UUID(collab["id"]),
            new_status="completed",
            workspace_id=DEFAULT_WORKSPACE,
            content_url="https://instagram.com/p/test",
            metrics={"likes": 1000, "comments": 50},
        )
        assert updated["status"] == "completed"
        assert updated["content_url"] == "https://instagram.com/p/test"
        assert updated["completed_at"] is not None

    @pytest.mark.asyncio
    async def test_list_collaborations(self, db_session):
        inf = await create_influencer(
            db_session, workspace_id=DEFAULT_WORKSPACE,
            name="List Test", platform="instagram", followers=5000,
        )
        await create_collaboration(
            db_session, workspace_id=DEFAULT_WORKSPACE,
            influencer_id=UUID(inf["id"]), collab_type="affiliate",
        )
        result = await list_collaborations(
            db_session, workspace_id=DEFAULT_WORKSPACE,
            influencer_id=UUID(inf["id"]),
        )
        assert result["total"] >= 1
