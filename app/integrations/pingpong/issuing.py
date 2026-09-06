"""Issuing port boundary.

The public Issuing directory confirms capability categories, but this POC has
not verified a complete merchant-specific request/response contract. The
protocol in ``base.py`` is therefore domain-shaped and the implementation
remains Mock-only; no PingPong raw field or real Issuing adapter is claimed.
"""

from .mock_issuing import MockPingPongIssuingAdapter

__all__ = ["MockPingPongIssuingAdapter"]
