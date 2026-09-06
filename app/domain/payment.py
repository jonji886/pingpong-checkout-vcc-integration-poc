from __future__ import annotations

from enum import Enum


class PaymentStatus(str, Enum):
    CREATED = "CREATED"
    PROCESSING = "PROCESSING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


PROVIDER_TO_PAYMENT = {
    "PENDING": PaymentStatus.PROCESSING,
    "SUCCESS": PaymentStatus.SUCCEEDED,
    "FAIL": PaymentStatus.FAILED,
    "CLOSE": PaymentStatus.CANCELLED,
    "AUTH_SUCCESS": PaymentStatus.REVIEW_REQUIRED,
}

# Terminal states are intentionally monotonic. A late PENDING cannot roll back SUCCESS.
TERMINAL_PAYMENT = {
    PaymentStatus.SUCCEEDED,
    PaymentStatus.FAILED,
    PaymentStatus.CANCELLED,
    PaymentStatus.REVIEW_REQUIRED,
}


class InvalidTransition(ValueError):
    pass


def transition(current: str, provider_status: str) -> str:
    """Map one trusted provider observation to a domain status."""
    target = PROVIDER_TO_PAYMENT.get(str(provider_status).upper())
    if target is None:
        raise InvalidTransition("unknown provider payment status")
    current_status = PaymentStatus(current)
    if current_status in TERMINAL_PAYMENT:
        if current_status == target:
            return current_status.value
        # A terminal observation is authoritative; out-of-order observations are ignored by caller.
        return current_status.value
    if current_status == PaymentStatus.CREATED and target not in {
        PaymentStatus.PROCESSING,
        PaymentStatus.SUCCEEDED,
        PaymentStatus.FAILED,
        PaymentStatus.CANCELLED,
        PaymentStatus.REVIEW_REQUIRED,
    }:
        raise InvalidTransition("invalid payment transition")
    return target.value


class PaymentStateMachine:
    """Small explicit façade used by services and unit tests."""

    @staticmethod
    def apply(current: PaymentStatus | str, provider_status: str) -> PaymentStatus:
        current_value = current.value if isinstance(current, PaymentStatus) else current
        return PaymentStatus(transition(current_value, provider_status))


class RefundStatus(str, Enum):
    CREATED = "CREATED"
    PROCESSING = "PROCESSING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


REFUND_TRANSITIONS = {
    RefundStatus.CREATED.value: {RefundStatus.PROCESSING.value, RefundStatus.MANUAL_REVIEW.value},
    RefundStatus.PROCESSING.value: {RefundStatus.SUCCEEDED.value, RefundStatus.FAILED.value},
}


def transition_refund(current: str, target: str) -> str:
    if current == target:
        return current
    if current in {RefundStatus.SUCCEEDED.value, RefundStatus.FAILED.value, RefundStatus.MANUAL_REVIEW.value}:
        return current
    if target not in REFUND_TRANSITIONS.get(current, set()):
        raise InvalidTransition("invalid refund transition")
    return target
