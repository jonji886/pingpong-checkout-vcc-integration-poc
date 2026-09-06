from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    role: Mapped[str] = mapped_column(String(32), default="developer")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CreditAccount(Base):
    __tablename__ = "credit_accounts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    credit_unit: Mapped[str] = mapped_column(String(32), default="USD_CREDIT")
    posted_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    available_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class CreditLedger(Base):
    __tablename__ = "credit_ledgers"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_credit_ledger_idempotency"),
        UniqueConstraint("reference_type", "reference_id", "entry_type", name="uq_credit_ledger_reference"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("credit_accounts.id"), index=True)
    entry_type: Mapped[str] = mapped_column(String(32))
    credit_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    fiat_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    fiat_currency: Mapped[str] = mapped_column(String(3))
    pricing_rule_version: Mapped[str] = mapped_column(String(64), default="P0_USD_1_TO_1")
    reference_type: Mapped[str] = mapped_column(String(64))
    reference_id: Mapped[str] = mapped_column(String(64))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CreditHold(Base):
    __tablename__ = "credit_holds"
    __table_args__ = (UniqueConstraint("refund_id", name="uq_credit_hold_refund"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("credit_accounts.id"), index=True)
    refund_id: Mapped[str] = mapped_column(ForeignKey("refund_orders.id"), unique=True)
    credit_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    status: Mapped[str] = mapped_column(String(16), default="HELD")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    released_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ApiIdempotency(Base):
    __tablename__ = "api_idempotencies"
    __table_args__ = (UniqueConstraint("actor_id", "method", "canonical_route", "key_hash", name="uq_api_idem"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    actor_id: Mapped[str] = mapped_column(String(64), index=True)
    method: Mapped[str] = mapped_column(String(16))
    canonical_route: Mapped[str] = mapped_column(String(255))
    key_hash: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(128))
    resource_type: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="IN_PROGRESS")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class PaymentOrder(Base):
    __tablename__ = "payment_orders"
    __table_args__ = (
        UniqueConstraint("provider", "partner_transaction_id", name="uq_payment_partner"),
        UniqueConstraint("provider", "partner_transaction_id", "provider_request_id", name="uq_payment_request"),
        Index("ix_payment_provider_transaction", "provider", "provider_transaction_id", unique=True),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    partner_transaction_id: Mapped[str] = mapped_column(String(128), unique=True)
    provider_request_id: Mapped[str] = mapped_column(String(128))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(32), default="CREATED", index=True)
    provider: Mapped[str] = mapped_column(String(32), default="pingpong")
    provider_transaction_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    provider_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    failure_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    failure_message: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    next_reconcile_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reconcile_attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class RefundOrder(Base):
    __tablename__ = "refund_orders"
    __table_args__ = (
        UniqueConstraint("payment_id", name="uq_refund_payment"),
        UniqueConstraint("partner_refund_id", name="uq_refund_partner"),
        Index("ix_refund_provider_id", "provider_refund_id", unique=True),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    payment_id: Mapped[str] = mapped_column(ForeignKey("payment_orders.id"), index=True)
    partner_refund_id: Mapped[str] = mapped_column(String(128))
    provider_request_id: Mapped[str] = mapped_column(String(128))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(32), default="CREATED", index=True)
    provider: Mapped[str] = mapped_column(String(32), default="pingpong")
    provider_refund_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    provider_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    credit_hold_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class WebhookEvent(Base):
    __tablename__ = "webhook_events"
    __table_args__ = (
        UniqueConstraint("provider", "provider_event_id", name="uq_webhook_provider_event"),
        UniqueConstraint("provider", "delivery_fingerprint", name="uq_webhook_delivery_fingerprint"),
    )
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), default="pingpong")
    event_type: Mapped[str] = mapped_column(String(64))
    # PingPong's public notification contract does not document a stable
    # event/delivery ID. This field is only populated if a future verified
    # contract supplies one; it is never synthesized from status/resource.
    provider_event_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    # Local duplicate-delivery guard; not a provider event ID.
    delivery_fingerprint: Mapped[str] = mapped_column(String(128))
    resource_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    provider_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(18, 2), nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    payload_hash: Mapped[str] = mapped_column(String(128))
    delivery_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="RECEIVED")
    error: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ProviderCallLog(Base):
    __tablename__ = "provider_call_logs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    provider: Mapped[str] = mapped_column(String(32))
    operation: Mapped[str] = mapped_column(String(64))
    trace_id: Mapped[str] = mapped_column(String(128), index=True)
    provider_request_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    http_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    provider_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    error_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    actor_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    actor_role: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    action: Mapped[str] = mapped_column(String(64))
    resource_type: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    trace_id: Mapped[str] = mapped_column(String(128), index=True)
    outcome: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class VCCApplication(Base):
    __tablename__ = "vcc_applications"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    requester_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    vendor: Mapped[str] = mapped_column(String(128))
    purpose: Mapped[str] = mapped_column(String(128))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    currency: Mapped[str] = mapped_column(String(3))
    period: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="DRAFT", index=True)
    approval_status: Mapped[str] = mapped_column(String(32), default="PENDING")
    provider_card_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    masked_card: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
