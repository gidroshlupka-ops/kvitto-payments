from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Payment, PaymentStatus, TARIFF_SEED, Tariff
from app.schemas import PaymentCreate
from app.services.pricing import calculate_payment
from app.services.status import is_allowed_transition


def _stage_tariffs(session: AsyncSession, rows: list[Tariff]) -> None:
    by_title = {tariff.title: tariff for tariff in rows}
    for title, price in TARIFF_SEED:
        tariff = by_title.get(title)
        if tariff is None:
            session.add(Tariff(title=title, price=price))
        elif tariff.price != price:
            tariff.price = price


async def seed_tariffs(session: AsyncSession) -> None:
    """Создаёт три тарифа из ТЗ. Повторный старт и второй воркер не плодят дубли."""
    rows = list(await session.scalars(select(Tariff)))
    _stage_tariffs(session, rows)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        rows = list(await session.scalars(select(Tariff)))
        _stage_tariffs(session, rows)
        await session.commit()


async def list_tariffs(session: AsyncSession) -> list[Tariff]:
    result = await session.scalars(select(Tariff).order_by(Tariff.id))
    return list(result.all())


async def get_tariff(session: AsyncSession, tariff_id: int) -> Tariff | None:
    return await session.get(Tariff, tariff_id)


async def get_payment(session: AsyncSession, payment_id: int) -> Payment | None:
    return await session.get(Payment, payment_id)


async def get_payment_by_idempotency_key(
    session: AsyncSession,
    idempotency_key: str,
) -> Payment | None:
    return await session.scalar(
        select(Payment).where(Payment.idempotency_key == idempotency_key)
    )


async def create_payment(
    session: AsyncSession,
    *,
    tariff: Tariff,
    body: PaymentCreate,
    idempotency_key: str | None,
) -> tuple[Payment, bool]:
    """Создаёт платёж. Если ключ уже занят, возвращает существующий и created=False."""
    if idempotency_key is not None:
        existing = await get_payment_by_idempotency_key(session, idempotency_key)
        if existing is not None:
            return existing, False

    quote = calculate_payment(
        price=tariff.price,
        method=body.method,
        installment_months=body.installment_months,
        promo_code=body.promo_code,
    )
    payment = Payment(
        status=PaymentStatus.pending.value,
        tariff_id=tariff.id,
        amount=quote.amount,
        discount=quote.discount,
        method=body.method.value,
        installment_months=body.installment_months,
        schedule=quote.schedule,
        idempotency_key=idempotency_key,
        email=str(body.email),
    )
    session.add(payment)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        if idempotency_key is None:
            raise
        existing = await get_payment_by_idempotency_key(session, idempotency_key)
        if existing is None:
            raise
        return existing, False
    await session.refresh(payment)
    return payment, True


async def change_payment_status(
    session: AsyncSession,
    payment: Payment,
    new_status: str,
) -> bool:
    """Меняет статус только если в базе всё ещё тот статус, который мы проверили."""
    if not is_allowed_transition(payment.status, new_status):
        return False
    result = await session.execute(
        update(Payment)
        .where(Payment.id == payment.id, Payment.status == payment.status)
        .values(status=new_status)
    )
    await session.commit()
    if result.rowcount != 1:
        return False
    payment.status = new_status
    return True
