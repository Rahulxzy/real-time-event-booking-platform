
from fastapi import FastAPI

from app.routers import auth, events, venues

app = FastAPI(title="Real-Time Event Booking Platform")

app.include_router(auth.router)
app.include_router(venues.router)
app.include_router(events.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
