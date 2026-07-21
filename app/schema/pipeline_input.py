"""External contract draft accepted by the Finance pipeline entrypoints."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.schema.handoff_packs import StrictModel


PaymentTerms = Literal[
    "Monthly payment",
    "Milestone payment",
    "Performance bond required",
    "Possible LC/trade finance",
]


class ContractUploadPackage(StrictModel):
    """One contract draft merged run-locally with the normal portfolio data.

    Every user-provided field is optional so a separate Finance preflight can
    report missing information instead of Pydantic rejecting an incomplete
    draft before the agent sees it.  Constraints still apply when a value is
    supplied.
    """

    contract_id: str | None = Field(default=None, min_length=1)
    customer_id: str | None = Field(default=None, min_length=1)
    start_date: date | None = None
    end_date: date | None = None
    status: Literal["Pending approval"] = "Pending approval"
    description: str | None = Field(default=None, min_length=1)
    contract_value: float | None = Field(default=None, gt=0)
    gross_margin: float | None = Field(default=None, ge=0, le=1)
    payment_terms: PaymentTerms | None = None
    requested_amount: float | None = Field(default=None, gt=0)
    funding_need_type: Literal[
        "PERFORMANCE_BOND",
        "TRADE_FINANCE",
        "WORKING_CAPITAL",
        "RECEIVABLE_FINANCING",
    ] | None = None
    tenor: str | None = Field(default=None, min_length=1)

    @field_validator("status", mode="before")
    @classmethod
    def enforce_new_contract_status(cls, _value: object) -> str:
        """A newly uploaded contract always starts in the approval queue."""
        return "Pending approval"

    @model_validator(mode="after")
    def validate_dates(self) -> "ContractUploadPackage":
        if (
            self.start_date is not None
            and self.end_date is not None
            and self.end_date < self.start_date
        ):
            raise ValueError("end_date must not be before start_date")
        return self


__all__ = ["ContractUploadPackage", "PaymentTerms"]
