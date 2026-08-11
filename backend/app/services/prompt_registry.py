"""Prompt registry service (M2.2): versioned prompts, never hardcoded.

Prompts live in the ``prompts`` table. ``get_active_prompt`` returns the
newest active version of a named prompt; ``render_prompt`` substitutes
``{variable}`` placeholders and rejects undeclared/missing variables so a
template typo fails loudly instead of silently degrading an LLM call.
"""

import logging
import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prompt import Prompt
from app.schemas.prompt import PromptCreate

logger = logging.getLogger(__name__)

_PLACEHOLDER = re.compile(r"\{([a-zA-Z0-9_]+)\}")


class PromptRegistryError(Exception):
    """Raised on invalid prompt registry operations."""


class PromptConflictError(PromptRegistryError):
    """Raised when a (name, version) already exists."""


class PromptNotFoundError(PromptRegistryError):
    """Raised when no active version of a named prompt exists."""


def _declare_version(base: str) -> str:
    """Bump a ``vN`` version (v1 -> v2); used by create helpers."""
    try:
        number = int(base.removeprefix("v"))
    except ValueError:
        return "v2"
    return f"v{number + 1}"


async def create_prompt(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    data: PromptCreate,
    trace_id: str | None = None,
) -> Prompt:
    """Register a new versioned prompt (unique workspace/name/version)."""
    declared = set(data.variables)
    found = set(_PLACEHOLDER.findall(data.template))
    undeclared = found - declared
    if undeclared:
        raise PromptRegistryError(
            f"template placeholders not declared in variables: {sorted(undeclared)}"
        )
    if not declared.issubset(found):
        raise PromptRegistryError(
            "declared variables missing from template: "
            f"{sorted(declared - found)}"
        )

    prompt = Prompt(
        workspace_id=workspace_id,
        prompt_id=data.prompt_id,
        name=data.name,
        version=data.version,
        template=data.template,
        variables=data.variables,
        status=data.status,
        description=data.description,
        trace_id=trace_id,
    )
    session.add(prompt)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise PromptConflictError(
            f"prompt '{data.name}' version '{data.version}' already exists"
        ) from exc
    await session.refresh(prompt)
    return prompt


async def list_prompts(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    name: str | None = None,
    limit: int = 100,
) -> list[Prompt]:
    """List prompts (optionally filtered by name), newest version first."""
    stmt = select(Prompt).where(Prompt.workspace_id == workspace_id)
    if name:
        stmt = stmt.where(Prompt.name == name)
    stmt = stmt.order_by(Prompt.name, Prompt.version.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)


async def get_active_prompt(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    name: str,
) -> Prompt:
    """Return the newest active version of a named prompt.

    Raises:
        PromptNotFoundError: when no active version exists.
    """
    rows = (
        await session.execute(
            select(Prompt)
            .where(
                Prompt.workspace_id == workspace_id,
                Prompt.name == name,
                Prompt.status == "active",
            )
            .order_by(Prompt.version.desc())
        )
    ).scalars().all()
    if not rows:
        raise PromptNotFoundError(f"no active prompt '{name}' found")
    return rows[0]


@dataclass(frozen=True)
class RenderedPrompt:
    """A rendered prompt with its registry metadata."""

    prompt: Prompt
    variables: dict[str, str]
    text: str


async def render_prompt(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    name: str,
    variables: dict[str, Any],
    trace_id: str | None = None,
) -> RenderedPrompt:
    """Load the active prompt and render it with validated variables.

    All declared variables must be supplied; undeclared extra variables are
    ignored. Values are stringified for substitution.
    """
    prompt = await get_active_prompt(session, workspace_id=workspace_id, name=name)
    declared = set(prompt.variables or [])
    missing = declared - set(variables)
    if missing:
        raise PromptRegistryError(
            f"prompt '{name}' missing variables: {sorted(missing)}"
        )
    stringified = {key: str(value) for key, value in variables.items()}
    rendered = prompt.template.format(**stringified)
    return RenderedPrompt(prompt=prompt, variables=stringified, text=rendered)
