import httpx
import pytest

from continuity_service import ContinuityCheck, run_continuity_check
from recharge_notifier import Balance, InfraiError, InfraiGateway


class RecordingGateway:
    def __init__(self, balance: float) -> None:
        self.balance = balance
        self.configured: tuple[float, float] | None = None
        self.sent: list[dict[str, str]] = []

    def configure_autorecharge(self, trigger_balance: float, recharge_amount: float) -> None:
        self.configured = (trigger_balance, recharge_amount)

    def get_balance(self) -> Balance:
        return Balance(self.balance)

    def send_email(self, **message: str) -> str:
        self.sent.append(message)
        return "msg_notice_42"


def request() -> ContinuityCheck:
    return ContinuityCheck.model_validate(
        {
            "check_id": "saturday-pantry-2026-09-26",
            "notification_to": "ops@riverpantry.org",
            "trigger_balance": 20,
            "recharge_amount": 100,
            "donor_receipt": {"donor_name": "September donors", "receipt_count": 18},
            "volunteer_reminder": {"shift_name": "Saturday packing", "volunteer_count": 7},
            "campaign_report": {"campaign_name": "Fall pantry", "donations_usd": 860},
        }
    )


def test_low_balance_configures_recharge_and_sends_one_operations_note() -> None:
    gateway = RecordingGateway(balance=12.5)

    result = run_continuity_check(request(), gateway)

    assert gateway.configured == (20, 100)
    assert result.recharge_triggered is True
    assert result.notification_message_id == "msg_notice_42"
    assert len(gateway.sent) == 1
    assert gateway.sent[0]["idempotency_key"] == "saturday-pantry-2026-09-26:recharge-notice"
    assert "18 ready" in gateway.sent[0]["text"]
    assert "7 people" in gateway.sent[0]["text"]
    assert "Fall pantry" in gateway.sent[0]["text"]


def test_healthy_balance_does_not_send_a_recharge_note() -> None:
    gateway = RecordingGateway(balance=50)

    result = run_continuity_check(request(), gateway)

    assert result.recharge_triggered is False
    assert result.notification_message_id is None
    assert gateway.sent == []


def test_email_retries_429_with_the_same_idempotency_key() -> None:
    seen_keys: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_keys.append(request.headers["Idempotency-Key"])
        if len(seen_keys) == 1:
            return httpx.Response(
                429,
                headers={"Retry-After": "0"},
                json={"ok": False, "data": None, "error": {"code": "RATE_LIMITED"}, "metadata": {}},
            )
        return httpx.Response(
            200,
            json={"ok": True, "data": {"message_id": "msg_retry_7"}, "error": None, "metadata": {}},
        )

    gateway = InfraiGateway("test-key", transport=httpx.MockTransport(handler))
    try:
        message_id = gateway.send_email(
            to="ops@riverpantry.org",
            subject="Recharge notice",
            text="The pantry run continues.",
            idempotency_key="check-7:recharge-notice",
        )
    finally:
        gateway.close()

    assert message_id == "msg_retry_7"
    assert seen_keys == ["check-7:recharge-notice", "check-7:recharge-notice"]


def test_business_rejection_is_read_from_the_envelope() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"ok": False, "data": None, "error": {"code": "INVALID_REQUEST"}, "metadata": {}},
        )

    gateway = InfraiGateway("test-key", transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(InfraiError) as caught:
            gateway.get_balance()
    finally:
        gateway.close()

    assert caught.value.code == "INVALID_REQUEST"
    assert caught.value.status_code == 400
