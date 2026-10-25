from app.models import PaymentStatus

ALLOWED_TRANSITIONS = {
    (PaymentStatus.pending, PaymentStatus.succeeded),
    (PaymentStatus.pending, PaymentStatus.failed),
    (PaymentStatus.succeeded, PaymentStatus.refunded),
}


def is_allowed_transition(current: PaymentStatus | str, new: PaymentStatus | str) -> bool:
    return (PaymentStatus(current), PaymentStatus(new)) in ALLOWED_TRANSITIONS
