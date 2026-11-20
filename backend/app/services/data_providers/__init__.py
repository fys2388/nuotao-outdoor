"""统一商品数据 Provider 层（D8-F P0-3）。

见 ``base.py``（接口与来源追溯模型）与 ``manual.py``（人工采集 Provider）。
设计详见 ``D8F_ARCHITECTURE.md``。
"""

from __future__ import annotations

from app.services.data_providers.base import (
    EvidenceGrade,
    FieldProvenance,
    I1688ProductProvider,
    ProductProvenance,
    ProviderResult,
    ValidationResult,
)
from app.services.data_providers.manual import ManualProvider

__all__ = [
    "EvidenceGrade",
    "FieldProvenance",
    "I1688ProductProvider",
    "ManualProvider",
    "ProductProvenance",
    "ProviderResult",
    "ValidationResult",
]
