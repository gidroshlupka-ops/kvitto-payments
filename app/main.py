from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import (
    change_payment_status,
    create_payment,
    get_payment,
    get_payment_by_idempotency_key,
    get_tariff,
    list_tariffs,
    seed_tariffs,
)
from app.database import SessionLocal, get_session, init_db
from app.models import Payment, Tariff
from app.schemas import BankWebhook, BankWebhookResult, PaymentCreate, PaymentRead, TariffRead

IDEMPOTENCY_KEY_MAX_LENGTH = 255


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Создание таблиц и сид тарифов выполняются при старте процесса.
    await init_db()
    async with SessionLocal() as session:
        await seed_tariffs(session)
    yield


app = FastAPI(title="Kvitto Payments", lifespan=lifespan)


def _idempotency_key(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if cleaned == "":
        return None
    if len(cleaned) > IDEMPOTENCY_KEY_MAX_LENGTH:
        raise RequestValidationError(
            [
                {
                    "type": "string_too_long",
                    "loc": ("header", "Idempotency-Key"),
                    "msg": "String should have at most 255 characters",
                    "input": cleaned,
                    "ctx": {"max_length": IDEMPOTENCY_KEY_MAX_LENGTH},
                }
            ]
        )
    return cleaned


@app.get("/tariffs", response_model=list[TariffRead])
async def get_tariffs(session: AsyncSession = Depends(get_session)) -> list[Tariff]:
    return await list_tariffs(session)


@app.post("/payments", response_model=PaymentRead, status_code=status.HTTP_201_CREATED)
async def post_payment(
    body: PaymentCreate,
    response: Response,
    session: AsyncSession = Depends(get_session),
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> Payment:
    key = _idempotency_key(idempotency_key)
    # Повтор с тем же ключом отдаём до проверки тарифа: тело второго запроса не создаёт дубль.
    if key is not None:
        existing = await get_payment_by_idempotency_key(session, key)
        if existing is not None:
            response.status_code = status.HTTP_200_OK
            return existing

    tariff = await get_tariff(session, body.tariff_id)
    if tariff is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tariff not found")

    payment, created = await create_payment(
        session,
        tariff=tariff,
        body=body,
        idempotency_key=key,
    )
    if not created:
        response.status_code = status.HTTP_200_OK
    return payment


@app.get("/payments/{payment_id}", response_model=PaymentRead)
async def get_payment_by_id(
    payment_id: int,
    session: AsyncSession = Depends(get_session),
) -> Payment:
    payment = await get_payment(session, payment_id)
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="payment not found")
    return payment


@app.post("/webhooks/bank", response_model=BankWebhookResult)
async def bank_webhook(
    body: BankWebhook,
    session: AsyncSession = Depends(get_session),
) -> BankWebhookResult | JSONResponse:
    payment = await get_payment(session, body.payment_id)
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="payment not found")
    changed = await change_payment_status(session, payment, body.status.value)
    if not changed:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"error": "invalid_transition"},
        )
    return BankWebhookResult(result="ok")
