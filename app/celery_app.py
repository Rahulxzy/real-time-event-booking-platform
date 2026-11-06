
from celery import Celery

from app.database import settings


celery_app = Celery(
    "event_booking",
    broker=settings.redis_url,
    include=["app.tasks.reservation_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_ignore_result=True,
    broker_connection_retry_on_startup=True,

    beat_schedule={
        "expire-reservations-every-minute": {
            "task": "reservations.expire_due",
            "schedule": 60.0,
        },
    },
)
