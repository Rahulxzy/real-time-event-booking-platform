
from fastapi import APIRouter, Depends, Header, status
from sqlalchemy.orm import Session

from app.dependencies import get_current_user, get_db
from app.models import User
from app.schemas import (
    PaymentOrderCreate,
    PaymentOrderResponse,
    PaymentVerificationCreate,
    PaymentVerificationResponse,
)
from app.services.payment_service import (
    create_payment_order,
    verify_checkout_payment,
)

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post(
    "/orders",
    response_model=PaymentOrderResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_order(
    payload: PaymentOrderCreate,
    idempotency_key: str = Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=255,
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return create_payment_order(
        db,
        reservation_id=payload.reservation_id,
        user=current_user,
        idempotency_key=idempotency_key,
    )


@router.post(
    "/verify",
    response_model=PaymentVerificationResponse,
    status_code=status.HTTP_200_OK,
)
def verify_payment(
    payload: PaymentVerificationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return verify_checkout_payment(
        db,
        order_id=payload.razorpay_order_id,
        razorpay_payment_id=payload.razorpay_payment_id,
        signature=payload.razorpay_signature,
        user=current_user,
    )
