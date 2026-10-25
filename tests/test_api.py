import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import Payment

pytestmark = pytest.mark.anyio


async def _tariffs(client: AsyncClient) -> dict[str, dict]:
    response = await client.get("/tariffs")
    assert response.status_code == 200
    return {row["title"]: row for row in response.json()}


def _payment(tariff_id: int, **extra: object) -> dict:
    body = {
        "tariff_id": tariff_id,
        "email": "student@school.ru",
        "method": "card",
    }
    body.update(extra)
    return body


async def test_payment_with_and_without_promo_code(client: AsyncClient) -> None:
    tariffs = await _tariffs(client)

    for tariff in tariffs.values():
        plain = await client.post("/payments", json=_payment(tariff["id"]))
        upper = await client.post(
            "/payments",
            json=_payment(tariff["id"], promo_code="KVITTO10", email="upper@school.ru"),
        )
        lower = await client.post(
            "/payments",
            json=_payment(tariff["id"], promo_code="kvitto10", email="lower@school.ru"),
        )

        assert plain.status_code == 201
        plain_body = plain.json()
        assert plain_body["created_at"].endswith(("Z", "+00:00"))
        assert plain_body["status"] == "pending"
        assert plain_body["discount"] == 0
        assert plain_body["amount"] == tariff["price"]

        discount = tariff["price"] * 10 // 100
        for response in (upper, lower):
            assert response.status_code == 201
            body = response.json()
            assert body["status"] == "pending"
            assert body["discount"] == discount
            assert body["amount"] == tariff["price"] - discount
            assert isinstance(body["amount"], int)
            assert isinstance(body["discount"], int)


async def test_installment_schedule_sums_to_payable_amount(client: AsyncClient) -> None:
    tariffs = await _tariffs(client)
    standard = tariffs["standard"]

    for months in (3, 6, 12):
        for promo_code in (None, "kvitto10"):
            for tariff in tariffs.values():
                payload = _payment(
                    tariff["id"],
                    method="installment",
                    installment_months=months,
                    email=f"{tariff['title']}-{months}@school.ru",
                )
                if promo_code is not None:
                    payload["promo_code"] = promo_code

                response = await client.post("/payments", json=payload)
                assert response.status_code == 201, response.text
                body = response.json()
                schedule = body["schedule"]

                assert body["installment_months"] == months
                assert isinstance(schedule, list)
                assert len(schedule) == months
                assert sum(schedule) == body["amount"]
                assert all(isinstance(part, int) for part in schedule)

                if promo_code is None:
                    assert body["amount"] == tariff["price"]
                else:
                    assert body["amount"] == tariff["price"] - tariff["price"] * 10 // 100

    example = await client.post(
        "/payments",
        json=_payment(
            standard["id"],
            method="installment",
            installment_months=3,
            email="example@school.ru",
        ),
    )
    assert example.status_code == 201
    assert example.json()["schedule"] == [663_334, 663_333, 663_333]
    assert sum(example.json()["schedule"]) == 1_990_000


async def test_same_idempotency_key_does_not_create_duplicate(client: AsyncClient) -> None:
    tariffs = await _tariffs(client)
    headers = {"Idempotency-Key": "order-42"}
    payload = _payment(tariffs["basic"]["id"], email="first@school.ru")

    first = await client.post("/payments", json=payload, headers=headers)
    second = await client.post(
        "/payments",
        json=_payment(
            tariffs["premium"]["id"],
            email="second@school.ru",
            promo_code="KVITTO10",
        ),
        headers=headers,
    )
    another = await client.post(
        "/payments",
        json=_payment(tariffs["basic"]["id"], email="third@school.ru"),
    )

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json() == first.json()
    assert second.json()["email"] == "first@school.ru"
    assert second.json()["tariff_id"] == tariffs["basic"]["id"]
    assert second.json()["discount"] == 0

    stored = await client.get(f"/payments/{first.json()['id']}")
    assert stored.status_code == 200
    assert stored.json() == first.json()

    assert another.status_code == 201
    assert another.json()["id"] != first.json()["id"]

    async with SessionLocal() as session:
        stored_count = await session.scalar(
            select(func.count())
            .select_from(Payment)
            .where(Payment.idempotency_key == "order-42")
        )
    assert stored_count == 1


async def test_forbidden_transition_does_not_change_status(client: AsyncClient) -> None:
    tariffs = await _tariffs(client)
    created = await client.post("/payments", json=_payment(tariffs["premium"]["id"]))
    assert created.status_code == 201
    payment_id = created.json()["id"]

    denied = await client.post(
        "/webhooks/bank",
        json={"payment_id": payment_id, "status": "refunded"},
    )
    assert denied.status_code == 409
    assert denied.json() == {"error": "invalid_transition"}
    assert (await client.get(f"/payments/{payment_id}")).json()["status"] == "pending"

    succeeded = await client.post(
        "/webhooks/bank",
        json={"payment_id": payment_id, "status": "succeeded"},
    )
    assert succeeded.status_code == 200
    assert succeeded.json() == {"result": "ok"}
    assert (await client.get(f"/payments/{payment_id}")).json()["status"] == "succeeded"

    still_blocked = await client.post(
        "/webhooks/bank",
        json={"payment_id": payment_id, "status": "failed"},
    )
    assert still_blocked.status_code == 409
    assert still_blocked.json() == {"error": "invalid_transition"}
    assert (await client.get(f"/payments/{payment_id}")).json()["status"] == "succeeded"


async def test_invalid_promo_and_idempotency_key_return_422(client: AsyncClient) -> None:
    tariffs = await _tariffs(client)
    tariff_id = tariffs["basic"]["id"]

    for promo_code in ("SALE", "KVITT010", "", " "):
        response = await client.post(
            "/payments",
            json=_payment(tariff_id, promo_code=promo_code, email="bad-promo@school.ru"),
        )
        assert response.status_code == 422
        assert response.json()["detail"][0]["loc"] == ["body", "promo_code"]

    too_long = await client.post(
        "/payments",
        json=_payment(tariff_id, email="long-key@school.ru"),
        headers={"Idempotency-Key": "k" * 256},
    )
    assert too_long.status_code == 422
    assert too_long.json()["detail"][0]["loc"] == ["header", "Idempotency-Key"]

    installment = await client.post(
        "/payments",
        json=_payment(tariff_id, method="card", installment_months=3),
    )
    assert installment.status_code == 422


async def test_missing_payment_returns_404(client: AsyncClient) -> None:
    response = await client.get("/payments/999999")
    assert response.status_code == 404

    webhook = await client.post(
        "/webhooks/bank",
        json={"payment_id": 999999, "status": "succeeded"},
    )
    assert webhook.status_code == 404
