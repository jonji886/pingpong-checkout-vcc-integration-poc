import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.agents.schemas import PaymentRequest
from app.integrations.llm.deepseek import DeepSeekIntentParser, LLMIntentParseError
from app.integrations.pingpong.mock_checkout import MockPingPongCheckoutAdapter
from app.main import create_app


def test_deepseek_parser_uses_json_output_and_returns_structured_intent():
    seen = {}

    def handler(request: httpx.Request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "vendor": "AWS",
                                    "amount": "20000.00",
                                    "currency": "USD",
                                    "purpose": "cloud_service",
                                    "period_days": 30,
                                    "missing_fields": [],
                                    "rejection_reason": None,
                                }
                            )
                        }
                    }
                ]
            },
        )

    parser = DeepSeekIntentParser(
        api_key="test-key",
        base_url="https://llm.example.invalid",
        model="deepseek-chat",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    result = parser.parse("为 AWS 账单申请 20000 USD 虚拟卡")
    assert result == PaymentRequest(
        vendor="AWS",
        amount="20000.00",
        currency="USD",
        purpose="cloud_service",
        period_days=30,
        missing_fields=[],
        rejection_reason=None,
    )
    assert seen["body"]["response_format"] == {"type": "json_object"}
    assert seen["body"]["stream"] is False
    assert "tool" not in seen["body"]


def test_deepseek_parser_failure_is_not_a_valid_intent():
    parser = DeepSeekIntentParser(
        api_key="test-key",
        base_url="https://llm.example.invalid",
        client=httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"choices": [{"message": {"content": "not-json"}}]})
            )
        ),
    )
    with pytest.raises(LLMIntentParseError):
        parser.parse("申请一张卡")


def test_llm_parser_failure_fails_closed_to_clarification():
    class FailingParser:
        def parse(self, message: str) -> PaymentRequest:
            raise RuntimeError("simulated provider failure")

    client = TestClient(
        create_app(
            provider=MockPingPongCheckoutAdapter("PENDING"),
            intent_parser=FailingParser(),
        )
    )
    response = client.post(
        "/api/vcc/agent",
        json={"message": "为 AWS 申请一张 20000 USD 虚拟卡"},
        headers={"Authorization": "Bearer finance-token"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "NEEDS_CLARIFICATION"
    assert response.json()["application_id"] is None
    assert response.json()["clarification_question"] == "请补充：完整的用卡申请。"
