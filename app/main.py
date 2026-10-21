from fastapi import FastAPI

from app.routers import auth, venues

app = FastAPI(title="Real-Time Event Booking Platform")

app.include_router(auth.router)
app.include_router(venues.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}