# Test Plan

自动化默认只使用本地 SQLite、Mock Provider、官方公开样例 fixture 和 `httpx.MockTransport`；不访问真实 PingPong，不把 contract test 当 Sandbox E2E。

| ID | Scenario | Risk | Precondition | Action | Expected | Automated Test | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| PAY-01 | 状态机单调性 | HIGH | Payment CREATED/SUCCEEDED | 观察 PENDING/SUCCESS/迟到 PENDING | 合法映射；终态不回退 | `test_state_machine_is_monotonic` | PASS |
| PAY-02 | Topup API idempotency | HIGH | Developer token | 相同 key replay、不同 payload replay | 原资源 replay；不同 payload 409 | `test_topup_webhook_idempotency_and_payload_conflict` | PASS |
| PAY-03 | Provider timeout → Query recovery | HIGH | Create 网络 timeout | 使用原 IDs Query | PROCESSING→SUCCEEDED；ledger 一条 | `test_create_timeout_keeps_same_identifiers_and_query_recovers` | PASS |
| PAY-04 | Missing webhook reconciliation | HIGH | Payment PROCESSING | Provider 变 SUCCESS 后 Query | 状态和 Credits 恢复 | `test_reconcile_recovers_missing_webhook`, `test_missing_webhook_is_recovered_by_query` | PASS |
| PAY-05 | Payment failure | HIGH | Mock FAIL | Create | FAILED；不入账 | `test_payment_fail_does_not_credit` | PASS |
| PAY-06 | Duplicate/out-of-order webhook | HIGH | 已收到 SUCCESS | 重复 SUCCESS、迟到 PENDING | ledger 不重复；状态不回退 | `test_late_webhook_cannot_roll_back_success_or_post_again`, `test_topup_webhook_idempotency_and_payload_conflict` | PASS |
| PAY-07 | Canonical delivery fingerprint | HIGH | 相同语义不同 key 顺序 | 发送两次 | 一个 local delivery record | `test_canonical_delivery_fingerprint_handles_reordered_duplicate_payload` | PASS |
| PAY-08 | Invalid webhook signature | HIGH | Mock secret | 错误 signature | 401；不执行业务 | `test_rbac_and_bad_signature` | PASS |
| PAY-09 | Concurrent business effect defense | HIGH | SUCCESS observation paths | Webhook + Query 同一 Payment | TOPUP ledger 一条；DB unique constraint 为最终防线 | `test_late_webhook_cannot_roll_back_success_or_post_again`, `test_create_timeout_keeps_same_identifiers_and_query_recovers` | PASS |
| REF-01 | Refund success/hold/reversal | HIGH | Credits 已到账 | Create full refund | hold settle；负向 ledger；余额不负 | `test_refund_hold_and_reversal`, `test_complete_checkout_refund_flow` | PASS |
| REF-02 | Duplicate refund replay | HIGH | 已成功 Payment | 相同 key 两次 | 一个 RefundOrder；Provider call 一次 | `test_refund_replay_is_idempotent_and_payload_conflict_is_409` | PASS |
| REF-03 | Refund insufficient balance | HIGH | 可用余额不足 | Create refund | MANUAL_REVIEW；不调用 Provider | `test_insufficient_credits_enters_manual_review_without_provider_call` | PASS |
| RET-01 | 429 bounded retry | HIGH | Rate limit error | policy retry | 最大次数、可注入 sleeper、不真实等待 | `test_retry_policy_is_bounded_and_injectable`, `test_pingpong_429_retry_after_and_timeout_mapping`, `test_retry_policy_is_bounded_without_real_sleep` | PASS |
| RET-02 | HTTP error classification | HIGH | MockTransport | 429/timeout | ProviderRateLimited/ProviderTimeout | `test_pingpong_429_retry_after_and_timeout_mapping` | PASS |
| CON-01 | Create request/response contract | HIGH | 官方最小 fixture | DTO→Mapper、MockTransport | URL/body/envelope/status/action boundary 正确 | `test_pingpong_create_payment_request_and_response_mapping` | PASS |
| CON-02 | Query/refund contract | HIGH | 官方最小 fixture | Query/refund DTO mapping | endpoint、IDs、status 正确 | `test_pingpong_query_refund_and_webhook_mapping` | PASS |
| CON-03 | Webhook contract | HIGH | 官方 notification fixture | map payment/refund | event type、IDs、amount/status 正确 | `test_pingpong_query_refund_and_webhook_mapping` | PASS |
| CON-04 | Unknown action safety | HIGH | action 未定义字段 | map response | 不猜字段，安全为 NONE | `test_mapper_keeps_unknown_action_safe` | PASS |
| SEC-01 | RBAC | HIGH | Developer principal | 访问 Admin | 403 | `test_rbac_and_bad_signature`, `test_idempotency_conflict_and_rbac_are_enforced` | PASS |
| SEC-02 | Sensitive redaction | HIGH | sensitive keys/action URL | redact snapshot | Secret/PAN/CVV/PII 不出现在日志副本 | `test_redactor_removes_sensitive_fields`, `test_sensitive_redaction_includes_provider_action_and_auth_fields` | PASS |
| VCC-01 | Approval boundary | HIGH | Finance request > threshold | Finance 直接开卡，再 Approver approve | 未审批 403；审批后 Mock card ACTIVE | `test_vcc_requires_human_approval_and_budget_gate`, `test_vcc_requires_approval_before_card_creation` | PASS |
| VCC-02 | Budget rejection / parser | MEDIUM | over-budget/缺金额 | parse + policy | REJECTED_BUDGET；缺失字段不猜 | `test_agent_does_not_treat_month_as_amount`, `test_vcc_requires_human_approval_and_budget_gate` | PASS |

本地当前 baseline/验收命令：

```bash
PINGPONG_MODE=mock PINGPONG_WEBHOOK_SECRET=local-demo-secret python3 -m pytest -q
```

CI 使用相同 Mock-only 命令；真实 Sandbox acceptance 需另行准备凭证、权限和公网 HTTPS callback，当前为 Pending。
