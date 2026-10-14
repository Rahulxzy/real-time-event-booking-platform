from fastapi import FastAPI

app = FastAPI(title = "Real-Time Event Booking Platfrom")

@app.get("/health")
def health_check():
    return {"status": "ok"}