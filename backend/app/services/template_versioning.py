"""Template versioning for prompt management.

Tracks prompt template versions, performance metrics, and allows
rollback to previous versions. Integrates with the SOP Step 7
(模板沉淀) workflow.

Design:
- Templates stored as structured dicts (not files) for easy DB persistence
- Each version has metadata: creator, timestamp, metrics, changelog
- Supports A/B comparison between versions
- Deterministic: no LLM, pure version control logic

Usage:
    from app.services.template_versioning import get_template_service

    service = get_template_service()
    service.create_version(
        template_id="main_image_v2",
        prompt="...",
        changelog="Improved lighting description",
    )
    service.get_latest_version("main_image_v2")
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Template version dataclass
# ---------------------------------------------------------------------------


class VersionStatus(str, Enum):
    """Status of a template version."""

    ACTIVE = "active"
    ARCHIVED = "archived"
    DRAFT = "draft"


@dataclass(frozen=True)
class TemplateVersion:
    """A versioned prompt template."""

    template_id: str
    version: int
    prompt: str
    created_at: float
    created_by: str = ""
    status: VersionStatus = VersionStatus.ACTIVE
    changelog: str = ""
    tags: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        return {
            "template_id": self.template_id,
            "version": self.version,
            "prompt": self.prompt,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "status": self.status.value,
            "changelog": self.changelog,
            "tags": self.tags,
            "metrics": self.metrics,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TemplateVersion:
        """Create from dict."""
        return cls(
            template_id=data["template_id"],
            version=data["version"],
            prompt=data["prompt"],
            created_at=data["created_at"],
            created_by=data.get("created_by", ""),
            status=VersionStatus(data.get("status", "active")),
            changelog=data.get("changelog", ""),
            tags=data.get("tags", []),
            metrics=data.get("metrics", {}),
        )


# ---------------------------------------------------------------------------
# Template service
# ---------------------------------------------------------------------------


class TemplateVersioningService:
    """Service for managing prompt template versions.

    Stores templates in-memory (can be backed by DB later).
    Provides versioning, comparison, and rollback.
    """

    def __init__(self) -> None:
        # template_id -> list[TemplateVersion] (sorted by version)
        self._templates: dict[str, list[TemplateVersion]] = {}
        # Cache: template_id -> latest version number
        self._latest_versions: dict[str, int] = {}

    def create_version(
        self,
        template_id: str,
        prompt: str,
        *,
        created_by: str = "",
        changelog: str = "",
        tags: list[str] | None = None,
        status: VersionStatus = VersionStatus.ACTIVE,
    ) -> TemplateVersion:
        """Create a new version of a template.

        Args:
            template_id: Unique template identifier.
            prompt: The prompt text.
            created_by: Creator name/email.
            changelog: What changed from previous version.
            tags: Optional tags for categorization.
            status: Initial status (active/draft/archived).

        Returns:
            The created TemplateVersion.
        """
        versions = self._templates.get(template_id, [])
        next_version = len(versions) + 1

        version = TemplateVersion(
            template_id=template_id,
            version=next_version,
            prompt=prompt,
            created_at=time.time(),
            created_by=created_by,
            status=status,
            changelog=changelog,
            tags=tags or [],
        )

        if template_id not in self._templates:
            self._templates[template_id] = []
        self._templates[template_id].append(version)
        self._latest_versions[template_id] = next_version

        logger.info(
            "Template version created: %s v%d by %s",
            template_id, next_version, created_by,
        )

        return version

    def get_latest_version(self, template_id: str) -> TemplateVersion | None:
        """Get the latest version of a template."""
        versions = self._templates.get(template_id, [])
        if not versions:
            return None
        return versions[-1]

    def get_version(self, template_id: str, version: int) -> TemplateVersion | None:
        """Get a specific version of a template."""
        versions = self._templates.get(template_id, [])
        for v in versions:
            if v.version == version:
                return v
        return None

    def list_versions(
        self,
        template_id: str,
        *,
        status: VersionStatus | None = None,
    ) -> list[TemplateVersion]:
        """List all versions of a template, optionally filtered by status."""
        versions = self._templates.get(template_id, [])
        if status:
            return [v for v in versions if v.status == status]
        return list(versions)

    def list_all_templates(self) -> dict[str, list[TemplateVersion]]:
        """List all templates and their versions."""
        return {tid: list(vs) for tid, vs in self._templates.items()}

    def archive_version(
        self,
        template_id: str,
        version: int,
        *,
        reason: str = "",
    ) -> bool:
        """Archive a version (keep for history but not usable)."""
        v = self.get_version(template_id, version)
        if not v or v.status == VersionStatus.ARCHIVED:
            return False

        # Create a new archived version (immutable pattern)
        archived = TemplateVersion(
            template_id=v.template_id,
            version=v.version,
            prompt=v.prompt,
            created_at=v.created_at,
            created_by=v.created_by,
            status=VersionStatus.ARCHIVED,
            changelog=f"Archived: {reason}" if reason else "Archived",
            tags=v.tags,
            metrics=v.metrics,
        )
        # Replace in list
        versions = self._templates[template_id]
        for i, existing in enumerate(versions):
            if existing.version == version:
                versions[i] = archived
                break
        return True

    def rollback(
        self,
        template_id: str,
        to_version: int,
        *,
        created_by: str = "",
    ) -> TemplateVersion | None:
        """Rollback to a previous version by creating a new version with old content.

        This preserves history: the new version has the old prompt but a new version number.
        """
        old_version = self.get_version(template_id, to_version)
        if not old_version:
            return None

        # Create a new version with the old prompt
        new_version = self.create_version(
            template_id=template_id,
            prompt=old_version.prompt,
            created_by=created_by,
            changelog=f"Rollback to v{to_version}",
            tags=old_version.tags,
        )
        return new_version

    def update_metrics(
        self,
        template_id: str,
        version: int,
        metrics: dict[str, Any],
    ) -> bool:
        """Update performance metrics for a version."""
        versions = self._templates.get(template_id, [])
        for v in versions:
            if v.version == version:
                # Create updated version (immutable)
                updated = TemplateVersion(
                    template_id=v.template_id,
                    version=v.version,
                    prompt=v.prompt,
                    created_at=v.created_at,
                    created_by=v.created_by,
                    status=v.status,
                    changelog=v.changelog,
                    tags=v.tags,
                    metrics={**v.metrics, **metrics},
                )
                # Replace in list
                for i, existing in enumerate(versions):
                    if existing.version == version:
                        versions[i] = updated
                        break
                return True
        return False

    def compare_versions(
        self,
        template_id: str,
        version_a: int,
        version_b: int,
    ) -> dict[str, Any]:
        """Compare two versions of a template."""
        va = self.get_version(template_id, version_a)
        vb = self.get_version(template_id, version_b)
        if not va or not vb:
            return {"error": "Version not found"}

        return {
            "template_id": template_id,
            "version_a": {
                "version": va.version,
                "prompt_length": len(va.prompt),
                "created_at": va.created_at,
                "metrics": va.metrics,
            },
            "version_b": {
                "version": vb.version,
                "prompt_length": len(vb.prompt),
                "created_at": vb.created_at,
                "metrics": vb.metrics,
            },
            "prompt_changed": va.prompt != vb.prompt,
            "prompt_diff_length": abs(len(va.prompt) - len(vb.prompt)),
        }

    def search_templates(
        self,
        *,
        tag: str | None = None,
        creator: str | None = None,
    ) -> list[TemplateVersion]:
        """Search templates by tag or creator."""
        results: list[TemplateVersion] = []
        for versions in self._templates.values():
            for v in versions:
                if tag and tag not in v.tags:
                    continue
                if creator and creator != v.created_by:
                    continue
                results.append(v)
        return results

    def delete_template(self, template_id: str) -> bool:
        """Delete all versions of a template."""
        if template_id in self._templates:
            del self._templates[template_id]
            self._latest_versions.pop(template_id, None)
            return True
        return False

    def get_stats(self) -> dict[str, Any]:
        """Get template service statistics."""
        total_versions = sum(len(vs) for vs in self._templates.values())
        templates_with_active = sum(
            1 for vs in self._templates.values()
            if any(v.status == VersionStatus.ACTIVE for v in vs)
        )
        return {
            "total_templates": len(self._templates),
            "total_versions": total_versions,
            "templates_with_active": templates_with_active,
        }

    def export(self) -> str:
        """Export all templates as JSON."""
        data = {
            tid: [v.to_dict() for v in versions]
            for tid, versions in self._templates.items()
        }
        return json.dumps(data, indent=2, ensure_ascii=False)

    def import_json(self, json_str: str) -> int:
        """Import templates from JSON. Returns count of imported versions."""
        data = json.loads(json_str)
        count = 0
        for tid, versions in data.items():
            for v_data in versions:
                self.create_version(
                    template_id=tid,
                    prompt=v_data["prompt"],
                    created_by=v_data.get("created_by", ""),
                    changelog=v_data.get("changelog", ""),
                    tags=v_data.get("tags", []),
                    status=VersionStatus(v_data.get("status", "active")),
                )
                count += 1
        return count


# ---------------------------------------------------------------------------
# Global service instance
# ---------------------------------------------------------------------------

_service: TemplateVersioningService | None = None


def get_template_service() -> TemplateVersioningService:
    """Get or create the global template versioning service."""
    global _service
    if _service is None:
        _service = TemplateVersioningService()
    return _service


# ---------------------------------------------------------------------------
# Predefined template categories
# ---------------------------------------------------------------------------

TEMPLATE_CATEGORIES = {
    "main_image": "主图生成 Prompt",
    "gallery_image": "附图生成 Prompt",
    "scene_image": "场景图生成 Prompt",
    "detail_image": "详情图生成 Prompt",
    "description": "产品描述文案",
    "title": "产品标题",
    "seo": "SEO 优化",
}


def create_initial_templates() -> None:
    """Create initial template versions for common use cases."""
    service = get_template_service()

    # Main image template
    service.create_version(
        template_id="main_image_v1",
        prompt=(
            "Professional product photography, {product_name}, "
            "{color} color, centered on pure white background, "
            "soft studio lighting, high resolution, "
            "no text, no watermark, no logo"
        ),
        created_by="system",
        changelog="Initial main image template",
        tags=["main_image", "v1"],
    )

    # Gallery image template
    service.create_version(
        template_id="gallery_image_v1",
        prompt=(
            "Product lifestyle scene, {product_name}, "
            "{scene_description}, natural lighting, "
            "professional photography, no text"
        ),
        created_by="system",
        changelog="Initial gallery image template",
        tags=["gallery_image", "v1"],
    )

    # Description template
    service.create_version(
        template_id="description_v1",
        prompt=(
            "Write a compelling product description for {product_name}. "
            "Include: key features, benefits, use cases. "
            "Tone: professional, engaging. Length: 150-200 words."
        ),
        created_by="system",
        changelog="Initial description template",
        tags=["description", "v1"],
    )


def format_template_report(service: TemplateVersioningService) -> str:
    """Format template service stats as a report."""
    stats = service.get_stats()
    lines = [
        "Template Versioning Report",
        f"  Templates: {stats['total_templates']}",
        f"  Total versions: {stats['total_versions']}",
        f"  With active versions: {stats['templates_with_active']}",
    ]
    return "\n".join(lines)
