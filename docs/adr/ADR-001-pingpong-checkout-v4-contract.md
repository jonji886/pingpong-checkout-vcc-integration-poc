# ADR-001：PingPong Checkout V4 Contract Boundary

- Status: Accepted for the local POC; real Sandbox E2E remains pending
- Date: 2026-09-06
- Change risk: HIGH

## Context

DemoAI 需要通过 Checkout 为开发者充值 Credits。支付创建、查询、退款和异步通知会产生资金相关状态，因此 Provider JSON 不能直接进入 Domain；真实外部 Contract 也不能由 Mock 行为推断。

## Source of Truth

本 ADR 记录本次实际复核的公开资料。页面内容可能继续变化，接入前应再次复核。

| document_name | url | api_version | official_last_updated_at | reviewed_at |
| --- | --- | --- | --- | --- |
| Unified Checkout Create Session | https://docs.pingpongx.com/api/acq/payment/create-a-session?version=v4 | V4 | 2026-06-18 | 2026-09-06 |
| Unified Checkout Create Payment | https://docs.pingpongx.com/api/acq/payment/create-a-payment?version=v4 | V4 | 2026-06-18 | 2026-09-06 |
| Unified Checkout Query / Refund | https://docs.pingpongx.com/api/acq/payment/query-a-payment?version=v4 | V4 | 2026-06-18 | 2026-09-06 |
| Unified Checkout Webhook | https://docs.pingpongx.com/api/webhooks/checkout-webhook | V4 | 2026-06-18 | 2026-09-06 |
| Unified Issuing Create Card | https://docs.pingpongx.com/api/issuing/cards/create-a-card?version=v2 | V2 | 2026-03-25 | 2026-09-06 |
| Unified Issuing Card Detail / Actions | https://docs.pingpongx.com/api/issuing/cards/query-card-details?version=v2 | V2 | 2026-03-25 | 2026-09-06 |

The current official docs expose the `/api/acq/v4/...` unified contract. The older public Checkout V4 developer guide exposes a different envelope and `/v4/payment/...` path family. The two contracts are not merged or presented as interchangeable.

## Decision

The current Sandbox adapter targets the unified Checkout V4 contract:

```text
POST /api/acq/v4/sessions/create
POST /api/acq/v4/payments/query
POST /api/acq/v4/refunds/create
POST /api/acq/v4/refunds/query
```

The historical `/v4/payment/prePay` adapter remains available as the
explicitly named `PingPongSandboxCheckoutAdapter` for Legacy Public Sandbox
contract tests. It is not selected by the current factory.

The local Domain model remains independent from Provider names. Provider DTOs in `app/integrations/pingpong/checkout_contracts.py` and mappers in `mappers.py` are the only boundary used by the HTTP adapter. Mock and Sandbox adapters implement the same `CheckoutProvider` port.

## Verified

- Current unified requests use `Authorization`, `sign`, and `sign-version`; the adapter delegates the RSA/SM2 signer to an explicit infrastructure port.
- Session create uses `request_id`, `partner_transaction_id`, `amount`, `currency`, and optional redirect/notify/cancel fields; `action.redirect_url` maps to `next_action`.
- A successfully created Session is `PROCESSING`, not payment `SUCCESS`; Query/Webhook provides payment status.
- Current unified Query/Refund fields use request and partner IDs, amount, and currency; Provider DTOs are mapped before entering the domain.
- Current Checkout webhook samples are flat payment/refund events; they are mapped by `map_unified_webhook` and never parsed as the Legacy envelope.
- The adapter never serializes direct card data and does not infer a payment-method contract.
- Issuing v2 card creation uses a configured `card_product_code`, explicit spending limits, and `apply_coupon`; card detail/action/authorization-log endpoints are separately mapped.
- Card detail fields `card_number` and `cvc` are intentionally dropped at the adapter boundary.

## Unverified / Sandbox Pending

- Sandbox credentials, signing key, account and product permissions.
- Whether the account is enabled for the unified hosted Session flow.
- The signer canonicalization implementation for the account's RSA/SM2 key remains an injected infrastructure responsibility; it is not guessed here.
- The account-level webhook verification material is also an injected infrastructure responsibility; without it, the Sandbox webhook route fails closed.
- Direct current Checkout create-payment is not invoked because this POC uses hosted Session and must not collect PAN/CVV.
- The real callback URL reachability and account-specific notification retry behavior in this POC environment.
- No real successful Sandbox payment, callback, refund, card issuance or transaction query was executed by this change.

## Consequences

- `MOCK_VERIFIED` means local deterministic behavior and tests pass.
- `CONTRACT_VERIFIED` means official public examples were parsed through DTO/mapper tests and HTTP request shape was checked with MockTransport; it is not a real API call.
- `SANDBOX_PENDING` remains the honest status until credentials, account permissions, public HTTPS callback and a real end-to-end run exist.
- Provider delivery is at-least-once/uncertain. Local business effects are idempotent within the database transaction boundary; this is not distributed exactly-once delivery.
