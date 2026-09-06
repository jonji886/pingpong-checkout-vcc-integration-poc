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
| API Endpoint Addresses | https://acquirer-api-docs-v4-en.pingpongx.com/en/notes/guide/endpoint/ | V4 | 2025-10-31 | 2026-09-06 |
| Basic Rules for API Usage | https://acquirer-api-docs-v4.pingpongx.com/en/notes/guide/APIUsage/ | V4 | 2025-03-07 | 2026-09-06 |
| Signature Convention | https://acquirer-api-docs-v4.pingpongx.com/en/notes/guide/sign/ | V4 | 2025-03-07 | 2026-09-06 |
| API Only (Non-Hosted Mode) | https://acquirer-api-docs-v4-en.pingpongx.com/en/notes/checkout/api/uniformly/ | V4 | 2025-03-07 | 2026-09-06 |
| Transaction Query | https://acquirer-api-docs-v4-en.pingpongx.com/en/notes/checkout/api/getOne/ | V4 | 2025-03-07 | 2026-09-06 |
| Request Refund | https://acquirer-api-docs-v4-en.pingpongx.com/en/notes/checkout/api/modifications/refund/ | V4 | 2025-03-07 | 2026-09-06 |
| Refund Query | https://acquirer-api-docs-v4-en.pingpongx.com/en/notes/checkout/api/getRefund/ | V4 | 2025-03-07 | 2026-09-06 |
| Payment Notification | https://acquirer-api-docs-v4-en.pingpongx.com/en/notes/notify/payment/notify/ | V4 | 2025-03-07 | 2026-09-06 |
| Refund Notification | https://acquirer-api-docs-v4-en.pingpongx.com/en/notes/notify/refundNotify/ | V4 | 2025-03-07 | 2026-09-06 |

The user-supplied prompt also referenced `docs.pingpongx.com` pages and `/api/acq/v4/...` paths. Those JavaScript pages did not expose a readable contract during this review, while the linked public V4 developer guide exposed the contract below. The two path families are not merged or presented as interchangeable.

## Decision

The Sandbox adapter targets the readable public Checkout V4 contract:

```text
POST /v4/payment/prePay       # Hosted Checkout used by this POC
POST /v4/payment/query
POST /v4/payment/refund
POST /v4/payment/getRefund
```

The local Domain model remains independent from Provider names. Provider DTOs in `app/integrations/pingpong/checkout_contracts.py` and mappers in `mappers.py` are the only boundary used by the HTTP adapter. Mock and Sandbox adapters implement the same `CheckoutProvider` port.

## Verified

- Requests and responses use JSON and the public V4 envelope fields `accId`, `clientId`, `signType`, `sign`, `version`, and `bizContent`.
- V4 signatures use all message fields except `sign`, sorted by key, with the configured salt prepended; public documentation describes MD5 and SHA256.
- Hosted create uses `merchantTransactionId`, `amount`, `currency`, `payResultUrl`, `payCancelUrl`, `notificationUrl`, `captureDelayHours`, `goods`, `shopperIP`, and optional `tradeCountry` as documented fields. Merchant/product conditions still apply.
- Query accepts the merchant transaction ID and/or provider transaction ID; this POC sends the merchant transaction ID. The local request ID remains a correlation value in Hosted mode.
- Refund create uses `merchantTransactionId`, `merchantRefundId`, `amount`, `currency`, and optional `notificationUrl`.
- Refund query uses `/v4/payment/getRefund` and requires `merchantTransactionId` plus `merchantRefundId` or `refundId`; the adapter sends the merchant IDs available to the local service.
- Documented payment status values include `INIT`, `PROCESSING`, `SUCCESS`, `FAILED`, `AUTH_SUCCESS`, `CANCEL`, and `CLOSED`. The local mapper keeps Provider status and applies a separate Domain mapping.
- Payment notifications expose `merchantTransactionId`, `transactionId`, `notifyType`, `currency`, `amount`, and `status`; refund notifications expose `merchantRefundId`, `refundId`, and `status`.
- Hosted create returns a provider `paymentUrl` for customer action; query recovery remains the source of truth when notification delivery is missing.
- Hosted-mode `paymentUrl` is a documented customer action. Unknown non-hosted `action` shapes are not guessed; they map to `NONE` until the merchant account's action contract is confirmed.

## Unverified / Sandbox Pending

- Sandbox credentials, salt/account values and merchant product permissions.
- Merchant-specific required values for `goods`, `shopperIP`, redirect/callback reachability, and any risk-control fields.
- Whether the user account is enabled for the Hosted `prePay` flow used by this POC.
- API-only `unifiedPay` remains a separate known path and is not invoked because its card/risk-control contract is outside this POC.
- The real callback URL reachability and account-specific notification retry behavior in this POC environment.
- No real successful Sandbox payment, callback or refund was executed by this change.

## Consequences

- `MOCK_VERIFIED` means local deterministic behavior and tests pass.
- `CONTRACT_VERIFIED` means official public examples were parsed through DTO/mapper tests and HTTP request shape was checked with MockTransport; it is not a real API call.
- `SANDBOX_PENDING` remains the honest status until credentials, account permissions, public HTTPS callback and a real end-to-end run exist.
- Provider delivery is at-least-once/uncertain. Local business effects are idempotent within the database transaction boundary; this is not distributed exactly-once delivery.
