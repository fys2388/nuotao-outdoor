"""Tests for the Prompt Registry (M2.2): versioning + rendering."""

import pytest
from app.core.workspace import DEFAULT_WORKSPACE_ID
from app.schemas.prompt import PromptCreate
from app.services import prompt_registry
from app.services.prompt_registry import (
    PromptConflictError,
    PromptNotFoundError,
    PromptRegistryError,
)

WORKSPACE = DEFAULT_WORKSPACE_ID

TEMPLATE_V1 = (
    "Analyze product {context_json} against schema {output_schema}."
)
TEMPLATE_V2 = (
    "Analyze product {context_json} against schema {output_schema} (v2)."
)


def _data(**overrides) -> PromptCreate:
    values = dict(
        prompt_id="PRODUCT_ANALYST",
        name="PRODUCT_ANALYST",
        version="v1",
        template=TEMPLATE_V1,
        variables=["context_json", "output_schema"],
        status="active",
        description="test prompt",
    )
    values.update(overrides)
    return PromptCreate(**values)


@pytest.mark.asyncio
async def test_create_and_list_prompts(db_session) -> None:
    """A registered prompt is persisted and listed."""
    created = await prompt_registry.create_prompt(
        db_session, workspace_id=WORKSPACE, data=_data()
    )
    assert created.name == "PRODUCT_ANALYST"
    assert created.version == "v1"
    assert created.status == "active"

    rows = await prompt_registry.list_prompts(
        db_session, workspace_id=WORKSPACE, name="PRODUCT_ANALYST"
    )
    assert len(rows) == 1
    assert rows[0].id == created.id


@pytest.mark.asyncio
async def test_prompt_version_conflict(db_session) -> None:
    """Registering the same (name, version) twice conflicts."""
    await prompt_registry.create_prompt(db_session, workspace_id=WORKSPACE, data=_data())
    with pytest.raises(PromptConflictError):
        await prompt_registry.create_prompt(db_session, workspace_id=WORKSPACE, data=_data())


@pytest.mark.asyncio
async def test_get_active_prompt_prefers_latest_version(db_session) -> None:
    """Only the newest active version is returned."""
    await prompt_registry.create_prompt(db_session, workspace_id=WORKSPACE, data=_data())
    await prompt_registry.create_prompt(
        db_session, workspace_id=WORKSPACE, data=_data(version="v2", template=TEMPLATE_V2)
    )
    active = await prompt_registry.get_active_prompt(
        db_session, workspace_id=WORKSPACE, name="PRODUCT_ANALYST"
    )
    assert active.version == "v2"
    assert "v2" in active.template


@pytest.mark.asyncio
async def test_get_active_prompt_missing(db_session) -> None:
    """A missing active prompt raises PromptNotFoundError."""
    with pytest.raises(PromptNotFoundError):
        await prompt_registry.get_active_prompt(
            db_session, workspace_id=WORKSPACE, name="NOPE"
        )


@pytest.mark.asyncio
async def test_render_prompt_validates_variables(db_session) -> None:
    """Rendering rejects missing declared variables and undeclared placeholders."""
    await prompt_registry.create_prompt(db_session, workspace_id=WORKSPACE, data=_data())
    rendered = await prompt_registry.render_prompt(
        db_session,
        workspace_id=WORKSPACE,
        name="PRODUCT_ANALYST",
        variables={"context_json": '{"x": 1}', "output_schema": "{}"},
    )
    assert "{" in rendered.text
    assert rendered.prompt.version == "v1"

    with pytest.raises(PromptRegistryError) as exc_info:
        await prompt_registry.render_prompt(
            db_session,
            workspace_id=WORKSPACE,
            name="PRODUCT_ANALYST",
            variables={"context_json": '{"x": 1}'},
        )
    assert "output_schema" in str(exc_info.value)


@pytest.mark.asyncio
async def test_create_prompt_rejects_undeclared_placeholders(db_session) -> None:
    """A template placeholder not declared in variables is rejected."""
    with pytest.raises(PromptRegistryError) as exc_info:
        await prompt_registry.create_prompt(
            db_session,
            workspace_id=WORKSPACE,
            data=_data(
                template="Uses {context_json} and {secret_var}",
                variables=["context_json", "output_schema"],
            ),
        )
    assert "secret_var" in str(exc_info.value)
