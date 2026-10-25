from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models import PaymentMethod, PaymentStatus
from app.services.pricing import normalize_promo_code, validate_payment_terms

# strict=True не даёт протащить float (в том числе 990000.0) в денежные поля.
Kopecks = Annotated[int, Field(ge=0, strict=True)]


class TariffRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    price: Kopecks


class PaymentCreate(BaseModel):
    tariff_id: int = Field(gt=0)
    email: EmailStr
    method: PaymentMethod
    installment_months: Literal[3, 6, 12] | None = None
    promo_code: str | None = None

    @field_validator("promo_code")
    @classmethod
    def promo_must_be_known(cls, value: str | None) -> str | None:
        return normalize_promo_code(value)

    @model_validator(mode="after")
    def installment_only_with_term(self) -> "PaymentCreate":
        validate_payment_terms(self.method, self.installment_months)
        return self


class BankWebhook(BaseModel):
    payment_id: int = Field(gt=0)
    status: PaymentStatus


class BankWebhookResult(BaseModel):
    result: Literal["ok"]


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: PaymentStatus
    tariff_id: int
    amount: Kopecks
    discount: Kopecks
    method: PaymentMethod
    installment_months: Literal[3, 6, 12] | None
    schedule: list[Kopecks] | None
    email: EmailStr
    created_at: datetime
