import pytest
from pydantic import ValidationError

from app.models import TARIFF_SEED
from app.schemas import PaymentCreate
from app.services.pricing import (
    UnknownPromoCode,
    build_schedule,
    calculate_payment,
)

PRICES = [price for _, price in TARIFF_SEED]
MONTHS = [3, 6, 12]


def test_standard_installment_matches_spec_example():
    quote = calculate_payment(
        price=1_990_000,
        method="installment",
        installment_months=3,
    )

    assert quote.discount == 0
    assert quote.amount == 1_990_000
    assert quote.schedule == [663_334, 663_333, 663_333]
    assert sum(quote.schedule) == quote.amount


@pytest.mark.parametrize("price", PRICES)
@pytest.mark.parametrize("promo", ["KVITTO10", "kvitto10", "KvItTo10"])
def test_promo_takes_ten_percent_in_kopecks(price: int, promo: str):
    quote = calculate_payment(price=price, method="card", promo_code=promo)

    assert quote.discount == price * 10 // 100
    assert quote.amount == price - quote.discount
    assert quote.schedule is None
    assert isinstance(quote.amount, int)
    assert isinstance(quote.discount, int)


@pytest.mark.parametrize("price", PRICES)
@pytest.mark.parametrize("method", ["card", "sbp"])
def test_payment_without_promo_keeps_full_price(price: int, method: str):
    quote = calculate_payment(price=price, method=method)

    assert quote.amount == price
    assert quote.discount == 0
    assert quote.schedule is None


@pytest.mark.parametrize("price", PRICES)
@pytest.mark.parametrize("months", MONTHS)
@pytest.mark.parametrize("promo", [None, "KVITTO10", "kvitto10"])
def test_schedule_sums_to_payable_amount(price: int, months: int, promo: str | None):
    quote = calculate_payment(
        price=price,
        method="installment",
        installment_months=months,
        promo_code=promo,
    )

    assert quote.schedule is not None
    assert len(quote.schedule) == months
    assert sum(quote.schedule) == quote.amount
    assert quote.amount == price - quote.discount
    assert all(isinstance(part, int) and not isinstance(part, bool) for part in quote.schedule)

    base, remainder = divmod(quote.amount, months)
    assert quote.schedule == [base + (1 if index < remainder else 0) for index in range(months)]
    assert max(quote.schedule) - min(quote.schedule) <= 1


def test_remainder_kopecks_go_to_the_first_payments():
    assert build_schedule(10, 3) == [4, 3, 3]
    assert build_schedule(5, 3) == [2, 2, 1]
    assert build_schedule(1_990_000, 6)[:4] == [331_667, 331_667, 331_667, 331_667]
    assert build_schedule(1_990_000, 6)[4:] == [331_666, 331_666]


@pytest.mark.parametrize(
    "promo",
    ["SALE", "KVITT010", "KVITTO", "KVITTO11", "kvitto"],
)
def test_unknown_promo_is_rejected(promo: str):
    with pytest.raises(UnknownPromoCode):
        calculate_payment(price=990_000, method="card", promo_code=promo)


def test_installment_requires_three_six_or_twelve_months():
    with pytest.raises(ValueError, match="installment_months"):
        calculate_payment(price=990_000, method="installment")

    with pytest.raises(ValueError, match="installment_months"):
        calculate_payment(price=990_000, method="installment", installment_months=5)

    with pytest.raises(ValueError, match="installment_months"):
        calculate_payment(price=990_000, method="card", installment_months=3)


def test_float_kopecks_are_rejected():
    with pytest.raises(TypeError):
        calculate_payment(price=990_000.0, method="card")  # type: ignore[arg-type]


@pytest.mark.parametrize("promo", ["", " ", "   "])
def test_blank_promo_is_rejected(promo: str):
    with pytest.raises(UnknownPromoCode):
        calculate_payment(price=990_000, method="card", promo_code=promo)


def test_lowercase_promo_passes_schema_validation():
    body = PaymentCreate(
        tariff_id=1,
        email="student@school.ru",
        method="sbp",
        promo_code="kvitto10",
    )
    assert body.promo_code == "KVITTO10"


def test_schema_rejects_unknown_promo():
    with pytest.raises(ValidationError):
        PaymentCreate(
            tariff_id=1,
            email="student@school.ru",
            method="card",
            promo_code="KVITT010",
        )
