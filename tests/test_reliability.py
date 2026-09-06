import hashlib
import hmac
import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.integrations.pingpong.base import NextAction, ProviderPaymentResult, ProviderTimeout
from app.integrations.pingpong.mock_checkout import MockPingPongCheckoutAdapter
from app.main import create_app
from app.models import CreditLedger, WebhookEvent
from app.observability.redaction import redact


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


def signed(payload: dict) -> tuple[bytes, dict[str, str]]:
    body = json.dumps(payload, separators=(",", ":")).encode()
    return body, {"X-Mock-Signature": hmac.new(b"local-demo-secret", body, hashlib.sha256).hexdigest()}


class TimeoutThenQueryProvider(MockPingPongCheckoutAdapter):
    def __init__(self):
        super().__init__("PENDING")
        self.create_arguments = []
        self.query_arguments = []
        self._timed_out = False

    def create_payment(self, **kwargs):
        self.create_arguments.append(kwargs)
        self.create_calls += 1
        if not self._timed_out:
            self._timed_out = True
            raise ProviderTimeout()
        return super().create_payment(**kwargs)

    def query_payment(self, **kwargs):
        self.query_arguments.append(kwargs)
        return ProviderPaymentResult(
            provider_transaction_id="provider_recovered_1",
            provider_request_id=kwargs["provider_request_id"],
            provider_status="SUCCESS",
            next_action=NextAction("NONE"),
            http_status=200,
        )


def topup(client: TestClient, key: str = "topup", amount: str = "100.00") -> str:
    response = client.post("/api/topups", json={"amount": amount, "currency": "USD"}, headers={"Authorization": "Bearer dev-token", "Idempotency-Key": key})
    assert response.status_code == 200, response.text
    return response.json()["payment_id"]


def test_create_timeout_keeps_same_identifiers_and_query_recovers():
    provider = TimeoutThenQueryProvider()
    client = TestClient(create_app(provider=provider))
    payment_id = topup(client, "timeout-recovery")
    first = client.get("/api/payments/" + payment_id, headers={"Authorization": "Bearer dev-token"}).json()
    assert first["payment_status"] == "PROCESSING"
    assert len(provider.create_arguments) == 1

    recovered = client.post("/api/payments/" + payment_id + "/query", headers={"Authorization": "Bearer dev-token"})
    assert recovered.status_code == 200
    assert recovered.json()["payment_status"] == "SUCCEEDED"
    assert provider.query_arguments[0]["partner_transaction_id"] == provider.create_arguments[0]["partner_transaction_id"]
    assert provider.query_arguments[0]["provider_request_id"] == provider.create_arguments[0]["provider_request_id"]

    db = SessionLocal()
    try:
        assert db.query(CreditLedger).filter_by(entry_type="TOPUP").count() == 1
    finally:
        db.close()


def test_late_webhook_cannot_roll_back_success_or_post_again():
    client = TestClient(create_app(provider=MockPingPongCheckoutAdapter("PENDING")))
    payment_id = topup(client, "out-of-order")
    success_body, success_headers = signed({"partner_transaction_id": "txn_" + payment_id, "transaction_id": "provider-1", "status": "SUCCESS", "amount": "100.00", "currency": "USD"})
    pending_body, pending_headers = signed({"partner_transaction_id": "txn_" + payment_id, "transaction_id": "provider-1", "status": "PENDING", "amount": "100.00", "currency": "USD"})
    assert client.post("/api/webhooks/pingpong/checkout", content=success_body, headers=success_headers).status_code == 200
    assert client.post("/api/webhooks/pingpong/checkout", content=pending_body, headers=pending_headers).status_code == 200
    payment = client.get("/api/payments/" + payment_id, headers={"Authorization": "Bearer dev-token"}).json()
    assert payment["payment_status"] == "SUCCEEDED"
    assert payment["provider_status"] == "SUCCESS"
    db = SessionLocal()
    try:
        assert db.query(CreditLedger).filter_by(entry_type="TOPUP").count() == 1
        assert db.query(WebhookEvent).count() == 2
    finally:
        db.close()


def test_refund_replay_is_idempotent_and_payload_conflict_is_409():
    provider = MockPingPongCheckoutAdapter("PENDING")
    client = TestClient(create_app(provider=provider))
    payment_id = topup(client, "refund-idempotency")
    body, headers = signed({"partner_transaction_id": "txn_" + payment_id, "status": "SUCCESS", "amount": "100.00", "currency": "USD"})
    client.post("/api/webhooks/pingpong/checkout", content=body, headers=headers)
    refund_headers = {"Authorization": "Bearer finance-token", "Idempotency-Key": "refund-replay"}
    first = client.post("/api/refunds", json={"payment_id": payment_id}, headers=refund_headers)
    second = client.post("/api/refunds", json={"payment_id": payment_id}, headers=refund_headers)
    assert first.status_code == second.status_code == 200
    assert first.json()["refund_id"] == second.json()["refund_id"]
    assert provider.refund_calls == 1

    other_payment_id = topup(client, "refund-other", "10.00")
    conflict = client.post("/api/refunds", json={"payment_id": other_payment_id}, headers=refund_headers)
    assert conflict.status_code == 409
    db = SessionLocal()
    try:
        assert db.query(CreditLedger).filter_by(entry_type="REFUND_REVERSAL").count() == 1
    finally:
        db.close()


def test_canonical_delivery_fingerprint_handles_reordered_duplicate_payload():
    client = TestClient(create_app(provider=MockPingPongCheckoutAdapter("PENDING")))
    payment_id = topup(client, "fingerprint")
    first = {"partner_transaction_id": "txn_" + payment_id, "status": "SUCCESS", "amount": "100.00", "currency": "USD"}
    second = {"currency": "USD", "amount": "100.00", "status": "SUCCESS", "partner_transaction_id": "txn_" + payment_id}
    body1, headers1 = signed(first)
    body2, headers2 = signed(second)
    assert client.post("/api/webhooks/pingpong/checkout", content=body1, headers=headers1).status_code == 200
    assert client.post("/api/webhooks/pingpong/checkout", content=body2, headers=headers2).status_code == 200
    db = SessionLocal()
    try:
        assert db.query(WebhookEvent).count() == 1
    finally:
        db.close()


def test_sensitive_redaction_includes_provider_action_and_auth_fields():
    assert redact({"paymentUrl": "https://provider.invalid/token=secret", "Authorization": "Bearer secret", "ok": 1}) == {"paymentUrl": "[REDACTED]", "Authorization": "[REDACTED]", "ok": 1}
