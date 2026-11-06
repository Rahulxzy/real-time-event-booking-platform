
from app.celery_app import celery_app
from app.database import SessionLocal
from app.services.reservation_expiry_service import (
    expire_all_due_reservations,
)


@celery_app.task(name="reservations.expire_due")
def expire_due_reservations_task():
    """
    Periodically expire overdue reservations
    and release their reserved seats.
    """

    db = SessionLocal()

    try:
        expired_count = expire_all_due_reservations(db)

        db.commit()

        return expired_count

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()
