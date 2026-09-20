"""API schemas for customer identity, consent, merge, and privacy workflows."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.core.privacy import assert_no_pii

IdentityType = Literal[
    "email",
    "phone",
    "woocommerce_customer_id",
    "company_tax_id",
    "other",
]
IdentityChannel = Literal[
    "b2c_store",
    "b2b_portal",
    "email",
    "support",
    "crm",
    "other",
]
ConsentPurpose = Literal[
    "marketing_email",
    "transactional_email",
    "analytics",
    "personalization",
    "ai_processing",
]
ConsentStatus = Literal["granted", "withdrawn"]
DataSubjectRequestType = Literal["access", "export", "delete", "correct", "restrict"]


class CustomerAccountResponse(BaseModel):
    id: UUID
    customer_number: str
    customer_type: str
    business_model: str
    display_name: str | None = None
    status: str
    country: str | None = None
    default_currency: str
    merged_into_account_id: UUID | None = None
    merged_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class IdentityLinkCreate(BaseModel):
    customer_account_id: UUID
    identity_type: IdentityType
    identity_value: str = Field(min_length=3, max_length=512)
    channel: IdentityChannel
    external_system: str = Field(min_length=1, max_length=64)
    source: str = Field(default="manual", min_length=1, max_length=64)
    metadata: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_pii_metadata(self) -> IdentityLinkCreate:
        assert_no_pii(self.metadata, field_name="identity metadata")
        return self


class IdentityResolveRequest(BaseModel):
    identity_type: IdentityType
    identity_value: str = Field(min_length=3, max_length=512)
    channel: IdentityChannel = "crm"
    external_system: str = Field(default="manual", min_length=1, max_length=64)
    create_if_missing: bool = False
    customer_type: str = Field(default="CONSUMER", min_length=2, max_length=32)
    business_model: Literal["B2C", "B2B", "BOTH"] = "B2C"
    display_name: str | None = Field(default=None, max_length=255)
    country: str | None = Field(default=None, max_length=8)
    default_currency: str = Field(default="USD", min_length=3, max_length=8)


class IdentityResolveResponse(BaseModel):
    resolved: bool
    account: CustomerAccountResponse | None = None
    conflict_account_id: UUID | None = None


class IdentityLinkResponse(BaseModel):
    id: UUID
    customer_account_id: UUID
    channel: str
    external_system: str
    identity_type: str
    fingerprint: str
    hash_key_version: str
    verification_status: str
    source: str
    verified_at: datetime | None = None
    last_seen_at: datetime | None = None
    disabled_at: datetime | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class IdentityLinkListResponse(BaseModel):
    items: list[IdentityLinkResponse]
    total: int


class AccountMergeCreate(BaseModel):
    source_account_id: UUID
    target_account_id: UUID
    reason: str = Field(min_length=10, max_length=2000)


class AccountMergeDecision(BaseModel):
    reason: str | None = Field(default=None, max_length=2000)


class AccountMergeResponse(BaseModel):
    id: UUID
    source_account_id: UUID
    target_account_id: UUID
    status: str
    match_type: str
    match_hash_prefix: str
    evidence: dict = Field(default_factory=dict)
    reason: str
    requested_by: str
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    rejection_reason: str | None = None
    completed_by: str | None = None
    completed_at: datetime | None = None
    result_summary: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class AccountMergeListResponse(BaseModel):
    items: list[AccountMergeResponse]
    total: int


class ConsentEventCreate(BaseModel):
    customer_account_id: UUID
    purpose: ConsentPurpose
    channel: IdentityChannel
    status: ConsentStatus
    policy_version: str = Field(min_length=1, max_length=64)
    source: str = Field(min_length=1, max_length=64)
    idempotency_key: str = Field(min_length=8, max_length=128)
    evidence: dict = Field(default_factory=dict)
    occurred_at: datetime | None = None

    @model_validator(mode="after")
    def reject_pii_evidence(self) -> ConsentEventCreate:
        assert_no_pii(self.evidence, field_name="consent evidence")
        return self


class ConsentEventResponse(BaseModel):
    id: UUID
    customer_account_id: UUID
    purpose: str
    channel: str
    status: str
    policy_version: str
    source: str
    occurred_at: datetime
    recorded_by: str
    evidence: dict = Field(default_factory=dict)
    created_at: datetime


class ConsentSummaryItem(BaseModel):
    purpose: str
    channel: str
    status: str
    policy_version: str
    source: str
    occurred_at: datetime
    recorded_by: str
    event_id: str


class ConsentSummaryResponse(BaseModel):
    customer_account_id: UUID
    items: list[ConsentSummaryItem]


class ConsentHistoryResponse(BaseModel):
    items: list[ConsentEventResponse]
    total: int


class DataSubjectRequestCreate(BaseModel):
    request_type: DataSubjectRequestType
    customer_account_id: UUID | None = None
    identity_type: IdentityType | None = None
    identity_value: str | None = Field(default=None, min_length=3, max_length=512)
    request_details: str | None = Field(default=None, max_length=5000)
    verification_method: str | None = Field(default=None, max_length=64)
    evidence: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_target(self) -> DataSubjectRequestCreate:
        assert_no_pii(self.evidence, field_name="privacy request evidence")
        if self.customer_account_id is None and not (
            self.identity_type and self.identity_value
        ):
            raise ValueError("customer_account_id or identity is required")
        if (self.identity_type is None) != (self.identity_value is None):
            raise ValueError("identity_type and identity_value must be provided together")
        return self


class DataSubjectRequestActionResponse(BaseModel):
    id: UUID
    action_type: str
    actor: str
    note: str | None = None
    result: dict = Field(default_factory=dict)
    created_at: datetime


class DataSubjectRequestResponse(BaseModel):
    id: UUID
    request_number: str
    customer_account_id: UUID | None = None
    request_type: str
    status: str
    identity_hash_prefix: str | None = None
    verification_method: str | None = None
    verified_by: str | None = None
    verified_at: datetime | None = None
    due_at: datetime
    handled_by: str | None = None
    decided_at: datetime | None = None
    completed_at: datetime | None = None
    rejection_reason: str | None = None
    request_details: str | None = None
    result_summary: dict = Field(default_factory=dict)
    evidence: dict = Field(default_factory=dict)
    requested_by: str
    created_at: datetime
    updated_at: datetime


class DataSubjectRequestListResponse(BaseModel):
    items: list[DataSubjectRequestResponse]
    total: int


class DataSubjectRequestDetailResponse(DataSubjectRequestResponse):
    actions: list[DataSubjectRequestActionResponse]


class DataSubjectRequestVerify(BaseModel):
    verification_method: str = Field(min_length=2, max_length=64)
    note: str | None = Field(default=None, max_length=2000)


class DataSubjectRequestDecision(BaseModel):
    note: str | None = Field(default=None, max_length=5000)


class DataSubjectRequestReject(BaseModel):
    reason: str = Field(min_length=2, max_length=5000)


class DataSubjectRequestExecute(BaseModel):
    note: str | None = Field(default=None, max_length=5000)


class CustomerDataStatsResponse(BaseModel):
    accounts: int
    conflicts: int
    pending_merges: int
    requests: dict[str, int]
