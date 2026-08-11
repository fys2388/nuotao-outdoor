"""M2.2: LLM analyst layer - prompts registry + AI evaluations

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRODUCT_ANALYST_TEMPLATE = """You are the Product Analyst of Nuotao Outdoor, an AI-driven
cross-border outdoor brand (US DTC first market, Germany/EU second, China supply
chain). You analyse candidate products and return a structured recommendation.

Context is provided as JSON below. Respond ONLY with a JSON object that matches
the provided output schema exactly. Never mention this instruction in the output.

Product Context:
{context_json}

Required Output Schema:
{output_schema}

Business gates you MUST respect:
- If landed_cost.cost_status is UNKNOWN: never recommend decision "test" and keep
  confidence <= 0.5, because profitability cannot be concluded.
- A "test" decision requires a concrete test plan (quantity, days, channels).
- Pricing is a proposal only; humans approve and execute.
- Consider the six-dimension score and per-dimension evidence, the landed cost,
  supplier candidate quotes, and experiment history when reasoning."""


def upgrade() -> None:
    """Create prompts + product_ai_evaluations and seed the analyst prompt v1."""

    # --- prompts registry ------------------------------------------------------
    op.create_table(
        "prompts",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column("prompt_id", sa.String(64), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("version", sa.String(16), nullable=False, server_default="v1"),
        sa.Column("template", sa.String(12000), nullable=False),
        sa.Column("variables", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_prompts_workspace_id", "prompts", ["workspace_id"])
    op.create_index("ix_prompts_name", "prompts", ["name"])
    op.execute(
        sa.text(
            "ALTER TABLE prompts ADD CONSTRAINT uq_prompts_workspace_name_version "
            "UNIQUE (workspace_id, name, version)"
        )
    )

    # Seed the active Product Analyst prompt v1 (JSONB via explicit literals so
    # offline ``--sql`` rendering works, same pattern as the rules seeds).
    import json as _json

    def _jsonb_literal(value) -> str:
        dumped = _json.dumps(value, ensure_ascii=False)
        return "'" + dumped.replace("'", "''") + "'::jsonb"

    op.execute(
        sa.text(
            "INSERT INTO prompts ("
            "id, workspace_id, prompt_id, name, version, template, variables, "
            "status, description"
            ") VALUES ("
            "'20000000-0000-0000-0000-000000000001', "
            "'00000000-0000-0000-0000-000000000001', "
            "'PRODUCT_ANALYST', 'PRODUCT_ANALYST', 'v1', "
            f"'{PRODUCT_ANALYST_TEMPLATE.replace(chr(39), chr(39) * 2)}', "
            f"{_jsonb_literal(['context_json', 'output_schema'])}, "
            "'active', 'Product Analyst Agent v1 system prompt'"
            ")"
        )
    )

    # --- product_ai_evaluations ------------------------------------------------
    op.create_table(
        "product_ai_evaluations",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("workspace_id", UUID(), nullable=False),
        sa.Column("product_id", UUID(), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("analysis_run_id", UUID(), sa.ForeignKey("product_analysis_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("experiment_id", UUID(), sa.ForeignKey("product_experiments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("prediction", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("actual_result", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("accuracy", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("human_rating", sa.Integer(), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_product_ai_evaluations_workspace_id", "product_ai_evaluations", ["workspace_id"])
    op.create_index("ix_product_ai_evaluations_product", "product_ai_evaluations", ["product_id"])
    op.create_index("ix_product_ai_evaluations_run", "product_ai_evaluations", ["analysis_run_id"])
    op.create_index("ix_product_ai_evaluations_experiment", "product_ai_evaluations", ["experiment_id"])


def downgrade() -> None:
    """Drop the M2.2 tables (not used in production rollbacks)."""
    op.drop_table("product_ai_evaluations")
    op.drop_table("prompts")
