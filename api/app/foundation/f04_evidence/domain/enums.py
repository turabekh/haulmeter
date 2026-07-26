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
    """AI-CONTEXT: the template picks the TITLE, which is the first line a clerk
    reads. `incident` exists because M5-FR4 was composing `cargo_condition`, so a
    pack about an accident or a dispute announced itself as a cargo condition
    report — wrong on the one line whose whole job is to say what this document is.
    Never persisted: it is chosen at composition time, so adding a value costs no
    migration."""

    detention_claim = "detention_claim"
    tonu = "tonu"
    on_time_proof = "on_time_proof"
    cargo_condition = "cargo_condition"
    incident = "incident"
