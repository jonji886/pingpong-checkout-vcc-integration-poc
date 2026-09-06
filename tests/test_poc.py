import hashlib
import hmac
import json
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.domain.payment import transition
from app.integrations.pingpong.auth import PingPongAuthProvider
from app.integrations.pingpong.base import ProviderRateLimited
from app.integrations.pingpong.mock_checkout import MockPingPongCheckoutAdapter
from app.integrations.pingpong.mock_issuing import MockPingPongIssuingAdapter
from app.integrations.pingpong.retry import RetryPolicy
from app.main import create_app
from app.models import CreditAccount, VCCApplication
from app.observability.redaction import redact
from app.services.issuing_service import IssuingService


@pytest.fixture(autouse=True)
def clean_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def client():
    provider = MockPingPongCheckoutAdapter("PENDING")
    return TestClient(create_app(provider=provider))


def signed(body: bytes) -> dict:
    return {"X-Mock-Signature": hmac.new(b"local-demo-secret", body, hashlib.sha256).hexdigest()}


def test_state_machine_is_monotonic():
    assert transition("CREATED", "PENDING") == "PROCESSING"
    assert transition("PROCESSING", "SUCCESS") == "SUCCEEDED"
    assert transition("SUCCEEDED", "PENDING") == "SUCCEEDED"


def test_topup_webhook_idempotency_and_payload_conflict(client):
    headers = {"Authorization": "Bearer dev-token", "Idempotency-Key": "topup-1"}
    first = client.post("/api/topups", json={"amount": "100.00", "currency": "USD"}, headers=headers)
    assert first.status_code == 200
    second = client.post("/api/topups", json={"amount": "100.00", "currency": "USD"}, headers=headers)
    assert second.status_code == 200
    assert second.json()["payment_id"] == first.json()["payment_id"]
    conflict = client.post("/api/topups", json={"amount": "101.00", "currency": "USD"}, headers=headers)
    assert conflict.status_code == 409
    payment_id = first.json()["payment_id"]
    body = json.dumps({"partner_transaction_id": "txn_" + payment_id, "status": "SUCCESS", "amount": "100.00", "currency": "USD"}).encode()
    for _ in range(10):
        assert client.post("/api/webhooks/pingpong/checkout", content=body, headers=signed(body)).status_code == 200
    assert client.get("/api/me/credits", headers={"Authorization": "Bearer dev-token"}).json()["posted_balance"] == "100.00"


def test_reconcile_recovers_missing_webhook(client):
    headers = {"Authorization": "Bearer dev-token", "Idempotency-Key": "topup-reconcile"}
    response = client.post("/api/topups", json={"amount": "12.00", "currency": "USD"}, headers=headers)
    payment_id = response.json()["payment_id"]
    admin = {"Authorization": "Bearer admin-token"}
    result = client.post("/api/admin/payments/%s/reconcile" % payment_id, headers=admin)
    assert result.status_code == 200
    assert result.json()["payment_status"] in {"PROCESSING", "SUCCEEDED"}


def test_refund_hold_and_reversal(client):
    topup_headers = {"Authorization": "Bearer dev-token", "Idempotency-Key": "refund-topup"}
    response = client.post("/api/topups", json={"amount": "100.00", "currency": "USD"}, headers=topup_headers)
    payment_id = response.json()["payment_id"]
    body = json.dumps({"partner_transaction_id": "txn_" + payment_id, "status": "SUCCESS", "amount": "100.00", "currency": "USD"}).encode()
    client.post("/api/webhooks/pingpong/checkout", content=body, headers=signed(body))
    refund = client.post("/api/refunds", json={"payment_id": payment_id}, headers={"Authorization": "Bearer finance-token", "Idempotency-Key": "refund-1"})
    assert refund.status_code == 200
    assert refund.json()["refund_status"] == "SUCCEEDED"
    assert client.get("/api/me/credits", headers={"Authorization": "Bearer dev-token"}).json()["available_balance"] == "0.00"


def test_rbac_and_bad_signature(client):
    assert client.get("/api/admin/provider-calls", headers={"Authorization": "Bearer dev-token"}).status_code == 403
    assert client.post("/api/webhooks/pingpong/checkout", content=b"{}", headers={"X-Mock-Signature": "bad"}).status_code == 401


def test_retry_policy_is_bounded_and_injectable():
    attempts = []
    def operation():
        attempts.append(1)
        if len(attempts) < 3: raise ProviderRateLimited()
        return "ok"
    assert RetryPolicy(max_attempts=3, base_delay=1, jitter=lambda _: 0, sleep=lambda _: None).run(operation) == "ok"
    assert len(attempts) == 3


def test_v4_signature_verification_uses_sorted_body_and_salt():
    payload = {"accId": "a", "clientId": "c", "signType": "SHA256", "version": "1.0", "bizContent": "{}"}
    content = "salt" + "&".join("%s=%s" % (key, payload[key]) for key in sorted(payload))
    payload["sign"] = __import__("hashlib").sha256(content.encode()).hexdigest().upper()
    assert PingPongAuthProvider("", "").verify_v4_body(payload, "salt")


def test_vcc_requires_human_approval_and_budget_gate(client):
    finance = {"Authorization": "Bearer finance-token"}
    parsed = client.post("/api/vcc/agent", json={"message": "为 AWS 9 月账单申请一张 20000 USD 的虚拟卡，有效期 30 天"}, headers=finance).json()
    assert parsed["status"] == "PENDING_APPROVAL"
    application_id = parsed["application_id"]
    assert client.post("/api/vcc/%s/card" % application_id, headers=finance).status_code == 403
    approved = client.post("/api/vcc/%s/approve" % application_id, json={"approved": True}, headers={"Authorization": "Bearer approver-token"})
    assert approved.status_code == 200
    assert client.post("/api/vcc/%s/card" % application_id, headers=finance).json()["status"] == "ACTIVE"
    rejected = client.post("/api/vcc/agent", json={"message": "为 AWS 账单申请一张 60000 USD 虚拟卡"}, headers=finance).json()
    assert rejected["status"] == "REJECTED_BUDGET"


def test_vcc_issuance_rejects_missing_human_confirmation(client):
    finance = {"Authorization": "Bearer finance-token"}
    parsed = client.post(
        "/api/vcc/agent",
        json={"message": "为 AWS 9 月账单申请一张 20000 USD 的虚拟卡，有效期 30 天"},
        headers=finance,
    ).json()
    application_id = parsed["application_id"]
    approved = client.post(
        "/api/vcc/%s/approve" % application_id,
        json={"approved": True},
        headers={"Authorization": "Bearer approver-token"},
    )
    assert approved.status_code == 200

    db = SessionLocal()
    try:
        service = IssuingService(MockPingPongIssuingAdapter())
        with pytest.raises(PermissionError, match="human confirmation"):
            service.create_vcc(
                db,
                application_id=application_id,
                actor_id="demo_finance",
                actor_role="finance",
                trace_id="trace-human-gate",
            )
        db.rollback()
        assert db.get(VCCApplication, application_id).status == "APPROVED"
    finally:
        db.close()


def test_redactor_removes_sensitive_fields():
    clean = redact({"token_value": "secret", "email": "person@example.com", "nested": {"cvv": "123", "ok": 1}})
    assert clean == {"token_value": "[REDACTED]", "email": "[REDACTED]", "nested": {"cvv": "[REDACTED]", "ok": 1}}


def test_agent_does_not_treat_month_as_amount():
    parsed = __import__("app.agents.finance_agent", fromlist=["parse_payment_request"]).parse_payment_request("为 AWS 9 月账单申请虚拟卡")
    assert "amount" in parsed.missing_fields


def test_ui_pages_are_available(client):
    for path in ("/ui/developer", "/ui/finance", "/ui/fde", "/ui/vcc"):
        response = client.get(path)
        assert response.status_code == 200
        assert "DemoAI" in response.text


def test_payment_fail_does_not_credit():
    provider = MockPingPongCheckoutAdapter("FAIL")
    local_client = TestClient(create_app(provider=provider))
    response = local_client.post("/api/topups", json={"amount": "20.00"}, headers={"Authorization": "Bearer dev-token", "Idempotency-Key": "fail-1"})
    assert response.status_code == 200
    assert response.json()["payment_status"] == "FAILED"
    assert local_client.get("/api/me/credits", headers={"Authorization": "Bearer dev-token"}).json()["posted_balance"] == "0.00"


def test_insufficient_credits_enters_manual_review_without_provider_call(client):
    topup = client.post("/api/topups", json={"amount": "100.00"}, headers={"Authorization": "Bearer dev-token", "Idempotency-Key": "hold-topup"}).json()
    body = json.dumps({"partner_transaction_id": "txn_" + topup["payment_id"], "status": "SUCCESS", "amount": "100.00", "currency": "USD"}).encode()
    client.post("/api/webhooks/pingpong/checkout", content=body, headers=signed(body))
    db = SessionLocal()
    try:
        account = db.query(CreditAccount).filter_by(user_id="demo_developer").one()
        account.posted_balance = Decimal("0.00"); account.available_balance = Decimal("0.00"); db.commit()
    finally:
        db.close()
    result = client.post("/api/refunds", json={"payment_id": topup["payment_id"]}, headers={"Authorization": "Bearer finance-token", "Idempotency-Key": "manual-refund"})
    assert result.status_code == 200
    assert result.json()["refund_status"] == "MANUAL_REVIEW"
