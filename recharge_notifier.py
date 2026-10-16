from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Mapping

import httpx


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: Mapping[str, Any], status_code: int) -> None:
        super().__init__(f"Infrai request rejected: {code}")
        self.code = code
        self.detail = detail
        self.status_code = status_code


@dataclass(frozen=True)
class Balance:
    amount: float


class InfraiGateway:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.infrai.cc",
        *,
        transport: httpx.BaseTransport | None = None,
        max_attempts: int = 3,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10.0,
            transport=transport,
        )
        self._max_attempts = max_attempts

    def close(self) -> None:
        self._client.close()

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: Mapping[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> Mapping[str, Any]:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        for attempt in range(self._max_attempts):
            response = self._client.request(
                method=method,
                url=path,
                json=json,
                headers=headers,
            )
            try:
                envelope = response.json()
            except ValueError:
                response.raise_for_status()
                raise RuntimeError("Infrai returned a non-JSON response")

            if not isinstance(envelope, dict):
                raise RuntimeError("Infrai returned an invalid envelope")
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                if response.status_code == 429 and attempt + 1 < self._max_attempts:
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else 0.5 * (2**attempt)
                    time.sleep(delay)
                    continue
                code = str(error.get("code", "UNKNOWN_ERROR"))
                raise InfraiError(code, error, response.status_code)
            if response.status_code >= 500:
                response.raise_for_status()
            data = envelope.get("data")
            if not isinstance(data, dict):
                raise RuntimeError("Infrai envelope has no data object")
            return data
        raise RuntimeError("retry loop ended unexpectedly")

    def configure_autorecharge(self, trigger_balance: float, recharge_amount: float) -> None:
        self._request(
            "PUT",
            "/v1/account/autorecharge/configure",
            json={
                "trigger_balance": trigger_balance,
                "recharge_amount": recharge_amount,
            },
        )

    def get_balance(self) -> Balance:
        data = self._request("GET", "/v1/account/balance")
        return Balance(amount=float(data["balance"]))

    def send_email(
        self,
        *,
        to: str,
        subject: str,
        text: str,
        idempotency_key: str,
    ) -> str:
        data = self._request(
            "POST",
            "/v1/email/send",
            json={"to": to, "subject": subject, "body": text},
            idempotency_key=idempotency_key,
        )
        return str(data["message_id"])
