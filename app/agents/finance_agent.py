from __future__ import annotations

import re
from decimal import Decimal
from typing import Protocol

from .schemas import PaymentRequest


class VCCIntentParser(Protocol):
    def parse(self, message: str) -> PaymentRequest: ...


UNSAFE_REQUEST_PATTERNS = (
    "ignore previous",
    "ignore all previous",
    "bypass approval",
    "skip approval",
    "system rule",
    "绕过审批",
    "跳过审批",
    "修改系统规则",
)


def is_unsafe_request(message: str) -> bool:
    text = message.lower()
    return any(pattern in text for pattern in UNSAFE_REQUEST_PATTERNS if pattern.isascii()) or any(
        pattern in message for pattern in UNSAFE_REQUEST_PATTERNS if not pattern.isascii()
    )


def unsafe_request() -> PaymentRequest:
    return PaymentRequest(
        vendor="UNKNOWN",
        amount="",
        currency="",
        purpose="",
        period_days=30,
        missing_fields=["request"],
        rejection_reason="UNSAFE_REQUEST",
    )


def parse_payment_request(message: str) -> PaymentRequest:
    text = message.strip()
    if is_unsafe_request(text):
        return unsafe_request()
    vendor_match = re.search(r"(?:为|给|for)\s*([A-Za-z][A-Za-z0-9 ._-]*?)(?:\s*(?:账单|申请|bill|的|一张)|\s+\d)", text, re.I)
    vendor = vendor_match.group(1).strip(" ，,的") if vendor_match else ""
    # Dates ("9 月") and validity periods ("30 天") are also numbers. Prefer the
    # largest monetary-looking number so the demo phrase resolves to 20,000, not 9.
    money_patterns = [
        r"(?:\$|USD\s*)([0-9][0-9,]*(?:\.[0-9]+)?)",
        r"([0-9][0-9,]*(?:\.[0-9]+)?)\s*(?:USD|美元|美金|\$)",
        r"(?:一张|金额|amount)[^0-9]*([0-9][0-9,]*(?:\.[0-9]+)?)",
    ]
    money_values = []
    for pattern in money_patterns:
        money_values.extend(re.findall(pattern, text, re.I))
    ambiguous_amount = bool(re.search(r"[0-9][0-9,]*(?:\.[0-9]+)?\s*[kKmMbB]\b", text))
    amount = None if ambiguous_amount else max((Decimal(item.replace(",", "")) for item in money_values), default=None)
    currency = "USD" if re.search(r"USD|美元|美金|\$", text, re.I) else ""
    period_match = re.search(r"(?:有效期|周期|period)[^0-9]*(\d+)\s*(?:天|day|days)?", text, re.I)
    period = int(period_match.group(1)) if period_match else 30
    missing = []
    if not vendor: missing.append("vendor")
    if amount is None: missing.append("amount")
    if not currency: missing.append("currency")
    return PaymentRequest(vendor=vendor or "UNKNOWN", amount=f"{amount:.2f}" if amount is not None else "", currency=currency, purpose="cloud_service" if re.search(r"AWS|Google Cloud|GCP|云|cloud", text, re.I) else "business_expense", period_days=period, missing_fields=missing)


class RuleBasedIntentParser:
    def parse(self, message: str) -> PaymentRequest:
        return parse_payment_request(message)


def build_configured_intent_parser() -> VCCIntentParser:
    """Build the explicitly configured parser for the production app.

    Tests and local callers can still use ``create_app()`` with the rule-based
    parser by default; the global ASGI app opts into this configured parser.
    """
    from ..config import settings

    if not settings.llm_enabled:
        return RuleBasedIntentParser()
    if settings.llm_provider != "deepseek":
        raise RuntimeError("unsupported LLM_PROVIDER")
    from ..integrations.llm.deepseek import DeepSeekIntentParser

    return DeepSeekIntentParser(
        api_key=settings.deepseek_api_key,
        base_url=settings.deepseek_base_url,
        model=settings.llm_router_model,
        max_tokens=settings.llm_router_max_tokens,
        timeout_seconds=settings.llm_router_timeout_seconds,
    )
