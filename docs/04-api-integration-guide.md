# API Integration Guide

所有受保护 API 使用 `Authorization: Bearer <demo token>`（本地演示）并由服务端注入 Principal。Topup/Refund 写操作必须带 `Idempotency-Key`。关键入口：

- `POST /api/topups`：创建 USD Payment，返回 `next_action`（REDIRECT/QR_CODE/NONE）。
- `GET /api/payments/{id}`、`GET /api/payments`：查看状态、request/transaction correlation。
- `POST /api/webhooks/pingpong/checkout`：原文仅用于验签；Mock 用 HMAC `X-Mock-Signature`。
- `POST /api/admin/payments/{id}/reconcile`：FDE/Admin 主动 Query。
- `POST /api/refunds`、`GET /api/refunds/{id}`：Finance 全额退款。

