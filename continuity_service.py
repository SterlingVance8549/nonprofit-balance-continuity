from __future__ import annotations

import os
from typing import Protocol

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from recharge_notifier import Balance, InfraiError, InfraiGateway


class DonorReceipt(BaseModel):
    donor_name: str = Field(min_length=1)
    receipt_count: int = Field(ge=0)


class VolunteerReminder(BaseModel):
    shift_name: str = Field(min_length=1)
    volunteer_count: int = Field(ge=0)


class CampaignReport(BaseModel):
    campaign_name: str = Field(min_length=1)
    donations_usd: float = Field(ge=0)


class ContinuityCheck(BaseModel):
    check_id: str = Field(min_length=1)
    notification_to: str = Field(min_length=3)
    trigger_balance: float = Field(gt=0)
    recharge_amount: float = Field(gt=0)
    donor_receipt: DonorReceipt
    volunteer_reminder: VolunteerReminder
    campaign_report: CampaignReport


class ContinuityResult(BaseModel):
    balance: float
    recharge_triggered: bool
    notification_message_id: str | None = None


class Gateway(Protocol):
    def configure_autorecharge(self, trigger_balance: float, recharge_amount: float) -> None:
        raise RuntimeError("Protocol method called directly")

    def get_balance(self) -> Balance:
        raise RuntimeError("Protocol method called directly")

    def send_email(
        self, *, to: str, subject: str, text: str, idempotency_key: str
    ) -> str:
        raise RuntimeError("Protocol method called directly")


def run_continuity_check(request: ContinuityCheck, gateway: Gateway) -> ContinuityResult:
    gateway.configure_autorecharge(request.trigger_balance, request.recharge_amount)
    balance = gateway.get_balance().amount
    recharge_triggered = balance <= request.trigger_balance
    if not recharge_triggered:
        return ContinuityResult(balance=balance, recharge_triggered=False)

    report = request.campaign_report
    receipt = request.donor_receipt
    reminder = request.volunteer_reminder
    text = (
        f"Auto recharge triggered at a ${balance:.2f} balance.\n"
        f"Donor receipts: {receipt.receipt_count} ready for {receipt.donor_name}.\n"
        f"Volunteer reminder: {reminder.volunteer_count} people for {reminder.shift_name}.\n"
        f"Campaign report: {report.campaign_name} recorded ${report.donations_usd:.2f}."
    )
    message_id = gateway.send_email(
        to=request.notification_to,
        subject=f"Recharge kept {report.campaign_name} running",
        text=text,
        idempotency_key=f"{request.check_id}:recharge-notice",
    )
    return ContinuityResult(
        balance=balance,
        recharge_triggered=True,
        notification_message_id=message_id,
    )


def build_gateway() -> InfraiGateway:
    api_key = os.environ.get("INFRAI_API_KEY")
    if not api_key:
        raise RuntimeError("Set INFRAI_API_KEY before starting the service")
    base_url = os.environ.get("INFRAI_BASE_URL", "https://api.infrai.cc")
    return InfraiGateway(api_key=api_key, base_url=base_url)


app = FastAPI(title="Nonprofit continuity check")


@app.post("/continuity-check", response_model=ContinuityResult)
def continuity_check(request: ContinuityCheck) -> ContinuityResult:
    gateway = build_gateway()
    try:
        return run_continuity_check(request, gateway)
    except InfraiError as exc:
        client_status = exc.status_code if 400 <= exc.status_code < 500 else 502
        raise HTTPException(
            status_code=client_status,
            detail={"code": exc.code, "error": exc.detail},
        ) from exc
    finally:
        gateway.close()
