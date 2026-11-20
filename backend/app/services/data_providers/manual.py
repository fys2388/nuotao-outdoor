"""人工采集 Provider（D8-F P0-3）：不依赖 Cookie/API 的标准化商品建档入口。

## 为什么需要它

审计发现现有真实商品数据被 ``scrape_1688``（浏览器 Cookie）单点卡死：Cookie 过期即
拿不到任何真实数据，而官方 API 又被 GMV 门槛挡住，导致长期靠 ``_KNOWN_PRODUCTS``
伪造兜底。人工采集是**不依赖任何外部凭据**的标准化来源：运营/Owner 在管理端按表单
录入真实观察到的商品信息，系统按统一 Provider 契约归一化 + 校验 + 记录来源追溯。

## 关键语义：is_real=True 但 evidence_grade=E0

- ``is_real=True``：人工录入是**真实观察**（人看到真实商品页/实物后录入），不是
  ``_KNOWN_PRODUCTS`` 那种过期快照/伪造兜底，因此**可进入自动化决策链路**。
- ``evidence_grade=E0``：人工录入初始只有商品基础信息（名称/价格/图片/描述），
  **不能做利润结论**（需 E1 采购价核对）、**不能做完整落地成本**（需 E2 实测重量）。
  升级必须逐级补证（E0→E1→E2…），禁止跳跃——与 M334 E0-E5 铁律一致。

这样既摆脱了 Cookie 单点，又不违反「缺失来源信息的数据不得进入自动化决策」：
来源是明确的（manual + 录入人 + 时间 + 可选 source_url），真实性是可追溯的。

设计详见 ``D8F_ARCHITECTURE.md`` §2.1。
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.services.data_providers.base import (
    EvidenceGrade,
    FieldProvenance,
    ProductProvenance,
    ProviderResult,
    ValidationResult,
)

logger = logging.getLogger(__name__)

# 占位名黑名单（与 product_pipeline_service generic 判定一致，防人工误填占位）
_PLACEHOLDER_NAMES = {"1688 Product", "1688产品", "Product", "商品", "", "test", "测试"}


class ManualProvider:
    """人工商品建档 Provider。``is_available()`` 恒 True（不依赖任何外部凭据）。"""

    name = "manual"

    def __init__(self, collected_by: str = "operator") -> None:
        # collected_by 应为录入人 user_id，用于审计追溯
        self._collected_by = collected_by

    def is_available(self) -> bool:
        """人工采集不依赖 Cookie/API，恒可用。"""
        return True

    def collect(self, url_or_id: str, *, fields: dict[str, Any] | None = None) -> ProviderResult:
        """从人工录入构造 ProviderResult。

        Args:
            url_or_id: 可选的 1688 链接或 offer id（人工录入时可空）。
            fields: 录入字段（name/price/sku/images/description/attributes/...）。

        Returns:
            ProviderResult：归一化 + 校验 + 来源追溯；结构不合规时 ok=False（fail-closed）。
        """
        fields = fields or {}
        trace_id = str(uuid4())
        product_id = self._extract_offer_id(url_or_id) if url_or_id else None

        normalized = self.normalize(fields)
        validation = self.validate(normalized)
        if not validation.is_valid:
            return ProviderResult(
                ok=False,
                data=None,
                provenance=None,
                degraded=False,
                fail_closed_reason="; ".join(validation.reasons),
            )

        provenance = ProductProvenance(
            provider=self.name,
            source_reference=product_id,
            source_url=url_or_id or None,
            collected_at=datetime.now(UTC),
            collected_by=self._collected_by,
            trace_id=trace_id,
            evidence_grade=validation.evidence_grade,  # 人工录入初始 E0
            is_real=True,  # 真实观察，非伪造兜底
            degraded_reason=None,
            field_provenance=self._field_provenance(normalized),
        )

        normalized["provenance"] = provenance.to_meta()
        return ProviderResult(ok=True, data=normalized, provenance=provenance, degraded=False)

    def normalize(self, raw: dict[str, Any]) -> dict[str, Any]:
        """归一化人工录入字段为统一商品结构。"""
        price = raw.get("price")
        price_str = str(price) if price not in (None, "") else "0"
        images = raw.get("images") or []
        if isinstance(images, str):
            images = [images]
        return {
            "name": (raw.get("name") or raw.get("subject") or raw.get("title") or "").strip(),
            "price": price_str,
            "sku_list": raw.get("sku_list") or raw.get("variations") or [],
            "images": images,
            "description": raw.get("description") or "",
            "attributes": raw.get("attributes") or [],
            "category": raw.get("category") or "",
            "source_url": raw.get("source_url") or "",
        }

    def validate(self, normalized: dict[str, Any]) -> ValidationResult:
        """校验人工录入真实性。人工录入是真实观察，但结构必须完整（名称+正价格）。"""
        reasons: list[str] = []
        name = normalized.get("name", "")
        # 占位名黑名单（拦"1688 Product"/"商品"等无信息占位），+ 极短名兜底。
        # 不用 len<10（对英文合法短名如 "Cup"/"Mat" 会误杀）——审计原则是拦
        # 占位名，不是拦短名；D8-F(审计 R1) 登录墙占位由黑名单 + 来源闸门覆盖。
        if name in _PLACEHOLDER_NAMES or len(name) < 2:
            reasons.append(f"商品名称缺失或为占位值: {name!r}")

        price_raw = normalized.get("price", "0")
        try:
            price = float(price_raw)
        except (TypeError, ValueError):
            price = 0.0
        if price <= 0:
            # 与审计 N1（price=35.8 伪造）反向对齐：价格为空/0 必须显式缺失，不得伪造
            reasons.append(f"价格缺失或非正数: {price_raw!r}（人工录入不得伪造价格）")

        return ValidationResult(
            is_valid=not reasons,
            reasons=reasons,
            # 人工录入初始 E0：仅基础信息，不可做利润结论，需逐级补证
            evidence_grade=EvidenceGrade.E0,
        )

    def get_provenance(self, product_id: str) -> ProductProvenance:
        """返回占位 provenance（实际采集时的 provenance 由 collect 返回并落库）。"""
        return ProductProvenance(
            provider=self.name,
            source_reference=product_id,
            collected_by=self._collected_by,
            evidence_grade=EvidenceGrade.E0,
            is_real=True,
        )

    def _field_provenance(self, normalized: dict[str, Any]) -> dict[str, FieldProvenance]:
        """为关键字段记录字段级来源（人工录入=已核实，来自录入人真实观察）。"""
        now = datetime.now(UTC)
        fields = ("name", "price", "images", "description")
        return {
            key: FieldProvenance(
                value=normalized.get(key),
                provider=self.name,
                collected_at=now,
                is_verified=True,  # 人工录入=录入人真实观察
                raw_evidence_ref=None,
            )
            for key in fields
            if normalized.get(key) not in (None, "", [])
        }

    @staticmethod
    def _extract_offer_id(url_or_id: str) -> str | None:
        """从链接或 ID 提取 1688 数字 offer id；提取不到返回 None。"""
        digits = re.sub(r"\D", "", url_or_id)
        return digits or None
