"""Black-box HTTP E2E coverage for the local Mock demonstration."""

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from app.db import Base, engine
from app.integrations.pingpong.mock_checkout import MockPingPongCheckoutAdapter
from app.main import create_app

pytestmark = pytest.mark.e2e


@pytest.fixture(autouse=True)
def isolated_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def e2e_client():
    provider = MockPingPongCheckoutAdapter("PENDING")
    with TestClient(create_app(provider=provider)) as client:
        yield client, provider


def auth(role: str) -> dict[str, str]:
    return {"Authorization": "Bearer " + {"developer": "dev-token", "finance": "finance-token", "approver": "approver-token", "admin": "admin-token"}[role]}


def signed_webhook(payload: dict) -> tuple[bytes, dict[str, str]]:
    body = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(b"local-demo-secret", body, hashlib.sha256).hexdigest()
    return body, {"Content-Type": "application/json", "X-Mock-Signature": signature}


def create_topup(client: TestClient, key: str = "e2e-topup", amount: str = "100.00") -> str:
    response = client.post("/api/topups", json={"amount": amount, "currency": "USD"}, headers={**auth("developer"), "Idempotency-Key": key})
    assert response.status_code == 200, response.text
    return response.json()["payment_id"]


def test_complete_checkout_refund_flow(e2e_client):
    client, _provider = e2e_client
    payment_id = create_topup(client)
    initial = client.get("/api/payments/" + payment_id, headers=auth("developer"))
    assert initial.status_code == 200
    assert initial.json()["payment_status"] == "PROCESSING"
    assert initial.json()["provider_request_id"]

    body, headers = signed_webhook({"partner_transaction_id": "txn_" + payment_id, "transaction_id": "provider_" + payment_id, "requestId": "req_" + payment_id, "status": "SUCCESS", "amount": "100.00", "currency": "USD"})
    for _ in range(10):
        response = client.post("/api/webhooks/pingpong/checkout", content=body, headers=headers)
        assert response.status_code == 200
        assert response.json() == {"code": 200, "message": "SUCCESS"}

    balance = client.get("/api/me/credits", headers=auth("developer"))
    assert balance.json()["posted_balance"] == "100.00"
    assert balance.json()["available_balance"] == "100.00"
    payment = client.get("/api/payments/" + payment_id, headers=auth("developer")).json()
    assert payment["payment_status"] == "SUCCEEDED"

    refund = client.post("/api/refunds", json={"payment_id": payment_id}, headers={**auth("finance"), "Idempotency-Key": "e2e-refund"})
    assert refund.status_code == 200
    assert refund.json()["refund_status"] == "SUCCEEDED"
    assert client.get("/api/me/credits", headers=auth("developer")).json()["available_balance"] == "0.00"

    assert client.get("/api/admin/provider-calls", headers=auth("admin")).status_code == 200
    events = client.get("/api/admin/webhooks", headers=auth("admin"))
    assert events.status_code == 200 and events.json()[0]["status"] == "PROCESSED"


def test_missing_webhook_is_recovered_by_query(e2e_client):
    client, provider = e2e_client
    payment_id = create_topup(client, key="e2e-reconcile", amount="12.00")
    provider.set_payment_status("txn_" + payment_id, "SUCCESS")
    response = client.post("/api/payments/" + payment_id + "/query", headers=auth("developer"))
    assert response.status_code == 200
    assert response.json()["payment_status"] == "SUCCEEDED"
    assert client.get("/api/me/credits", headers=auth("developer")).json()["posted_balance"] == "12.00"


def test_idempotency_conflict_and_rbac_are_enforced(e2e_client):
    client, provider = e2e_client
    headers = {**auth("developer"), "Idempotency-Key": "e2e-conflict"}
    first = client.post("/api/topups", json={"amount": "1.00", "currency": "USD"}, headers=headers)
    assert first.status_code == 200
    calls_after_first = provider.create_calls
    conflict = client.post("/api/topups", json={"amount": "2.00", "currency": "USD"}, headers=headers)
    assert conflict.status_code == 409
    assert provider.create_calls == calls_after_first
    assert client.get("/api/admin/audit", headers=auth("developer")).status_code == 403
    assert client.get("/api/payments/" + first.json()["payment_id"], headers=auth("finance")).status_code == 200


def test_vcc_requires_approval_before_card_creation(e2e_client):
    client, _provider = e2e_client
    finance = auth("finance")
    parsed = client.post("/api/vcc/agent", json={"message": "为 AWS 9 月账单申请一张 20000 USD 的虚拟卡，有效期 30 天"}, headers=finance)
    assert parsed.status_code == 200
    data = parsed.json()
    assert data["parsed"]["vendor"] == "AWS"
    assert data["budget"]["passed"] is True
    assert data["approval"]["required"] is True
    application_id = data["application_id"]
    assert client.get("/api/vcc/" + application_id, headers=auth("developer")).status_code == 403
    assert client.post("/api/vcc/" + application_id + "/approve", json={"approved": True}, headers=finance).status_code == 403
    assert client.post("/api/vcc/" + application_id + "/card", headers=finance).status_code == 403
    approved = client.post("/api/vcc/" + application_id + "/approve", json={"approved": True}, headers=auth("approver"))
    assert approved.status_code == 200
    card = client.post("/api/vcc/" + application_id + "/card", headers=finance)
    assert card.status_code == 200 and card.json()["status"] == "ACTIVE"
    over_budget = client.post("/api/vcc/agent", json={"message": "为 AWS 账单申请一张 60000 USD 虚拟卡"}, headers=finance)
    assert over_budget.status_code == 200 and over_budget.json()["status"] == "REJECTED_BUDGET"


def test_ui_and_swagger_entrypoints(e2e_client):
    client, _provider = e2e_client
    for path in ("/docs", "/ui/demo", "/ui/developer", "/ui/finance", "/ui/fde", "/ui/vcc"):
        response = client.get(path)
        assert response.status_code == 200
        assert "DemoAI" in response.text or path == "/docs"


def test_payment_timeline_and_debug_search_are_correlated(e2e_client):
    client, _provider = e2e_client
    payment_id = create_topup(client, key="timeline-topup")

    timeline = client.get("/api/payments/" + payment_id + "/timeline", headers=auth("developer"))
    assert timeline.status_code == 200
    assert any(event["title"] == "创建订单" for event in timeline.json()["events"])
    assert any(event["title"].startswith("Provider ") for event in timeline.json()["events"])

    debug = client.get("/api/admin/debug", params={"payment_id": payment_id}, headers=auth("admin"))
    assert debug.status_code == 200
    debug_data = debug.json()
    assert debug_data["payment"]["payment_id"] == payment_id
    assert debug_data["provider_calls"]
    trace_id = debug_data["provider_calls"][0]["trace_id"]

    trace_debug = client.get("/api/admin/debug", params={"trace_id": trace_id}, headers=auth("admin"))
    assert trace_debug.status_code == 200
    assert any(item["trace_id"] == trace_id for item in trace_debug.json()["provider_calls"])
