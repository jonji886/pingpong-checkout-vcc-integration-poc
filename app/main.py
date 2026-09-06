from __future__ import annotations

from fastapi import FastAPI

from .agents.finance_agent import VCCIntentParser, build_configured_intent_parser
from .config import settings
from .db import init_db, SessionLocal
from .integrations.pingpong.checkout import PingPongSandboxCheckoutAdapter
from .integrations.pingpong.issuing import MockPingPongIssuingAdapter
from .integrations.pingpong.mock_checkout import MockPingPongCheckoutAdapter
from .integrations.pingpong.retry import NoOpSleeper, RetryPolicy
from .models import User
from .api.routes import make_router
from .services.common import new_id
from .services.issuing_service import IssuingService
from .services.payment_service import PaymentService
from .services.refund_service import RefundService
from .ui import router as ui_router


class _UnconfiguredProvider:
    def __getattr__(self, _name):
        raise RuntimeError("PINGPONG_MODE must be explicitly set to mock or sandbox")


def _seed_demo_users() -> None:
    db = SessionLocal()
    try:
        for role in ("developer", "finance", "approver", "admin", "fde"):
            uid = "demo_" + role
            if not db.get(User, uid):
                db.add(User(id=uid, email=uid + "@demo.invalid", role=role))
        db.commit()
    finally:
        db.close()


def create_app(*, provider=None, issuing_provider=None, intent_parser: VCCIntentParser | None = None, initialize: bool = True) -> FastAPI:
    app = FastAPI(title="DemoAI PingPong FDE POC", version="0.1.0")
    if provider is None:
        if settings.pingpong_mode == "sandbox":
            provider = PingPongSandboxCheckoutAdapter()
        elif settings.pingpong_mode == "mock":
            provider = MockPingPongCheckoutAdapter()
        else:
            provider = _UnconfiguredProvider()
    issuing_provider = issuing_provider or MockPingPongIssuingAdapter()
    retry_policy = RetryPolicy(sleeper=NoOpSleeper()) if settings.pingpong_mode == "mock" else RetryPolicy()
    payment_service = PaymentService(provider, retry_policy=retry_policy)
    refund_service = RefundService(provider, retry_policy=retry_policy)
    issuing_service = IssuingService(issuing_provider)
    app.include_router(make_router(payment_service, refund_service, issuing_service, intent_parser=intent_parser))
    app.include_router(ui_router)

    @app.on_event("startup")
    def startup() -> None:
        # Explicit mode is a safety boundary: no implicit Sandbox→Mock fallback.
        settings.validate()
        if initialize:
            init_db(); _seed_demo_users()

    @app.get("/health")
    def health():
        mode = settings.pingpong_mode
        return {"status": "ok", "pingpong_mode": mode or "UNCONFIGURED", "verification_status": "MOCK_VERIFIED" if mode == "mock" else "SANDBOX_PENDING"}

    return app


app = create_app(intent_parser=build_configured_intent_parser())
