import enum


class FacilityType(enum.Enum):
    truck_stop = "truck_stop"
    rest_area = "rest_area"
    shipper_receiver = "shipper_receiver"
    parking_property = "parking_property"
    scale = "scale"
    weigh_station = "weigh_station"
    fuel_station = "fuel_station"
    repair = "repair"
    composite = "composite"


class FacilityStatus(enum.Enum):
    candidate = "candidate"
    confirmed = "confirmed"
    merged = "merged"


class SourceKind(enum.Enum):
    osm = "osm"
    fhwa = "fhwa"
    tpims = "tpims"
    chain_list = "chain_list"
    user_checkin = "user_checkin"
    admin = "admin"
