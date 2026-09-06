import json
from decimal import Decimal
from pathlib import Path

import httpx

from app.integrations.pingpong.issuing import PingPongIssuingHttpAdapter
from app.integrations.pingpong.unified_auth import PingPongUnifiedAuthProvider
from app.integrations.pingpong.unified_checkout import PingPongUnifiedCheckoutAdapter
from app.integrations.pingpong.unified_mappers import map_unified_webhook

ROOT = Path(__file__).parent / "fixtures" / "pingpong"


class TestSigner:
    def sign(self, *, method, path, body):
        return "test-signature"


def load(path: str) -> dict:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def auth():
    return PingPongUnifiedAuthProvider("access-token", signer=TestSigner(), sign_version="v1")


def test_current_checkout_session_query_and_refund_contract():
    seen = []

    def handler(request: httpx.Request):
        seen.append((request.method, request.url.path, json.loads(request.content), dict(request.headers)))
        if request.url.path.endswith("sessions/create"):
            return httpx.Response(200, json=load("checkout/unified/v4/create_session_success.json"))
        if request.url.path.endswith("payments/query"):
            return httpx.Response(200, json=load("checkout/unified/v4/query_payment_success.json"))
        return httpx.Response(200, json=load("checkout/unified/v4/refund_success.json"))

    adapter = PingPongUnifiedCheckoutAdapter(
        base_url="https://gateway.example.invalid",
        auth=auth(),
        cancel_url="https://merchant.example/cancel",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    created = adapter.create_payment(
        partner_transaction_id="txn-unified-001",
        provider_request_id="req-unified-001",
        amount=Decimal("100.00"),
        currency="USD",
        user_id="demo-user",
        redirect_url="https://merchant.example/result",
        notify_url="https://merchant.example/notify",
    )
    queried = adapter.query_payment(partner_transaction_id="txn-unified-001", provider_request_id="req-unified-001")
    refund = adapter.create_refund(
        partner_refund_id="rfn-unified-001",
        provider_request_id="req-refund-001",
        partner_transaction_id="txn-unified-001",
        amount=Decimal("100.00"),
        currency="USD",
    )
    assert created.provider_status == "PROCESSING"
    assert created.next_action.url.endswith("session-001")
    assert queried.provider_status == "SUCCESS"
    assert refund.provider_refund_id == "2026090650000002"
    assert [item[1] for item in seen] == [
        "/api/acq/v4/sessions/create",
        "/api/acq/v4/payments/query",
        "/api/acq/v4/refunds/create",
    ]
    assert seen[0][2]["request_id"] == "req-unified-001"
    assert seen[0][3]["sign"] == "test-signature"
    assert "payment_method" not in seen[0][2]


def test_current_issuing_contract_serialization_parsing_and_redaction():
    seen = []

    def handler(request: httpx.Request):
        seen.append((request.method, request.url.path, request.content, dict(request.headers)))
        if request.url.path.endswith("/apply"):
            return httpx.Response(200, json=load("issuing/v2/create_card_success.json"))
        if request.url.path.endswith("/detail"):
            return httpx.Response(200, json=load("issuing/v2/card_detail_success.json"))
        if request.url.path.endswith("/authorizations"):
            return httpx.Response(200, json=load("issuing/v2/authorization_logs_success.json"))
        return httpx.Response(200, json=load("issuing/v2/action_success.json"))

    adapter = PingPongIssuingHttpAdapter(
        base_url="https://gateway.example.invalid",
        auth=auth(),
        card_product_code="T1FBXO",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    created = adapter.create_card(application_id="vcc-001", vendor="AWS", amount=Decimal("20000.00"), currency="USD", period_days=30)
    detail = adapter.get_card(provider_card_id="card202609060001")
    frozen = adapter.change_card_status(provider_card_id="card202609060001", action="FREEZE")
    transactions = adapter.query_transactions(provider_card_id="card202609060001")
    assert created["provider_card_id"] == "card202609060001"
    assert detail["status"] == "ACTIVE"
    assert detail["masked_card"].endswith("2321")
    assert "cvc" not in detail and "card_number" not in detail
    assert frozen["provider_card_id"] == "card202609060001"
    assert transactions["total"] == 1
    assert [item[1] for item in seen] == [
        "/api/issuing/card/v2/apply",
        "/api/issuing/card/v2/detail",
        "/api/issuing/card/v2/freeze",
        "/api/issuing/transaction/v2/authorizations",
    ]
    create_body = json.loads(seen[0][2])
    assert create_body == {
        "card_product_code": "T1FBXO",
        "remark": "AWS",
        "transaction_amount_limit": "20000.00",
        "lifetime_limit": "20000.00",
        "apply_coupon": False,
    }
    assert "sign" in seen[0][3]
    assert "sign" not in seen[1][3]


def test_current_flat_webhook_contract_maps_without_legacy_envelope():
    webhook = map_unified_webhook(load("checkout/unified/v4/webhook_payment_success.json"))
    assert webhook.event_type == "payment"
    assert webhook.request_id == "req-unified-001"
    assert webhook.transaction_id == "2026090650000001"
    assert webhook.merchant_transaction_id == "txn-unified-001"
    assert webhook.status == "SUCCESS"
    assert webhook.amount == Decimal("100.00")
