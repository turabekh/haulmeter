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
    # AI-CONTEXT: what happened at ONE STOP — arrival, notice, departure, and the
    # paperwork filed there (§23 entry 71). Added for the same reason `incident` was:
    # the only export a driver could reach rendered as a "Cargo condition report", and
    # it 404'd outright unless condition photos existed — so the pack that argues a
    # detention claim had no way out of the phone at all.
    stop_record = "stop_record"
    # AI-CONTEXT: the whole ROUTE in one document (§23 entry 78). Entry 71 found a
    # per-log export could only show a fragment of a stop; a per-stop export can only
    # show a fragment of a load. A driver who photographed a pickup and a delivery had
    # eight photos in the system and no document holding more than four.
    load_record = "load_record"
    # AI-CONTEXT: A1. A ROUTINE HANDOFF, not a claim and not an export. `stop_record`
    # already describes one stop, but it is the document a DRIVER reaches for their own
    # records; this one lands in a dispatcher's inbox. Same reasoning `incident` was
    # added for — the template picks the title, and a handoff announcing itself as a
    # "Stop record" is wrong on the one line whose whole job is to say what this is.
    stop_packet = "stop_packet"
