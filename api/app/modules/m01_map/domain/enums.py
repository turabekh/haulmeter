import enum


class Preset(enum.Enum):
    drive = "drive"
    tonight = "tonight"
    work = "work"
    fuel = "fuel"
    # A5: repair, tire, wash and parts. A preset, not a new tab — §23's Food-chip
    # precedent settles that a chip row is a filter, and NAV-1 governs tabs.
    service = "service"


class NavProvider(enum.Enum):
    google = "google"
    apple = "apple"
    hammer = "hammer"
    copilot = "copilot"
