"""Product import request/response schemas."""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ImportRowError(BaseModel):
    """One failed CSV row."""

    row: int
    message: str


class ProductImportResult(BaseModel):
    """Summary of a CSV product import run."""

    imported: int
    updated: int
    failed: int
    errors: list[ImportRowError] = Field(default_factory=list)


class ProductOut(BaseModel):
    """Product as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    sku: str
    name: str
    description: str | None
    category: str | None
    brand: str | None
    status: str
    candidate_status: str | None = None
    # V3.0 独立评分漏斗阶段（rejected/test_candidate/testing/hero 等），
    # 以及一票否决时的失败规则快照，供前端在推送前做本地硬阻断展示。
    funnel_stage: str | None = None
    reject_reasons: list[Any] = Field(default_factory=list)
    source: str
    source_url: str | None
    tags: list[Any]
    attributes: dict[str, Any]
    meta: dict[str, Any]
    weight_kg: Decimal | None
    dimensions: dict[str, Any] | None
    target_market: str
    # Product Master creation info (Phase 3A).
    mastered_at: datetime | None = None
    mastered_by: str | None = None
    mastered_trace_id: str | None = None
    # V3.0 data integrity tracking (Phase 1 of V3 evaluation fix).
    # NULL until the first integrity check runs; the V3 selection pipeline
    # uses these to decide whether a candidate has enough data to score.
    data_integrity_status: str | None = None
    data_integrity_score: Decimal | None = None
    data_integrity_missing: list[Any] = Field(default_factory=list)
    data_integrity_checked_at: datetime | None = None
    data_integrity_trace_id: str | None = None
    data_integrity_version: str = "v1"
    created_at: datetime
    updated_at: datetime


class ProductLifecycleItem(BaseModel):
    """下架 / 恢复 / 彻底删除的单项结果。"""

    product_id: UUID
    sku: str | None = None
    success: bool
    # unpublished | restored | updated | already_set | already_absent
    # | skipped | deleted | failed | blocked | not_found
    action: str
    woocommerce_id: int | None = None
    woocommerce_status: str | None = None
    verified: bool = False
    error: str | None = None
    message: str | None = None


class ProductBatchDeleteRequest(BaseModel):
    """Request body for batch-deleting products（移入回收站）。

    ``force_local`` 在 WooCommerce 下架失败时仍然只处理本地。默认 ``False``：
    下架失败即中止，避免产生「系统已移入回收站、店铺仍在售」的幽灵商品。
    """

    product_ids: list[UUID] = Field(min_length=1, max_length=500)
    force_local: bool = False


class ProductBatchIdsRequest(BaseModel):
    """Request body carrying only product ids（恢复 / 彻底删除）。"""

    product_ids: list[UUID] = Field(min_length=1, max_length=200)


class ProductDeleteResult(BaseModel):
    """下架（移入回收站）结果。

    本地与 WooCommerce 是两件事，必须分别如实汇报，否则「已删除」会掩盖
    「商品仍在店铺在售」的事实。
    """

    deleted: int
    not_found: list[UUID] = Field(default_factory=list)
    wc_unpublished: int = 0
    wc_unpublish_failed: list[ProductLifecycleItem] = Field(default_factory=list)
    blocked: bool = False
    message: str | None = None


class ProductRestoreResult(BaseModel):
    """从回收站恢复的结果。"""

    restored: int
    not_found: list[UUID] = Field(default_factory=list)
    wc_restored: int = 0
    wc_restore_failed: list[ProductLifecycleItem] = Field(default_factory=list)
    blocked: bool = False
    message: str | None = None


class ProductPurgeResult(BaseModel):
    """彻底删除的结果。

    - ``purged``：本地行与 WooCommerce 商品都已删除
    - ``blocked``：被 B2B 业务单据引用而拒绝删除（本地与 WC 均未动）
    - ``wc_delete_failed``：本地已删但 WooCommerce 删除失败，需人工清理
      （审计事件与 ``items`` 里留有 ``woocommerce_id``）
    """

    purged: int = 0
    blocked: int = 0
    wc_delete_failed: int = 0
    not_found: list[UUID] = Field(default_factory=list)
    items: list[ProductLifecycleItem] = Field(default_factory=list)
    message: str | None = None


class ProductRecycleBinOut(BaseModel):
    """回收站列表。"""

    items: list[ProductOut] = Field(default_factory=list)
    total: int = 0
