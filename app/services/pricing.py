from dataclasses import dataclass

from app.models import PaymentMethod

# Код из ТЗ. Сравнение без учёта регистра.
PROMO_CODE = "KVITTO10"
PROMO_PERCENT = 10
INSTALLMENT_MONTHS = (3, 6, 12)


class UnknownPromoCode(ValueError):
    """Неизвестный промокод. ValueError нужен, чтобы FastAPI отдал 422."""


@dataclass(frozen=True, slots=True)
class PriceQuote:
    amount: int
    discount: int
    schedule: list[int] | None


def _kopecks(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer number of kopecks")
    if value < 0:
        raise ValueError(f"{name} must be >= 0")
    return value


def normalize_promo_code(promo_code: str | None) -> str | None:
    if promo_code is None:
        return None
    normalized = promo_code.strip().upper()
    if normalized != PROMO_CODE:
        raise UnknownPromoCode(f"unknown promo code: {promo_code}")
    return PROMO_CODE


def discount_kopecks(price: int, promo_code: str | None) -> int:
    """10% от цены тарифа. Только целочисленная арифметика."""
    price = _kopecks(price, "price")
    if normalize_promo_code(promo_code) is None:
        return 0
    return price * PROMO_PERCENT // 100


def validate_payment_terms(
    method: PaymentMethod | str,
    installment_months: int | None,
) -> PaymentMethod:
    if isinstance(method, PaymentMethod):
        parsed = method
    else:
        try:
            parsed = PaymentMethod(method)
        except ValueError as exc:
            raise ValueError("method must be card, sbp, or installment") from exc

    if parsed == PaymentMethod.installment:
        if installment_months not in INSTALLMENT_MONTHS:
            raise ValueError("installment_months must be 3, 6, or 12")
    elif installment_months is not None:
        raise ValueError("installment_months is allowed only for installment")
    return parsed


def build_schedule(amount: int, months: int) -> list[int]:
    """Делит сумму на месяцы. Остаток копеек добавляется к первым платежам."""
    amount = _kopecks(amount, "amount")
    if months not in INSTALLMENT_MONTHS:
        raise ValueError("installment_months must be 3, 6, or 12")

    base, remainder = divmod(amount, months)
    return [base + (1 if index < remainder else 0) for index in range(months)]


def calculate_payment(
    *,
    price: int,
    method: PaymentMethod | str,
    installment_months: int | None = None,
    promo_code: str | None = None,
) -> PriceQuote:
    price = _kopecks(price, "price")
    parsed_method = validate_payment_terms(method, installment_months)
    discount = discount_kopecks(price, promo_code)
    amount = price - discount
    schedule = (
        build_schedule(amount, installment_months)
        if parsed_method == PaymentMethod.installment
        else None
    )
    return PriceQuote(amount=amount, discount=discount, schedule=schedule)
