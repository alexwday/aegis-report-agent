import re
from dataclasses import dataclass
from hmac import digest
from typing import Protocol

import httpx
from fastapi import HTTPException


@dataclass(frozen=True)
class CurrentUser:
    user_id: str
    email: str | None = None

    def owner_key(self, secret: bytes) -> bytes:
        return digest(secret, self.user_id.encode(), "sha256")


class AuthProvider(Protocol):
    def authenticate(self, token: str | None) -> CurrentUser: ...


@dataclass(frozen=True)
class LocalAuth:
    user_id: str

    def authenticate(self, token: str | None) -> CurrentUser:
        return CurrentUser(self.user_id)


def response_detail(response: httpx.Response, token: str) -> str:
    try:
        body = response.json()
    except ValueError:
        return "Identity service rejected credentials"
    detail = body.get("detail") if isinstance(body, dict) else None
    if (
        isinstance(detail, str) and 0 < len(detail) <= 160 and token not in detail
        and re.fullmatch(r"[a-zA-Z0-9 .,'!?_-]+", detail)
    ):
        return detail
    return "Identity service rejected credentials"


@dataclass(frozen=True)
class UpstreamAuth:
    url: str
    client: httpx.Client

    def authenticate(self, token: str | None) -> CurrentUser:
        if not token:
            raise HTTPException(401, "A bearer token is required", {"WWW-Authenticate": "Bearer"})
        try:
            response = self.client.get(
                self.url,
                params={"service": "AEGIS"},
                headers={"Authorization": f"Bearer {token}"},
                timeout=httpx.Timeout(10, connect=5),
                follow_redirects=False,
            )
        except httpx.RequestError as exc:
            raise HTTPException(503, "Identity service unavailable") from exc
        if response.status_code == 503 or response.is_redirect:
            raise HTTPException(503, "Identity service unavailable")
        if response.status_code != 200:
            status = response.status_code if response.is_error else 503
            raise HTTPException(status, response_detail(response, token))
        try:
            body = response.json()
            data = body.get("data") if isinstance(body, dict) else None
            employee_id = data.get("employee_id") if isinstance(data, dict) else None
        except ValueError:
            employee_id = None
        if not isinstance(employee_id, str) or not employee_id.strip():
            raise HTTPException(401, "Validated response has no user identity")
        return CurrentUser(employee_id)


class OwnerStatusChecker(Protocol):
    def is_active(self, owner_key: bytes) -> bool: ...


@dataclass(frozen=True)
class UnwiredOwnerStatus:
    local: bool

    def is_active(self, owner_key: bytes) -> bool:
        return self.local
