import enum
from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON, TypeDecorator

# Цены из ТЗ в копейках: 9 900 ₽, 19 900 ₽, 29 900 ₽.
TARIFF_SEED: tuple[tuple[str, int], ...] = (
    ("basic", 990_000),
    ("standard", 1_990_000),
    ("premium", 2_990_000),
)


class PaymentStatus(enum.StrEnum):
    pending = "pending"
    succeeded = "succeeded"
    failed = "failed"
    refunded = "refunded"


class PaymentMethod(enum.StrEnum):
    card = "card"
    sbp = "sbp"
    installment = "installment"


class UtcDateTime(TypeDecorator):
    """SQLite не хранит смещение. При чтении возвращаем то же мгновение как UTC."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: object) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: object) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class Base(DeclarativeBase):
    pass


class Tariff(Base):
    __tablename__ = "tariffs"
    __table_args__ = (
        CheckConstraint("price >= 0", name="ck_tariffs_price_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    price: Mapped[int] = mapped_column(BigInteger, nullable=False)


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_payments_idempotency_key"),
        CheckConstraint("amount >= 0", name="ck_payments_amount_non_negative"),
        CheckConstraint("discount >= 0", name="ck_payments_discount_non_negative"),
        CheckConstraint(
            "status IN ('pending', 'succeeded', 'failed', 'refunded')",
            name="ck_payments_status",
        ),
        CheckConstraint(
            "method IN ('card', 'sbp', 'installment')",
            name="ck_payments_method",
        ),
        CheckConstraint(
            "installment_months IS NULL OR installment_months IN (3, 6, 12)",
            name="ck_payments_installment_months",
        ),
        CheckConstraint(
            "("
            "method = 'installment' "
            "AND installment_months IS NOT NULL "
            "AND schedule IS NOT NULL"
            ") OR ("
            "method != 'installment' "
            "AND installment_months IS NULL "
            "AND schedule IS NULL"
            ")",
            name="ck_payments_installment_shape",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=PaymentStatus.pending.value,
    )
    tariff_id: Mapped[int] = mapped_column(
        ForeignKey("tariffs.id"),
        nullable=False,
        index=True,
    )
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    discount: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    installment_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    schedule: Mapped[list[int] | None] = mapped_column(
        JSON(none_as_null=True),
        nullable=True,
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UtcDateTime(),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
