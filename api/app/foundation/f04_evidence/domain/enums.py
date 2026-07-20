import enum


class RecordType(enum.Enum):
    GEOFENCE = "GEOFENCE"
    PHOTO = "PHOTO"
    DOCUMENT = "DOCUMENT"
    USER_ACTION = "USER_ACTION"
    NOTIFICATION = "NOTIFICATION"
    SYSTEM = "SYSTEM"


class ArtifactType(enum.Enum):
    photo = "photo"
    pdf = "pdf"
    document = "document"
    other = "other"


class PackTemplate(enum.Enum):
    detention_claim = "detention_claim"
    tonu = "tonu"
    on_time_proof = "on_time_proof"
    cargo_condition = "cargo_condition"
