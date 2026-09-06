from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import settings


@dataclass(frozen=True)
class Principal:
    actor_id: str
    role: str


bearer = HTTPBearer(auto_error=False)


def current_principal(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> Principal:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required")
    role = settings.auth_tokens().get(credentials.credentials)
    if not role:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    return Principal(actor_id="demo_" + role, role=role)


def require_role(*roles: str) -> Callable:
    allowed = {r.lower() for r in roles}

    def dependency(principal: Principal = Depends(current_principal)) -> Principal:
        if principal.role not in allowed:
            raise HTTPException(status_code=403, detail="forbidden")
        return principal

    return dependency

