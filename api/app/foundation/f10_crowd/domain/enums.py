import enum


class SignalType(enum.Enum):
    parking_fullness = "parking_fullness"
    weigh_station_status = "weigh_station_status"
    fuel_price = "fuel_price"
    facility_attribute = "facility_attribute"
    # M13-FR4: is this vendor actually at this facility right now / sold out?
    # Subject-scoped (Submission.subject_ref = vendor id) — never facility-wide.
    vendor_present = "vendor_present"
    vendor_sold_out = "vendor_sold_out"
