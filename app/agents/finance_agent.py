from __future__ import annotations

import re
from decimal import Decimal

from .schemas import PaymentRequest


def parse_payment_request(message: str) -> PaymentRequest:
    text = message.strip()
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
    amount = max((Decimal(item.replace(",", "")) for item in money_values), default=None)
    currency = "USD" if re.search(r"USD|美元|美金|\$", text, re.I) else ""
    period_match = re.search(r"(?:有效期|周期|period)[^0-9]*(\d+)\s*(?:天|day|days)?", text, re.I)
    period = int(period_match.group(1)) if period_match else 30
    missing = []
    if not vendor: missing.append("vendor")
    if amount is None: missing.append("amount")
    if not currency: missing.append("currency")
    return PaymentRequest(vendor=vendor or "UNKNOWN", amount=f"{amount:.2f}" if amount is not None else "", currency=currency, purpose="cloud_service" if re.search(r"AWS|Google Cloud|GCP|云|cloud", text, re.I) else "business_expense", period_days=period, missing_fields=missing)
