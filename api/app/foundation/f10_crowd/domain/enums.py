import enum


class SignalType(enum.Enum):
    parking_fullness = "parking_fullness"
    weigh_station_status = "weigh_station_status"
    fuel_price = "fuel_price"
    facility_attribute = "facility_attribute"
