"""统一商品数据 Provider 接口与来源追溯模型（D8-F P0-3）。

## 为什么需要这个抽象

审计（``D8F_P0_DATA_TRUST_AUDIT.md``）发现：现有商品数据只有一个隐式入口
（``scrape_1688`` + ``_KNOWN_PRODUCTS`` 兜底），数据来源标记 ``data_source`` 只在
``import_from_1688`` 单个函数体内读一次，离开即失传，下游选品/利润分析/上架全程
"失明"，导致 fallback 假数据、登录墙占位、伪造价格（price=35.8）都能以
``success=True`` 流转。

本模块把「商品数据来源」变成一等公民：

1. **统一接口** ``I1688ProductProvider``：所有采集途径（人工/浏览器 Cookie/官方 API）
   实现同一套 ``collect / normalize / validate / get_provenance``，业务层不再写
   if/else 分叉，新增来源只需注册新 Provider。
2. **字段级来源追溯** ``ProductProvenance`` / ``FieldProvenance``：每次采集记录
   provider / source_reference / collected_at / evidence_grade / trace_id /
   field_provenance，使「商品级真实 ≠ 字段级真实」可表达。
3. **真假严格隔离** ``ProviderResult``：``ok=False`` 时 ``data=None``——拿不到可信
   真实数据即失败，**绝不返回 success=True + 假数据**（fail-closed）。
4. **接入现有 E0-E5 证据等级**（``reports/b2m/M334_EVIDENCE_GRADE_SYSTEM.md``），
   不另起证据标准；采集时按来源赋初始等级，禁止跳跃升级。

注意区分两套证据体系：**采购 SKU 用 E0-E5**（本模块 ``EvidenceGrade``）；
**市场研究证据用 A-E**（MarketResearch SOP，与本模块无关）。

设计详见 ``D8F_ARCHITECTURE.md`` §2/§3/§5。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class EvidenceGrade(str, Enum):
    """采购 SKU 证据等级（复用 M334 E0-E5，禁止跳跃升级）。

    采集时按来源赋**初始等级**；升级必须逐级并归档证据文件。
    禁止降级使用：E 级不达标不得做对应动作（E0 不能做利润结论等）。
    """

    E0 = "E0"  # 仅有商品基础信息（名称/链接/图片）——可上架展示，不能做利润结论
    E1 = "E1"  # 采购资料已核对（1688 采购价已记录 + 供应商确认）
    E2 = "E2"  # 采购+物流完备（采购价 + 净重/毛重/包装尺寸已实测）
    E3 = "E3"  # HTSUS 已核实（报关行正式归类意见书）
    E4 = "E4"  # 完整落地成本（货代 DDP 报价 + 关税清关明细已确认）
    E5 = "E5"  # 经营利润确认（实际订单 + 进口费用 + 售后数据已回收）


# 采集方式 / Provider 名（区别于 products.source 的来源类别 manual/1688/woocommerce）
PROVIDER_MANUAL = "manual"
PROVIDER_BROWSER_COOKIE = "browser_cookie"
PROVIDER_OFFICIAL_API = "official_api"


class FieldProvenance(BaseModel):
    """单个字段的来源与证据状态。

    商品级真实不等于字段级真实：例如价格字段来自人工核对（E1）而重量字段仍是
    未实测占位，必须在字段级分别标记，避免整商品被误当已核实。
    """

    value: Any = None
    provider: str
    collected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    is_verified: bool = False
    raw_evidence_ref: str | None = None  # 原始页面片段/截图引用（不含凭据）


class ProductProvenance(BaseModel):
    """商品级来源追溯。每次采集必带，是「数据能否进入自动化决策」的唯一判据。"""

    provider: str
    source_reference: str | None = None  # 1688 offer_id / 人工录入单号
    source_url: str | None = None
    collected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    collected_by: str = "system"  # user_id 或 "system:<provider>"
    trace_id: str | None = None  # 贯穿采集→分析→上架
    evidence_grade: EvidenceGrade = EvidenceGrade.E0
    field_provenance: dict[str, FieldProvenance] = Field(default_factory=dict)
    is_real: bool = False  # 终极判据：能否进入选品/利润/上架/采购
    degraded_reason: str | None = None  # 非真实时必填原因

    def to_meta(self) -> dict[str, Any]:
        """序列化为可写入 product_info['provenance'] / products.provenance 的 dict。"""
        return {
            "provider": self.provider,
            "source_reference": self.source_reference,
            "source_url": self.source_url,
            "collected_at": self.collected_at.isoformat(),
            "collected_by": self.collected_by,
            "trace_id": self.trace_id,
            "evidence_grade": self.evidence_grade.value,
            "is_real": self.is_real,
            "degraded_reason": self.degraded_reason,
            "field_provenance": {
                k: {
                    "provider": v.provider,
                    "collected_at": v.collected_at.isoformat(),
                    "is_verified": v.is_verified,
                    "raw_evidence_ref": v.raw_evidence_ref,
                }
                for k, v in self.field_provenance.items()
            },
        }


class ValidationResult(BaseModel):
    """validate() 结果。fail-closed：不通过即 is_valid=False + 原因。"""

    is_valid: bool = False
    reasons: list[str] = Field(default_factory=list)
    evidence_grade: EvidenceGrade = EvidenceGrade.E0


class ProviderResult(BaseModel):
    """统一采集结果。``ok=False`` 时 ``data=None``（fail-closed，绝无假数据）。"""

    ok: bool = False
    data: dict[str, Any] | None = None
    provenance: ProductProvenance | None = None
    degraded: bool = False  # 是否降级（estimated/fallback/占位）
    fail_closed_reason: str | None = None


@runtime_checkable
class I1688ProductProvider(Protocol):
    """所有 1688 商品数据来源的统一接口。

    实现方：ManualProvider（人工建档，不依赖 Cookie/API）、BrowserCookieProvider
    （包装现有 scrape_1688）、OfficialApiProvider（包装 sourcing_1688，GMV 达标后启用）。
    业务层只依赖本接口，新增来源只需注册新 Provider（满足 D8-F「平滑切换 + 不改
    Agent 业务接口」）。
    """

    name: str

    def is_available(self) -> bool:
        """该 Provider 当前是否可用（如 Cookie 是否有效、凭证是否配置）。"""
        ...

    def collect(self, url_or_id: str) -> ProviderResult:
        """采集原始商品数据。拿不到可信真实数据必须返回 ok=False（fail-closed）。"""
        ...

    def normalize(self, raw: Any) -> dict[str, Any]:
        """把原始数据归一化为统一商品结构。"""
        ...

    def validate(self, normalized: dict[str, Any]) -> ValidationResult:
        """校验归一化数据真实性（占位名/价格为空/规格缺失等），赋证据等级。"""
        ...

    def get_provenance(self, product_id: str) -> ProductProvenance:
        """返回该商品的来源追溯。"""
        ...
