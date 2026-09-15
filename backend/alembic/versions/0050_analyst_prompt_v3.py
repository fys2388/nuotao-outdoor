"""V3.0: upgrade Product Analyst prompts to v3 (Nuotao Score guidance).

Inserts the v3 prompt for both logical names (PRODUCT_ANALYST for the direct
API path, AGENT_PRODUCT_ANALYST for the bound agent runtime), archives older
versions, and rebinds the registered product_analyst agent to v3. Idempotent.
The template text is shared from app.agents.product_analyst_prompt so code and
migration cannot drift. SQL uses inline escaped literals (same proven approach
as 0049) to avoid Alembic op.execute parameter-binding differences.
"""

import json

import sqlalchemy as sa
from alembic import op

from app.agents.product_analyst_prompt import (
    PRODUCT_ANALYST_TEMPLATE_V3,
    PROMPT_NAMES,
    PROMPT_VARIABLES,
    PROMPT_VERSION_V3,
)

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None

WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"


def _quote(value) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def upgrade() -> None:
    variables_literal = _quote(json.dumps(PROMPT_VARIABLES)) + "::jsonb"
    for index, name in enumerate(PROMPT_NAMES, start=1):
        prompt_id = f"00000000-0050-0000-0000-{index:012d}"
        op.execute(
            sa.text(
                f"""
                INSERT INTO prompts (
                    id, workspace_id, prompt_id, name, version, template,
                    variables, status, description
                ) VALUES (
                    {_quote(prompt_id)}, {_quote(WORKSPACE_ID)}, {_quote(name)},
                    {_quote(name)}, {_quote(PROMPT_VERSION_V3)},
                    {_quote(PRODUCT_ANALYST_TEMPLATE_V3)},
                    {variables_literal}, 'active',
                    'Product Analyst v3 (Nuotao Score V3.0: 6-dim + V1/V2/V3/V5)'
                )
                ON CONFLICT ON CONSTRAINT uq_prompts_workspace_name_version DO UPDATE
                    SET template = EXCLUDED.template,
                        variables = EXCLUDED.variables,
                        status = 'active'
                """
            )
        )
        op.execute(
            sa.text(
                f"""
                UPDATE prompts
                   SET status = 'archived'
                 WHERE workspace_id = {_quote(WORKSPACE_ID)}
                   AND name = {_quote(name)}
                   AND version <> {_quote(PROMPT_VERSION_V3)}
                """
            )
        )

    op.execute(
        sa.text(
            f"""
            UPDATE agents
               SET prompt_version = {_quote(PROMPT_VERSION_V3)}
             WHERE workspace_id = {_quote(WORKSPACE_ID)}
               AND agent_id = 'product_analyst'
            """
        )
    )


def downgrade() -> None:
    for name in PROMPT_NAMES:
        op.execute(
            sa.text(
                f"""
                DELETE FROM prompts
                 WHERE workspace_id = {_quote(WORKSPACE_ID)}
                   AND name = {_quote(name)}
                   AND version = {_quote(PROMPT_VERSION_V3)}
                """
            )
        )
        op.execute(
            sa.text(
                f"""
                UPDATE prompts
                   SET status = 'active'
                 WHERE workspace_id = {_quote(WORKSPACE_ID)}
                   AND name = {_quote(name)}
                   AND version = 'v1'
                """
            )
        )
    op.execute(
        sa.text(
            f"""
            UPDATE agents
               SET prompt_version = 'v1'
             WHERE workspace_id = {_quote(WORKSPACE_ID)}
               AND agent_id = 'product_analyst'
            """
        )
    )
