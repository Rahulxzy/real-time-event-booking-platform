from datetime import datetime
from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class VenueCreate(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    address: str = Field(min_length=1, max_length=500)
    city: str = Field(min_length=1, max_length=100)


class VenueUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    address: str | None = Field(default=None, min_length=1, max_length=500)
    city: str | None = Field(default=None, min_length=1, max_length=100)


class VenueResponse(BaseModel):
    id: int
    name: str
    address: str
    city: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EventCreate(BaseModel):
    venue_id: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    starts_at: datetime
    ends_at: datetime
    price: Decimal = Field(
        ge=0,
        max_digits=10,
        decimal_places=2,
    )
    capacity: int = Field(gt=0)

    @field_validator("starts_at", "ends_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Datetime must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_event_times(self):
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class EventUpdate(BaseModel):
    venue_id: int | None = Field(default=None, gt=0)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    price: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=10,
        decimal_places=2,
    )
    capacity: int | None = Field(default=None, gt=0)

    @field_validator("starts_at", "ends_at")
    @classmethod
    def require_timezone(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is not None and (
            value.tzinfo is None or value.utcoffset() is None
        ):
            raise ValueError("Datetime must include a timezone")
        return value

    @model_validator(mode="after")
    def validate_event_times(self):
        if (
            self.starts_at is not None
            and self.ends_at is not None
            and self.ends_at <= self.starts_at
        ):
            raise ValueError("ends_at must be after starts_at")
        return self


class EventResponse(BaseModel):
    id: int
    venue_id: int
    title: str
    description: str | None
    starts_at: datetime
    ends_at: datetime
    price: Decimal
    capacity: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SeatCreate(BaseModel):
    row_label: str = Field(min_length=1, max_length=10)
    seat_number: int = Field(gt=0)


class SeatUpdate(BaseModel):
    row_label: str | None = Field(
        default=None,
        min_length=1,
        max_length=10,
    )
    seat_number: int | None = Field(default=None, gt=0)


class SeatResponse(BaseModel):
    id: int
    venue_id: int
    row_label: str
    seat_number: int

    model_config = ConfigDict(from_attributes=True)



class EventSeatResponse(BaseModel):
    id: int
    event_id: int
    seat_id: int
    venue_id: int
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EventSeatAvailabilityResponse(BaseModel):
    id: int
    event_id: int
    seat_id: int
    row_label: str
    seat_number: int
    status: str

    model_config = ConfigDict(from_attributes=True)