import json
from decimal import Decimal
from pathlib import Path

from app.agents.finance_agent import RuleBasedIntentParser
from app.domain.vcc import CardStatus, transition_card
from app.integrations.pingpong.mock_issuing import MockPingPongIssuingAdapter


def test_vcc_eval_cases_keep_parser_and_policy_deterministic():
    cases = json.loads((Path(__file__).parent / "evals" / "vcc_intent_cases.json").read_text(encoding="utf-8"))
    parser = RuleBasedIntentParser()
    for case in cases:
        parsed = parser.parse(case["message"])
        if case["expected"] == "UNSAFE_REQUEST":
            assert parsed.rejection_reason == "UNSAFE_REQUEST", case["name"]
        elif case["expected"] == "NEEDS_CLARIFICATION":
            assert parsed.missing_fields, case["name"]
        elif case["expected"] == "OVER_BUDGET":
            assert Decimal(parsed.amount) > Decimal("50000"), case["name"]
        else:
            assert not parsed.missing_fields, case["name"]


def test_mock_issuing_lifecycle_has_domain_boundary_without_pan_or_cvv():
    provider = MockPingPongIssuingAdapter()
    card = provider.create_card(application_id="vcc_demo_12345678", vendor="AWS", amount=Decimal("20000"), currency="USD", period_days=30)
    assert card["status"] == CardStatus.ACTIVE.value
    assert "masked_card" in card and "cvv" not in card and "pan" not in card
    frozen = provider.change_card_status(provider_card_id=card["provider_card_id"], action="FREEZE")
    assert frozen["status"] == CardStatus.FROZEN.value
    active = provider.change_card_status(provider_card_id=card["provider_card_id"], action="UNFREEZE")
    assert active["status"] == CardStatus.ACTIVE.value
    controlled = provider.update_spending_control(provider_card_id=card["provider_card_id"], controls={"daily_limit": Decimal("1000")})
    assert controlled["spending_control"]["daily_limit"] == "1000"
    assert provider.get_balance(provider_card_id=card["provider_card_id"])["source"] == "mock"


def test_card_state_machine_rejects_closed_card_reactivation():
    assert transition_card(CardStatus.ACTIVE, CardStatus.FROZEN) == CardStatus.FROZEN
    assert transition_card(CardStatus.FROZEN, CardStatus.CLOSED) == CardStatus.CLOSED
    try:
        transition_card(CardStatus.CLOSED, CardStatus.ACTIVE)
    except ValueError:
        pass
    else:
        raise AssertionError("closed card must not reactivate")
