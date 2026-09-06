import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.integrations.pingpong.auth import PingPongAuthProvider
from app.integrations.pingpong.base import ProviderContractError, ProviderRateLimited, ProviderTimeout
from app.integrations.pingpong.checkout import PingPongSandboxCheckoutAdapter
from app.integrations.pingpong.mappers import map_payment_response, map_refund_response, map_webhook
from app.integrations.pingpong.retry import NoOpSleeper, RetryPolicy


FIXTURES = Path(__file__).parent / "fixtures" / "pingpong" / "checkout" / "v4"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def adapter(handler):
    transport = httpx.MockTransport(handler)
    return PingPongSandboxCheckoutAdapter(
        base_url="https://sandbox.example.invalid",
        auth=PingPongAuthProvider("acc-demo", client_id="client-demo", salt="test-salt"),
        client=httpx.Client(transport=transport),
        trade_country="US",
        shopper_ip="203.0.113.10",
        pay_result_url="https://merchant.example/pay-result",
        pay_cancel_url="https://merchant.example/pay-cancel",
    )


def test_pingpong_create_payment_request_and_response_mapping():
    seen = {}

    def handler(request: httpx.Request):
        seen.update(json.loads(request.content))
        return httpx.Response(200, json=fixture("create_payment_success.json"))

    result = adapter(handler).create_payment(
        partner_transaction_id="PMT-DEMO-001",
        provider_request_id="REQ-DEMO-001",
        amount=Decimal("100.00"),
        currency="USD",
        user_id="demo_developer",
        notify_url="https://merchant.example/notify",
    )
    assert seen["accId"] == "acc-demo"
    assert seen["clientId"] == "client-demo"
    assert seen["signType"] == "SHA256"
    assert seen["version"] == "1.0"
    assert PingPongAuthProvider("", "").verify_v4_body(seen, "test-salt")
    biz = json.loads(seen["bizContent"])
    assert biz["merchantTransactionId"] == "PMT-DEMO-001"
    assert biz["amount"] == "100.00"
    assert biz["payResultUrl"] == "https://merchant.example/pay-result"
    assert biz["payCancelUrl"] == "https://merchant.example/pay-cancel"
    assert "paymentMethod" not in biz
    assert "device" not in biz
    assert result.provider_transaction_id == "2024050650046394"
    assert result.provider_status == "PROCESSING"
    assert result.next_action.type == "REDIRECT"
    assert result.next_action.url == "https://checkout.example.invalid/session/demo"


def test_pingpong_query_refund_and_webhook_mapping():
    paths = []

    def handler(request: httpx.Request):
        paths.append(request.url.path)
        if request.url.path == "/v4/payment/query":
            return httpx.Response(200, json=fixture("query_payment_success.json"))
        if request.url.path == "/v4/payment/getRefund":
            return httpx.Response(200, json=fixture("query_refund_success.json"))
        return httpx.Response(200, json=fixture("create_refund_success.json"))

    client = adapter(handler)
    payment = client.query_payment(partner_transaction_id="PMT-DEMO-001", provider_request_id="REQ-DEMO-001")
    refund = client.create_refund(partner_refund_id="RFN-DEMO-001", provider_request_id="REQ-RFN-001", partner_transaction_id="PMT-DEMO-001", amount=Decimal("100.00"), currency="USD")
    queried_refund = client.query_refund(partner_refund_id="RFN-DEMO-001", partner_transaction_id="PMT-DEMO-001", provider_request_id="REQ-RFN-001")
    webhook = map_webhook(fixture("webhook_payment_success.json"))
    refund_webhook = map_webhook(fixture("webhook_refund_success.json"))
    assert payment.provider_status == "SUCCESS"
    assert refund.provider_refund_id == "2024050750046461"
    assert queried_refund.provider_status == "SUCCESS"
    assert webhook.event_type == "payment" and webhook.transaction_id == "2024050650046394"
    assert refund_webhook.is_refund and refund_webhook.merchant_refund_id == "RFN-DEMO-001"
    assert paths == ["/v4/payment/query", "/v4/payment/refund", "/v4/payment/getRefund"]


def test_mapper_keeps_unknown_action_safe():
    payload = fixture("create_payment_success.json")
    payload["bizContent"].pop("paymentUrl", None)
    payload["bizContent"]["action"] = {"providerSpecificField": "do-not-guess"}
    result = map_payment_response(payload, "REQ-DEMO-001")
    assert result.next_action.type == "NONE"


def test_pingpong_429_retry_after_and_timeout_mapping():
    def rate_limited(request: httpx.Request):
        return httpx.Response(429, headers={"Retry-After": "0"}, json={"code": "RATE_LIMITED"})

    with pytest.raises(ProviderRateLimited) as error:
        adapter(rate_limited).query_payment(partner_transaction_id="PMT-DEMO-001", provider_request_id="REQ-DEMO-001")
    assert error.value.status_code == 429
    assert error.value.retry_after == 0

    def timeout(request: httpx.Request):
        raise httpx.ReadTimeout("read timeout", request=request)

    with pytest.raises(ProviderTimeout):
        adapter(timeout).query_payment(partner_transaction_id="PMT-DEMO-001", provider_request_id="REQ-DEMO-001")


def test_hosted_adapter_fails_without_required_redirect_configuration():
    client = PingPongSandboxCheckoutAdapter(
        base_url="https://sandbox.example.invalid",
        auth=PingPongAuthProvider("acc-demo", client_id="client-demo", salt="test-salt"),
        client=httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=fixture("create_payment_success.json")))),
        shopper_ip="203.0.113.10",
        pay_result_url="https://merchant.example/pay-result",
        pay_cancel_url="",
    )
    with pytest.raises(ProviderContractError, match="PINGPONG_PAY_CANCEL_URL"):
        client.create_payment(
            partner_transaction_id="PMT-DEMO-001",
            provider_request_id="REQ-DEMO-001",
            amount=Decimal("100.00"),
            currency="USD",
            user_id="demo_developer",
            notify_url="https://merchant.example/notify",
        )


def test_sandbox_settings_require_real_https_endpoints_without_secrets_in_error():
    valid = Settings(
        pingpong_mode="sandbox",
        pingpong_base_url="https://sandbox-acquirer-payment.pingpongx.com",
        pingpong_acc_id="acc-demo",
        pingpong_client_id="client-demo",
        pingpong_salt="salt-demo",
        pingpong_notify_url="https://callback.demoai.dev/notify",
        pingpong_pay_result_url="https://callback.demoai.dev/result",
        pingpong_pay_cancel_url="https://callback.demoai.dev/cancel",
        pingpong_shopper_ip="203.0.113.10",
    )
    valid.validate()

    with pytest.raises(RuntimeError, match="PINGPONG_PAY_RESULT_URL") as error:
        replace(valid, pingpong_pay_result_url="https://example.invalid/result").validate()
    assert "salt-demo" not in str(error.value)


def test_retry_policy_is_bounded_without_real_sleep():
    attempts = []
    delays = []

    def operation():
        attempts.append(1)
        raise ProviderRateLimited(retry_after=0)

    policy = RetryPolicy(max_attempts=3, base_delay=1, jitter=lambda value: 0, sleeper=NoOpSleeper(), on_retry=lambda attempt, error, delay: delays.append((attempt, error.error_type, delay)))
    with pytest.raises(ProviderRateLimited):
        policy.run(operation, operation_name="query_payment", request_id="REQ-DEMO-001")
    assert len(attempts) == 3
    assert [item[0] for item in delays] == [1, 2]
