import enum


class BookingState(enum.Enum):
    booked = "booked"
    checked_in = "checked_in"
    checked_out = "checked_out"
    canceled = "canceled"
    refunded = "refunded"
