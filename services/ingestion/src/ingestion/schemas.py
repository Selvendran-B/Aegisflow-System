
"""Wire format for POST /api/v1/transactions.

M1 compatibility: map id -> txn_id and ts -> occurred_at.
Money uses Decimal, and timestamps must carry a timezone.
"""
from datetime import datetime
from decimal import Decimal
from ipaddress import IPv4Address, IPv6Address
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class TransactionIn(BaseModel):
    id: UUID
    ts: datetime
    account_id: UUID
    external_ref: str | None = Field(default=None, max_length=64)
    counterparty_id: UUID | None = None
    device_id: str | None = Field(default=None, max_length=80)
    ip_id: IPv4Address | IPv6Address | None = None
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    currency: str = Field(default="INR", pattern=r"^[A-Z]{3}$")
    channel: Literal["card", "wire", "upi", "ach", "atm"]
    direction: Literal["debit", "credit"]
    merchant_mcc: str | None = Field(default=None, max_length=4)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)

    @field_validator("ts")
    @classmethod
    def _tz(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError("ts must carry a timezone")
        return v

    def feature_input(self) -> dict:
        from aegis_ml.features.definitions import amount_minor

        return {
            "id": str(self.id),
            "ts": self.ts,
            "account_id": str(self.account_id),
            "amount_minor": amount_minor(self.amount),
            "device_id": self.device_id,
            "ip_id": str(self.ip_id) if self.ip_id else None,
        }


class TransactionOut(BaseModel):
    id: UUID
    decision: str | None = None
    duplicate: bool = False
