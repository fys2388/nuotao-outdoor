"""Agent config seed — idempotent registration for CI / bootstrap.

Replaces the hand-run ``scripts/configure_agent_roles.sql`` (hyphenated agent
ids that conflicted with the runtime snake_case ids) and the never-wired
``scripts/register_agent_tools.sql`` (26 tools whose ``handler_name`` values
were ``module.func`` paths that never matched a registered tool handler).

Run from ``backend``:

    python scripts/seed_agent_config.py

Semantics
---------
- **upsert only, never DELETE**: existing rows are updated in place, so a
  partially- or manually-configured environment is brought into alignment
  without data loss;
- prompts are created first (``register_agent`` refuses to register an agent
  whose prompt version does not exist);
- ``handler_name`` is set **only** for tools that actually have a handler
  registered in ``app.services.m6_tool_registry``. Everything else is written
  as ``handler_name=None`` -> whitelist-only (audit-only) behavior, which is
  the safe default per ``app/services/tool_gateway.py``. Writing a handler
  name that does not exist would make the L3 approval flow silently
  non-executable;
- the seed runs against ``DEFAULT_WORKSPACE_ID``; pass ``--workspace`` for
  other workspaces.

Scope (v1.0)
------------
1. 5 canonical agents (snake_case, one row per role, no identity forks)
2. 5 versioned prompts (``AGENT_<AGENT_ID>`` v1) so the runtime prompt gate
   passes for every agent, not just ``product_analyst``
3. Tool whitelist: 26 legacy tools (``handler_name=None``) + 5 real M6 handlers
4. Per-agent monthly budget policies (only when none exists, to avoid version
   churn on every deploy)

Out of scope: approval SLA (config-driven via
``approval_default_warning_seconds`` / ``approval_default_expire_seconds``).

See ``docs/agent_team_workflow_refactor.md`` for the full assessment.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Allow running as a script from the ``backend/`` directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import async_session_factory  # noqa: E402
from app.core.workspace import DEFAULT_WORKSPACE_ID  # noqa: E402
from app.models.agent_runtime import AgentRegistry, AgentTool  # noqa: E402
from app.models.agent_runtime_hardening import AgentBudgetPolicy  # noqa: E402
from app.models.prompt import Prompt  # noqa: E402
from app.schemas.agent_runtime import AgentRegisterRequest  # noqa: E402
from app.schemas.prompt import PromptCreate  # noqa: E402
from app.services import agent_policies, agent_runtime, prompt_registry  # noqa: E402

logger = logging.getLogger("seed_agent_config")

TRACE_ID = "seed-agent-config"
PROMPT_VERSION = "v1"
MAX_COST_PER_EXECUTION = Decimal("5.00")
BUDGET_ALERT_THRESHOLD = Decimal("0.80")

# Every runtime agent prompt must expose exactly these two placeholders —
# ``app/agents/generic_agent.py`` renders ``context_json`` + ``output_schema``.
PROMPT_VARIABLES = ["context_json", "output_schema"]

# --------------------------------------------------------------------------- #
# 1. Agents: 5 canonical roles, snake_case ids (AGENTS.md §1.1)
# --------------------------------------------------------------------------- #
# NOTE: ``domain`` is constrained by ``AgentRegisterRequest`` to
# product | marketing | customer | supply_chain | operations, so
# business_analyst maps to "operations".
AGENTS: list[dict] = [
    {
        "agent_id": "product_analyst",
        "name": "Product Analyst AI",
        "domain": "product",
        "permission_level": "L2",
        "model_provider": "sensenova",
        "model_name": "sensenova-6.8-flash-lite",
        "description": (
            "AI 产品分析师：选品分析、产品导入、图片合规检查、WooCommerce 上架提议。"
            "只提议不执行，发布产品等高风险动作必须人工审批。"
        ),
        "role_zh": "Product Analyst (产品分析师)",
        "monthly_budget": "50.00",
    },
    {
        "agent_id": "marketing_manager",
        "name": "Marketing Manager AI",
        "domain": "marketing",
        "permission_level": "L2",
        "model_provider": "sensenova",
        "model_name": "sensenova-6.8-flash-lite",
        "description": (
            "AI 营销经理：产品文案生成、文案合规检查、AI 生图（主图+详情图）、"
            "生图质量检查。报告强制通过 report_truthfulness 防造假校验。"
        ),
        "role_zh": "Marketing Manager (营销经理)",
        "monthly_budget": "100.00",
    },
    {
        "agent_id": "supply_chain_manager",
        "name": "Supply Chain Manager AI",
        "domain": "supply_chain",
        "permission_level": "L2",
        "model_provider": "sensenova",
        "model_name": "sensenova-6.8-flash-lite",
        "description": (
            "AI 供应链经理：库存同步、采购单创建、1688 下单、采购物流追踪。"
            "1688 实际下单需人工审批（L3）。"
        ),
        "role_zh": "Supply Chain Manager (供应链经理)",
        "monthly_budget": "30.00",
    },
    {
        "agent_id": "customer_manager",
        "name": "Customer Manager AI",
        "domain": "customer",
        "permission_level": "L1",
        "model_provider": "sensenova",
        "model_name": "sensenova-6.8-flash-lite",
        "description": (
            "AI 客户经理：客户咨询回复、订单状态查询、售后问题处理。"
            "对外文案必须通过禁词/敏感词/品牌口径校验，回复不了时降级到人工。"
        ),
        "role_zh": "Customer Manager (客户经理)",
        "monthly_budget": "20.00",
    },
    {
        "agent_id": "business_analyst",
        "name": "Business Analyst AI",
        "domain": "operations",
        "permission_level": "L3",
        "model_provider": "sensenova",
        "model_name": "sensenova-6.8-flash-lite",
        "description": (
            "AI 商业分析师：经营数据分析、成本模型、AI 周报、选品模型评估。"
            "所有数据基于真实 API，禁止模拟数据。"
        ),
        "role_zh": "Business Analyst (商业分析师)",
        "monthly_budget": "30.00",
    },
]


def prompt_name_for(agent_id: str) -> str:
    """Runtime prompt name for an agent: ``AGENT_PRODUCT_ANALYST`` etc."""
    return "AGENT_" + agent_id.upper().replace("-", "_")


def prompt_template_for(role_zh: str) -> str:
    return (
        f"You are the Nuotao Outdoor {role_zh}. Analyze the provided context "
        "and respond with ONLY a JSON object matching the output schema.\n"
        "Context: {context_json}\n"
        "Output schema: {output_schema}"
    )


# --------------------------------------------------------------------------- #
# 1b. Service prompts
# --------------------------------------------------------------------------- #
# These are NOT the 5 canonical agent roles. They back live REST endpoints and
# M6 tool handlers that call run_generic_agent() directly.
#
# Without these, the tools registered above as "executable" (handler_name set)
# would crash on their very first call with PromptNotFoundError - they look up
# their prompt before doing anything else.
#
# NOTE: agents_generic.py also requires AGENT_CUSTOMER_SERVICE_MANAGER. That
# identity is a known fork (see docs/agent_team_workflow_refactor.md §1.1) and
# is deliberately NOT seeded here: the endpoint must be repointed to the
# canonical `customer_manager` instead of getting its own prompt row.
SERVICE_PROMPTS: list[tuple[str, str, str]] = [
    (
        "ACTIVITY_PLANNER_V1",
        "Marketing Activity Planner",
        "营销活动计划生成 prompt（activity_planner_service + M6 工具 generate_activity_plan）",
    ),
    (
        "CUSTOMER_RESPONSE_V1",
        "Customer Response Writer",
        "客服回复生成 prompt（customer_template_service.generate_customer_response）",
    ),
    (
        "LISTING_LOCALIZATION_V1",
        "Listing Localizer",
        "产品 listing 多语种本地化 prompt（listing_localization_service + M6 工具 localize_listing）",
    ),
]


def service_prompt_template(role_en: str) -> str:
    """Same two-placeholder contract as the agent prompts (generic_agent.py)."""
    return (
        f"You are the Nuotao Outdoor {role_en}. Analyze the provided context "
        "and respond with ONLY a JSON object matching the output schema.\n"
        "Context: {context_json}\n"
        "Output schema: {output_schema}"
    )


# --------------------------------------------------------------------------- #
# 2. Tool whitelist
# --------------------------------------------------------------------------- #
# ``handler_name`` stays None unless a real handler is registered in
# app/services/m6_tool_registry.py. Registering a name without a handler makes
# execute_tool_call() log "handler not registered" and refuse.
TOOL_SCHEMAS: dict[str, str] = {
    "search_1688_products": '{"keyword":"string","category":"string","page":"integer","page_size":"integer"}',
    "get_1688_product_detail": '{"offer_id":"string"}',
    "analyze_product_selection": '{"product_data":"object","market_data":"object"}',
    "import_product_to_system": '{"sku":"string","name":"string","source_url":"string","source":"string","cost_price":"decimal"}',
    "generate_product_copy": '{"product_id":"uuid","language":"string","tone":"string"}',
    "check_copy_compliance": '{"content":"string","rules":"array"}',
    "save_product_copy": '{"product_id":"uuid","title":"string","description":"string","bullets":"array","seo_keywords":"array"}',
    "check_image_compliance": '{"image_url":"string","rules":"array"}',
    "download_1688_images": '{"offer_id":"string","output_dir":"string"}',
    "generate_main_images": '{"product_id":"uuid","reference_image":"string","directions":"array","prompt_template":"string"}',
    "generate_detail_images": '{"product_id":"uuid","reference_image":"string","sections":"array","prompt_template":"string"}',
    "check_image_quality": '{"generated_images":"array","reference_image":"string","checklist":"array"}',
    "save_product_images": '{"product_id":"uuid","main_image":"string","gallery_images":"array","detail_images":"array"}',
    "create_woocommerce_product": '{"product_id":"uuid","name":"string","sku":"string","price":"decimal","description":"string","category":"string"}',
    "upload_woocommerce_images": '{"product_id":"uuid","images":"array"}',
    "publish_woocommerce_product": '{"woocommerce_product_id":"integer"}',
    "create_purchase_order": '{"order_id":"uuid","product_id":"uuid","supplier_id":"string","quantity":"integer","unit_price":"decimal"}',
    "submit_1688_order": '{"purchase_order_id":"uuid","1688_offer_id":"string","sku_id":"string","quantity":"integer"}',
    "track_purchase_order": '{"purchase_order_id":"uuid"}',
    "sync_logistics_to_woocommerce": '{"order_id":"uuid","tracking_number":"string","carrier":"string"}',
    "sync_inventory_from_1688": '{"offer_id":"string","sku_id":"string"}',
    "update_woocommerce_inventory": '{"product_id":"uuid","quantity":"integer"}',
    "get_product_data": '{"product_id":"uuid"}',
    "list_products": '{"status":"string","page":"integer","page_size":"integer"}',
    "create_approval_request": '{"approval_type":"string","entity_type":"string","entity_id":"string","metadata":"object"}',
    "log_agent_run": '{"agent_id":"uuid","input":"object","output":"object","tool_calls":"array","cost":"decimal","status":"string"}',
    "generate_product_image": '{"prompt":"string","product_id":"uuid","style":"string"}',
    "generate_activity_plan": '{"goal":"string","budget":"decimal","period":"string"}',
    "match_influencers": '{"category":"string","region":"string","audience_size_min":"integer"}',
    "localize_listing": '{"product_id":"uuid","target_locale":"string"}',
    "get_customer_template": '{"scenario":"string","locale":"string"}',
}

# 26 legacy tools: whitelist-only (handler_name=None) until a handler is
# registered under that exact name.
LEGACY_TOOLS: list[tuple[str, str, str, str]] = [
    ("search_1688_products", "L1", "sourcing", "1688商品搜索，按关键词/品类检索商品列表"),
    ("get_1688_product_detail", "L1", "sourcing", "获取1688商品详情（价格、SKU、图片、属性、供应商）"),
    ("analyze_product_selection", "L2", "selection", "选品分析（市场需求、竞争度、利润空间、风险评估）"),
    ("import_product_to_system", "L2", "selection", "将选品导入系统（创建 candidate 状态产品）"),
    ("generate_product_copy", "L1", "copywriting", "AI生成产品文案（标题、描述、卖点、SEO关键词）"),
    ("check_copy_compliance", "L1", "copywriting", "文案合规检查（禁词、敏感词、品牌口径、事实核对）"),
    ("save_product_copy", "L2", "copywriting", "保存AI生成的文案到产品记录"),
    ("check_image_compliance", "L1", "image", "图片合规检查（白底、无文字、无水印、无促销标签）"),
    ("download_1688_images", "L1", "image", "下载1688商品图片到本地（用于 I2I 图生图参考）"),
    ("generate_main_images", "L1", "image_generation", "生成产品主图（白底/真实场景/促销转化 3 套方向）"),
    ("generate_detail_images", "L1", "image_generation", "生成产品详情页长图（6 个标准板块）"),
    ("check_image_quality", "L1", "image_generation", "生图质量检查（外观一致性、文字清晰度、构图）"),
    ("save_product_images", "L2", "image_generation", "保存生成的图片到产品记录"),
    ("create_woocommerce_product", "L2", "woocommerce", "创建WooCommerce产品（草稿状态，不直接发布）"),
    ("upload_woocommerce_images", "L2", "woocommerce", "上传图片到WooCommerce媒体库"),
    ("publish_woocommerce_product", "L3", "woocommerce", "发布WooCommerce产品（高风险，必须人工审批）"),
    ("create_purchase_order", "L2", "procurement", "创建采购单（1688下单，半自动模式）"),
    ("submit_1688_order", "L3", "procurement", "提交1688订单（高风险，必须人工审批）"),
    ("track_purchase_order", "L1", "procurement", "追踪采购单物流状态"),
    ("sync_logistics_to_woocommerce", "L2", "procurement", "同步物流信息到WooCommerce订单"),
    ("sync_inventory_from_1688", "L1", "inventory", "从1688同步库存信息"),
    ("update_woocommerce_inventory", "L2", "inventory", "更新WooCommerce产品库存"),
    ("get_product_data", "L0", "common", "读取产品数据"),
    ("list_products", "L0", "common", "列出产品列表"),
    ("create_approval_request", "L2", "common", "创建人工审批请求"),
    ("log_agent_run", "L0", "common", "记录Agent运行审计日志"),
]

# Tools that DO have a real in-process handler. Names must match
# app/services/m6_tool_registry.py:M6_TOOL_HANDLERS exactly.
M6_EXECUTABLE_TOOLS: list[tuple[str, str, str, str]] = [
    ("generate_product_image", "L2", "image_generation", "生成产品图片（成本护栏，默认 wan2.7-image）"),
    ("generate_activity_plan", "L2", "marketing", "生成营销活动计划建议（进入审批队列后才执行）"),
    ("match_influencers", "L1", "marketing", "按品类/地区/互动度匹配达人/KOL"),
    ("localize_listing", "L2", "localization", "产品 listing 多语种本地化（en/de/fr/es/it）"),
    ("get_customer_template", "L0", "customer_service", "客服话术模板检索（15 场景 x 6 语言，零 LLM 成本）"),
]


# --------------------------------------------------------------------------- #
# Seed steps
# --------------------------------------------------------------------------- #


async def _exists(session: AsyncSession, model, **where_values) -> bool:
    """Return True when a row matches all ``where_values``."""
    row = (
        await session.execute(
            select(model.id).where(
                *[getattr(model, column) == value for column, value in where_values.items()]
            )
        )
    ).scalar_one_or_none()
    return row is not None


async def seed_prompts(session: AsyncSession, *, workspace_id: UUID) -> tuple[int, int]:
    """Create-if-missing the versioned prompt for every agent."""
    created = existing = 0
    for agent in AGENTS:
        name = prompt_name_for(agent["agent_id"])
        if await _exists(session, Prompt, workspace_id=workspace_id, name=name, status="active"):
            existing += 1
            continue
        await prompt_registry.create_prompt(
            session,
            workspace_id=workspace_id,
            data=PromptCreate(
                prompt_id=name,
                name=name,
                version=PROMPT_VERSION,
                template=prompt_template_for(agent["role_zh"]),
                variables=PROMPT_VARIABLES,
                status="active",
                description=f"{agent['name']} runtime prompt {PROMPT_VERSION}",
            ),
            trace_id=TRACE_ID,
        )
        created += 1
        logger.info("prompt created: %s %s", name, PROMPT_VERSION)
    return created, existing


async def seed_service_prompts(session: AsyncSession, *, workspace_id: UUID) -> tuple[int, int]:
    """Create-if-missing the prompts that back live endpoints and M6 tools."""
    created = existing = 0
    for name, role_en, description in SERVICE_PROMPTS:
        if await _exists(session, Prompt, workspace_id=workspace_id, name=name, status="active"):
            existing += 1
            continue
        await prompt_registry.create_prompt(
            session,
            workspace_id=workspace_id,
            data=PromptCreate(
                prompt_id=name,
                name=name,
                version=PROMPT_VERSION,
                template=service_prompt_template(role_en),
                variables=PROMPT_VARIABLES,
                status="active",
                description=description,
            ),
            trace_id=TRACE_ID,
        )
        created += 1
        logger.info("service prompt created: %s", name)
    return created, existing


async def seed_agents(session: AsyncSession, *, workspace_id: UUID) -> tuple[int, int]:
    """Register (or update) the 5 canonical agents."""
    created = updated = 0
    for agent in AGENTS:
        existed = await _exists(
            session,
            AgentRegistry,
            workspace_id=workspace_id,
            agent_id=agent["agent_id"],
        )
        await agent_runtime.register_agent(
            session,
            workspace_id=workspace_id,
            data=AgentRegisterRequest(
                agent_id=agent["agent_id"],
                name=agent["name"],
                domain=agent["domain"],
                version="v1",
                status="active",
                model_provider=agent["model_provider"],
                model_name=agent["model_name"],
                prompt_version=PROMPT_VERSION,
                permission_level=agent["permission_level"],
                description=agent["description"],
            ),
            trace_id=TRACE_ID,
        )
        if existed:
            updated += 1
            logger.info("agent updated: %s", agent["agent_id"])
        else:
            created += 1
            logger.info(
                "agent created: %s (%s, %s/%s)",
                agent["agent_id"],
                agent["permission_level"],
                agent["model_provider"],
                agent["model_name"],
            )
    return created, updated


async def seed_tools(session: AsyncSession, *, workspace_id: UUID) -> tuple[int, int, int]:
    """Register the whitelist: 26 legacy (audit-only) + 5 real handlers."""
    created = updated = executable = 0
    for tool_name, level, category, description in (*LEGACY_TOOLS, *M6_EXECUTABLE_TOOLS):
        existed = await _exists(
            session, AgentTool, workspace_id=workspace_id, tool_name=tool_name
        )
        handler_name = tool_name if tool_name in dict(M6_EXECUTABLE_TOOLS) else None
        schema = TOOL_SCHEMAS.get(tool_name)
        args_schema = json.loads(schema) if schema else {}
        await agent_runtime.register_tool(
            session,
            workspace_id=workspace_id,
            tool_name=tool_name,
            description=description,
            permission_level=level,
            enabled=True,
            category=category,
            handler_name=handler_name,
            args_schema=args_schema,
            trace_id=TRACE_ID,
        )
        if existed:
            updated += 1
        else:
            created += 1
        if handler_name is not None:
            executable += 1
    return created, updated, executable


async def seed_budgets(session: AsyncSession, *, workspace_id: UUID) -> tuple[int, int]:
    """Insert per-agent budget policies only when none exists (no churn)."""
    created = skipped = 0
    for agent in AGENTS:
        agent_row = (
            await session.execute(
                select(AgentRegistry.id).where(
                    AgentRegistry.workspace_id == workspace_id,
                    AgentRegistry.agent_id == agent["agent_id"],
                )
            )
        ).scalar_one_or_none()
        if agent_row is None:
            logger.warning("agent %s missing, skipping budget", agent["agent_id"])
            skipped += 1
            continue
        current = (
            await session.execute(
                select(AgentBudgetPolicy.id).where(
                    AgentBudgetPolicy.workspace_id == workspace_id,
                    AgentBudgetPolicy.agent_id == agent_row,
                    AgentBudgetPolicy.is_current.is_(True),
                )
            )
        ).scalar_one_or_none()
        if current is not None:
            skipped += 1
            continue
        await agent_policies.set_budget_policy(
            session,
            workspace_id=workspace_id,
            agent_id=agent_row,
            monthly_budget=Decimal(agent["monthly_budget"]),
            max_cost_per_execution=MAX_COST_PER_EXECUTION,
            alert_threshold=BUDGET_ALERT_THRESHOLD,
            currency="USD",
            enabled=True,
            trace_id=TRACE_ID,
        )
        created += 1
        logger.info(
            "budget created: %s monthly=$%s", agent["agent_id"], agent["monthly_budget"]
        )
    return created, skipped


async def run(workspace_id: UUID) -> dict[str, object]:
    """Run every seed step, committing per step for partial-progress visibility."""
    stats: dict[str, object] = {}
    async with async_session_factory() as session:
        try:
            stats["prompts_created"], stats["prompts_existing"] = await seed_prompts(
                session, workspace_id=workspace_id
            )
            await session.commit()
            stats["service_prompts_created"], stats["service_prompts_existing"] = (
                await seed_service_prompts(session, workspace_id=workspace_id)
            )
            await session.commit()
            stats["agents_created"], stats["agents_updated"] = await seed_agents(
                session, workspace_id=workspace_id
            )
            await session.commit()
            (
                stats["tools_created"],
                stats["tools_updated"],
                stats["tools_executable"],
            ) = await seed_tools(session, workspace_id=workspace_id)
            await session.commit()
            stats["budgets_created"], stats["budgets_skipped"] = await seed_budgets(
                session, workspace_id=workspace_id
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Idempotently seed Nuotao AI OS agent config (agents/prompts/tools/budgets)."
    )
    parser.add_argument(
        "--workspace",
        default=str(DEFAULT_WORKSPACE_ID),
        help="Workspace UUID (default: the seeded default workspace)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    try:
        workspace_id = UUID(args.workspace)
    except ValueError:
        print(f"ERROR: invalid workspace UUID: {args.workspace}", file=sys.stderr)
        return 2

    try:
        stats = asyncio.run(run(workspace_id))
    except Exception as exc:
        logger.exception("seed failed")
        print(f"ERROR: seed failed: {exc}", file=sys.stderr)
        return 1

    print("\n=== Agent config seed result ===")
    for key in sorted(stats):
        print(f"  {key}: {stats[key]}")
    print(f"  workspace: {workspace_id}")
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
