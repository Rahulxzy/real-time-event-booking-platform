
from fastapi import APIRouter, Depends, Header, Request, status
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.services.webhook_service import process_razorpay_webhook


router = APIRouter(
    prefix="/webhooks",
    tags=["Webhooks"],
)


@router.post(
    "/razorpay",
    status_code=status.HTTP_200_OK,
)
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: str = Header(
        alias="X-Razorpay-Signature",
    ),
    x_razorpay_event_id: str = Header(
        alias="x-razorpay-event-id",
    ),
    db: Session = Depends(get_db),
):
    """
    Public Razorpay webhook endpoint.

    Authentication is intentionally not required because Razorpay
    authenticates webhook requests using its HMAC signature.
    """

    raw_body = await request.body()

    return process_razorpay_webhook(
        db,
        raw_body=raw_body,
        signature=x_razorpay_signature,
        provider_event_id=x_razorpay_event_id,
    )
