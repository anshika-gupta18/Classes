from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr, Field, validator
from typing import List, Optional
from datetime import datetime
import pytz
import logging


# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

logger = logging.getLogger(__name__)

app = FastAPI(title="Fitness Studio Booking API")


# Data Models with Validation
class FitnessClass(BaseModel):
    id: int
    name: str
    instructor: str
    schedule: datetime
    capacity: int = Field(..., gt=0, description="Total capacity must be > 0")
    available_slots: int

    @validator("available_slots")
    def check_slots(cls, v, values):
        if "capacity" in values and v > values["capacity"]:
            raise ValueError("Available slots cannot exceed capacity")
        return v

class BookingRequest(BaseModel):
    class_id: int = Field(..., gt=0, description="Class ID must be positive")
    client_name: str = Field(..., min_length=2, max_length=50)
    client_email: EmailStr

class Booking(BaseModel):
    id: int
    class_id: int
    class_name: str
    client_name: str
    client_email: EmailStr
    booking_time: datetime


# In-memory DB (IST timezone)
IST = pytz.timezone("Asia/Kolkata")

classes: List[FitnessClass] = [
    FitnessClass(id=1, name="Yoga", instructor="Alice",
                 schedule=IST.localize(datetime(2025, 8, 22, 8, 0)),
                 capacity=10, available_slots=10),
    FitnessClass(id=2, name="Zumba", instructor="Bob",
                 schedule=IST.localize(datetime(2025, 8, 22, 10, 0)),
                 capacity=12, available_slots=12),
    FitnessClass(id=3, name="HIIT", instructor="Charlie",
                 schedule=IST.localize(datetime(2025, 8, 22, 18, 0)),
                 capacity=15, available_slots=15),
]

bookings: List[Booking] = []


# Global Error Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unexpected error: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Please try again later."}
    )


# Routes
@app.get("/classes")
def get_classes(timezone: Optional[str] = "Asia/Kolkata"):
    """
    Returns upcoming classes (converted to requested timezone).
    """
    try:
        target_tz = pytz.timezone(timezone)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid timezone")

    response = []
    for c in classes:
        converted_time = c.schedule.astimezone(target_tz)
        response.append({
            "id": c.id,
            "name": c.name,
            "instructor": c.instructor,
            "schedule": converted_time.strftime("%Y-%m-%d %H:%M:%S %Z%z"),
            "capacity": c.capacity,
            "available_slots": c.available_slots
        })
    logger.info(f"Returned {len(response)} classes in timezone {timezone}")
    return response


@app.post("/book", response_model=Booking)
def book_class(request: BookingRequest):
    """
    Book a class if slots available.
    """
    fitness_class = next((c for c in classes if c.id == request.class_id), None)
    if not fitness_class:
        raise HTTPException(status_code=404, detail="Class not found")

    if fitness_class.available_slots <= 0:
        raise HTTPException(status_code=400, detail="No slots available")

    # prevent duplicate booking for same class & email
    if any(b.client_email == request.client_email and b.class_id == request.class_id for b in bookings):
        raise HTTPException(status_code=400, detail="Already booked for this class")

    booking_id = len(bookings) + 1
    new_booking = Booking(
        id=booking_id,
        class_id=fitness_class.id,
        class_name=fitness_class.name,
        client_name=request.client_name,
        client_email=request.client_email,
        booking_time=datetime.now(pytz.utc)
    )

    bookings.append(new_booking)
    fitness_class.available_slots -= 1

    logger.info(f"Booking created: {new_booking.client_email} -> {fitness_class.name}")
    return new_booking


@app.get("/bookings", response_model=List[Booking])
def get_bookings(email: Optional[EmailStr] = Query(None)):
    """
    Get all bookings or bookings for a specific email.
    """
    result = bookings if not email else [b for b in bookings if b.client_email == email]
    logger.info(f"Returned {len(result)} bookings for email={email}")
    return result
