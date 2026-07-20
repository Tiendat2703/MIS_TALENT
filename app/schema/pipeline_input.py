"""Validated external contract accepted by the Finance pipeline."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.schema.handoff_packs import StrictModel


class ContractUploadPackage(StrictModel):
    """One contract merged run-locally with the normal portfolio data."""

    contract_id: str = Field(min_length=1)
    customer_id: str = Field(min_length=1)
    start_date: date
    end_date: date
    status: Literal["Pending approval"] = "Pending approval"
    description: str = Field(min_length=1)
    contract_value: float = Field(gt=0)
    gross_margin: float = Field(ge=-1, le=1)
    payment_terms: str = Field(min_length=1)
    requested_amount: float = Field(gt=0)
    funding_need_type: Literal[
        "PERFORMANCE_BOND",
        "TRADE_FINANCE",
        "WORKING_CAPITAL",
        "RECEIVABLE_FINANCING",
    ]
    tenor: str = Field(min_length=1)

    @field_validator("status", mode="before")
    @classmethod
    def enforce_new_contract_status(cls, _value: object) -> str:
        """A newly uploaded contract always starts in the approval queue."""
        return "Pending approval"

    @model_validator(mode="after")
    def validate_dates(self) -> "ContractUploadPackage":
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        return self


__all__ = ["ContractUploadPackage"]
